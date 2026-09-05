"""Collect and preserve one configured city's forecast."""

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", required=True, help="Configured city_id, e.g. kyiv")
    parser.add_argument(
        "--raw-dir", type=Path,
        default=Path(os.environ.get("RAW_DATA_DIR", "data/raw")),
        help="Output directory; relative paths resolve from the repository root",
    )
    args = parser.parse_args(argv)

    try:
        config = validate_pipeline_config()
        cities = validate_city_config()
        city = next((c for c in cities if c["city_id"].strip() == args.city), None)
        if city is None:
            raise ValueError(f"Unknown city_id: {args.city}")
        if not parse_boolean(city["active"], city_id=args.city):
            raise ValueError(f"City is inactive: {args.city}")

        api = config["open_meteo"]
        policy = config["ingestion"]
        raw_dir = args.raw_dir
        if not raw_dir.is_absolute():
            raw_dir = PROJECT_ROOT / raw_dir

        raw_body, retrieved_at = fetch_forecast(
            api, city, policy["request_timeout_seconds"],
            max_retries=policy["max_retries"],
            retry_backoff_seconds=policy["retry_backoff_seconds"],
        )
        snapshot = save_raw_snapshot(
            raw_body, retrieved_at, args.city, api["base_url"],
            build_request_params(api, city), raw_dir,
        )
        try:
            payload = validate_forecast(raw_body, api)
        except ValueError as error:
            raise ValueError(f"raw snapshot retained at {snapshot}; {error}") from error
    except (OSError, ValueError) as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        return 1

    print(f"Saved: {snapshot}")
    print(f"Retrieved at: {retrieved_at.isoformat()}")
    print(f"Response bytes: {len(raw_body)}")
    print("Raw snapshot complete: _SUCCESS present.")
    print(f"Contract valid: {len(payload['hourly']['time'])} hourly positions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
