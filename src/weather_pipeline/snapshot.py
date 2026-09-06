"""Read and prepare a completed raw snapshot without network or database access."""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from weather_pipeline.config import CITY_ID_PATTERN, EXPECTED_VARIABLES
from weather_pipeline.normalize import normalize_forecast


def prepare_snapshot(directory: Path) -> dict:
    """Validate saved metadata and return snapshot fields plus normalized rows."""
    directory = directory.resolve()
    if not (directory / "_SUCCESS").is_file():
        raise ValueError("snapshot has no _SUCCESS completion marker")
    metadata = json.loads((directory / "metadata.json").read_bytes())
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")

    city_id = metadata.get("city_id")
    if not isinstance(city_id, str) or not CITY_ID_PATTERN.fullmatch(city_id):
        raise ValueError("metadata.city_id must be a valid stable city identifier")
    value = metadata.get("retrieved_at")
    if not isinstance(value, str):
        raise ValueError("metadata.retrieved_at must be an ISO timestamp")
    retrieved_at = datetime.fromisoformat(value)
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("metadata.retrieved_at must include a timezone")
    retrieved_at = retrieved_at.astimezone(timezone.utc)
    if metadata.get("endpoint") != "https://api.open-meteo.com/v1/forecast":
        raise ValueError("metadata.endpoint must identify the Forecast API")

    params = metadata.get("request_params")
    if not isinstance(params, dict):
        raise ValueError("metadata.request_params must be a JSON object")
    for field, expected in (
        ("timezone", "UTC"), ("timeformat", "iso8601"),
        ("temperature_unit", "celsius"), ("precipitation_unit", "mm"),
        ("wind_speed_unit", "kmh"),
    ):
        if params.get(field) != expected:
            raise ValueError(f"request_params.{field} must be {expected}")
    days = params.get("forecast_days")
    if type(days) is not int or not 1 <= days <= 16:
        raise ValueError("request_params.forecast_days must be an integer from 1 to 16")
    hourly = params.get("hourly")
    variables = hourly.split(",") if isinstance(hourly, str) else []
    if set(variables) != EXPECTED_VARIABLES or len(variables) != len(EXPECTED_VARIABLES):
        raise ValueError("request_params.hourly must contain the four supported fields once")
    for field, limit in (("latitude", 90), ("longitude", 180)):
        value = params.get(field)
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError(f"request_params.{field} must be a coordinate")
        try:
            coordinate = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"request_params.{field} must be a coordinate") from error
        if not math.isfinite(coordinate) or not -limit <= coordinate <= limit:
            raise ValueError(f"request_params.{field} is outside its valid range")

    # Historical requests, not today's pipeline.toml, define replay coverage.
    api = {**params, "hourly_variables": variables}
    response_path = directory / "response.json"
    raw_body = response_path.read_bytes()
    rows = normalize_forecast(raw_body, api, city_id, retrieved_at)
    payload = json.loads(raw_body)
    return {
        "snapshot": {
            "city_id": city_id,
            "retrieved_at": retrieved_at,
            "raw_response_path": str(response_path),
            "request_params": params,
            "grid_latitude": payload["latitude"],
            "grid_longitude": payload["longitude"],
        },
        "hourly_rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Completed snapshot directory")
    args = parser.parse_args(argv)
    try:
        prepared = prepare_snapshot(args.directory)
    except (OSError, ValueError) as error:
        print(f"Snapshot invalid: {error}", file=sys.stderr)
        return 1
    snapshot = prepared["snapshot"]
    rows = prepared["hourly_rows"]
    print(f"City: {snapshot['city_id']}")
    print(f"Retrieved at: {snapshot['retrieved_at'].isoformat()}")
    print(f"Prepared: 1 snapshot, {len(rows)} hourly records.")
    print(f"Forecast range: {rows[0]['forecast_at'].isoformat()} to {rows[-1]['forecast_at'].isoformat()}")
    print("Preview only: no database writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
