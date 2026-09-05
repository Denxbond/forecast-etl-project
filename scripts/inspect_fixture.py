"""Inspect the saved Open-Meteo response without making a network request."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "open_meteo_kyiv_forecast.json"
METADATA_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "open_meteo_kyiv_forecast.metadata.json"
)
EXPECTED_HOURLY_FIELDS = (
    "time",
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as json_file:
        return json.load(json_file)


def main() -> int:
    try:
        response = load_json(FIXTURE_PATH)
        metadata = load_json(METADATA_PATH)
        hourly = response["hourly"]
        units = response["hourly_units"]

        missing_fields = set(EXPECTED_HOURLY_FIELDS) - set(hourly)
        if missing_fields:
            raise ValueError(f"missing hourly fields: {sorted(missing_fields)}")

        lengths = {field: len(hourly[field]) for field in EXPECTED_HOURLY_FIELDS}
        if len(set(lengths.values())) != 1:
            raise ValueError(f"hourly arrays have different lengths: {lengths}")

        row_count = lengths["time"]
        if row_count == 0:
            raise ValueError("hourly arrays are empty")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Fixture invalid: {error}", file=sys.stderr)
        return 1

    requested = metadata["requested_coordinates"]
    print(f"Fixture: {FIXTURE_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Captured at: {metadata['captured_at_utc']}")
    print(
        "Coordinates: "
        f"requested ({requested['latitude']}, {requested['longitude']}), "
        f"returned grid cell ({response['latitude']}, {response['longitude']})"
    )
    print(f"Hourly rows: {row_count}")
    print(f"Range: {hourly['time'][0]} to {hourly['time'][-1]}")
    print("Units:")
    for field in EXPECTED_HOURLY_FIELDS:
        print(f"  {field}: {units[field]}")

    print("First normalized row:")
    for field in EXPECTED_HOURLY_FIELDS:
        print(f"  {field}: {hourly[field][0]}")

    print(
        f"Fixture valid: {row_count} hourly rows from "
        f"{hourly['time'][0]} to {hourly['time'][-1]}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

