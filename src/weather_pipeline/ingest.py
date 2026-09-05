"""Collect and preserve forecasts for configured cities."""

import argparse
import os
import sys
from pathlib import Path

from weather_pipeline.client import build_request_params, fetch_forecast
from weather_pipeline.config import (
    PROJECT_ROOT,
    parse_boolean,
    validate_city_config,
    validate_pipeline_config,
)
from weather_pipeline.raw import save_raw_snapshot
from weather_pipeline.validation import validate_forecast


def ingest_city(api: dict, policy: dict, city: dict, raw_dir: Path) -> None:
    """Fetch, save, and validate one city; let the caller handle failures."""
    raw_body, retrieved_at = fetch_forecast(
        api, city, policy["request_timeout_seconds"],
        max_retries=policy["max_retries"],
        retry_backoff_seconds=policy["retry_backoff_seconds"],
    )
    snapshot = save_raw_snapshot(
        raw_body, retrieved_at, city["city_id"].strip(), api["base_url"],
        build_request_params(api, city), raw_dir,
    )
    try:
        payload = validate_forecast(raw_body, api)
    except ValueError as error:
        raise ValueError(f"raw snapshot retained at {snapshot}; {error}") from error

    print(f"Saved: {snapshot}")
    print(f"Retrieved at: {retrieved_at.isoformat()}")
    print(f"Response bytes: {len(raw_body)}")
    print("Raw snapshot complete: _SUCCESS present.")
    print(f"Contract valid: {len(payload['hourly']['time'])} hourly positions.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--city", help="Configured city_id, e.g. kyiv")
    selection.add_argument("--all", action="store_true", help="Collect all active cities")
    parser.add_argument(
        "--raw-dir", type=Path,
        default=Path(os.environ.get("RAW_DATA_DIR", "data/raw")),
        help="Output directory; relative paths resolve from the repository root",
    )
    args = parser.parse_args(argv)

    try:
        config = validate_pipeline_config()
        cities = validate_city_config()
        if args.all:
            selected = [c for c in cities if parse_boolean(c["active"], city_id=c["city_id"])]
            if not selected:
                raise ValueError("No active cities configured")
        else:
            city = next((c for c in cities if c["city_id"].strip() == args.city), None)
            if city is None:
                raise ValueError(f"Unknown city_id: {args.city}")
            if not parse_boolean(city["active"], city_id=args.city):
                raise ValueError(f"City is inactive: {args.city}")
            selected = [city]

        api = config["open_meteo"]
        policy = config["ingestion"]
        raw_dir = args.raw_dir
        if not raw_dir.is_absolute():
            raw_dir = PROJECT_ROOT / raw_dir

    except (OSError, ValueError) as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        return 1

    succeeded = 0
    failed = []
    for city in selected:
        city_id = city["city_id"].strip()
        print(f"Collecting: {city_id}", flush=True)
        try:
            ingest_city(api, policy, city, raw_dir)
        except (OSError, ValueError) as error:
            failed.append(city_id)
            print(f"FAILED {city_id}: {error}", file=sys.stderr)
        else:
            succeeded += 1

    print(f"Summary: {succeeded} succeeded, {len(failed)} failed.")
    if failed:
        print(f"Failed cities: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
