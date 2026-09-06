"""Load one saved forecast snapshot atomically into PostgreSQL."""

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from weather_pipeline.config import PROJECT_ROOT, parse_boolean, validate_city_config
from weather_pipeline.snapshot import prepare_snapshot


HOURLY_COLUMNS = (
    'city_id', 'retrieved_at', 'forecast_at', 'temperature_2m',
    'precipitation', 'wind_speed_10m', 'weather_code',
)


def connection_settings() -> dict:
    """Read project .env; exported environment variables take precedence."""
    values = {**dotenv_values(PROJECT_ROOT / '.env', interpolate=False), **os.environ}
    mapping = {'host': 'WAREHOUSE_HOST', 'port': 'WAREHOUSE_PORT',
               'dbname': 'WAREHOUSE_DATABASE', 'user': 'WAREHOUSE_USER',
               'password': 'WAREHOUSE_PASSWORD'}
    missing = [name for name in mapping.values() if not values.get(name)]
    if missing:
        raise ValueError(f"Missing database settings: {', '.join(missing)}")
    return {**{key: values[name] for key, name in mapping.items()},
            'connect_timeout': 10, 'options': '-c timezone=UTC'}


def load_prepared(conn: psycopg.Connection, prepared: dict, city: dict) -> bool:
    """Commit one prepared snapshot, or verify an identical existing snapshot.

    Returns True for an insertion and False for an identical replay. Use an
    autocommit connection so this transaction is the commit boundary; tests may
    wrap it in an outer rollback transaction.
    """
    snapshot = prepared['snapshot']
    rows = prepared['hourly_rows']
    if city['city_id'].strip() != snapshot['city_id']:
        raise ValueError('Configured city does not match snapshot city')
    key = (snapshot['city_id'], snapshot['retrieved_at'])
    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                '''INSERT INTO raw.city
                   (city_id, city_name, country_code, latitude, longitude, timezone, active)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_id) DO NOTHING''',
                (snapshot['city_id'], city['city_name'], city['country_code'],
                 float(city['latitude']), float(city['longitude']), city['timezone'],
                 parse_boolean(city['active'], city_id=snapshot['city_id'])),
            )
            cur.execute(
                '''INSERT INTO raw.forecast_snapshot
                   (city_id, retrieved_at, raw_response_path, request_params,
                    grid_latitude, grid_longitude)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (city_id, retrieved_at) DO NOTHING RETURNING city_id''',
                (*key, snapshot['raw_response_path'], Jsonb(snapshot['request_params']),
                 snapshot['grid_latitude'], snapshot['grid_longitude']),
            )
            inserted = cur.fetchone() is not None
            if not inserted:
                cur.execute(
                    '''SELECT request_params, grid_latitude, grid_longitude
                       FROM raw.forecast_snapshot WHERE city_id = %s AND retrieved_at = %s''', key)
                existing = cur.fetchone()
                expected = {name: snapshot[name] for name in
                            ('request_params', 'grid_latitude', 'grid_longitude')}
                cur.execute(
                    '''SELECT city_id, retrieved_at, forecast_at, temperature_2m,
                              precipitation, wind_speed_10m, weather_code
                       FROM raw.hourly_forecast WHERE city_id = %s AND retrieved_at = %s
                       ORDER BY forecast_at''', key)
                if existing != expected or cur.fetchall() != rows:
                    raise ValueError('Snapshot identity already exists with different content')
                return False
            cur.executemany(
                '''INSERT INTO raw.hourly_forecast
                   (city_id, retrieved_at, forecast_at, temperature_2m,
                    precipitation, wind_speed_10m, weather_code)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                [tuple(row[column] for column in HOURLY_COLUMNS) for row in rows],
            )
    return True


def load_directory(directory: Path, cities: dict, settings: dict) -> tuple[bool, int]:
    """Use a fresh connection for each snapshot, including after connection loss."""
    prepared = prepare_snapshot(directory)
    city_id = prepared['snapshot']['city_id']
    if city_id not in cities:
        raise ValueError(f'Unknown city_id: {city_id}')
    with psycopg.connect(**settings, autocommit=True) as conn:
        inserted = load_prepared(conn, prepared, cities[city_id])
    return inserted, len(prepared['hourly_rows'])


def load_batch(root: Path, cities: dict, settings: dict) -> dict[str, int]:
    """Scan root/city/snapshot directories; continue after individual failures."""
    if not root.is_dir():
        raise ValueError(f'Raw directory does not exist: {root}')
    directories = sorted(path for path in root.glob('*/*') if path.is_dir())
    if not directories:
        raise ValueError(f'No snapshot directories found in {root}')
    counts = {'loaded': 0, 'already_loaded': 0, 'failed': 0, 'incomplete': 0}
    for directory in directories:
        if not (directory / '_SUCCESS').is_file():
            counts['incomplete'] += 1
            print(f'INCOMPLETE: {directory}', flush=True)
            continue
        try:
            inserted, row_count = load_directory(directory, cities, settings)
        except (OSError, ValueError, psycopg.Error) as error:
            counts['failed'] += 1
            print(f'FAILED {directory}: {error}', file=sys.stderr, flush=True)
        else:
            status = 'loaded' if inserted else 'already_loaded'
            counts[status] += 1
            print(f'{status.upper()}: {directory} ({row_count} hours)', flush=True)
    print(f"Summary: {counts['loaded']} loaded, {counts['already_loaded']} already loaded, "
          f"{counts['failed']} failed, {counts['incomplete']} incomplete.")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Snapshot directory, or raw root with --all')
    parser.add_argument('--all', action='store_true', help='Replay all snapshots under directory')
    args = parser.parse_args(argv)
    try:
        cities = {c['city_id'].strip(): c for c in validate_city_config()}
        settings = connection_settings()
        if args.all:
            counts = load_batch(args.directory, cities, settings)
            return 1 if counts['failed'] else 0
        inserted, row_count = load_directory(args.directory, cities, settings)
    except (OSError, ValueError, psycopg.Error) as error:
        print(f'Load failed: {error}', file=sys.stderr)
        return 1
    if inserted:
        print(f"Loaded: 1 snapshot, {row_count} hourly records.")
    else:
        print('Already loaded: identical snapshot; no rows added.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
