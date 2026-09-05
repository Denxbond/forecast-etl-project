"""Validate project configuration using the shared application validators."""

import sys
import tomllib
from pathlib import Path

# Keep this script runnable directly without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from weather_pipeline.config import (
    parse_boolean,
    validate_city_config,
    validate_pipeline_config,
)


def main() -> int:
    try:
        pipeline = validate_pipeline_config()
        cities = validate_city_config()
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"Configuration invalid: {error}", file=sys.stderr)
        return 1

    active_count = sum(
        parse_boolean(city["active"], city_id=city["city_id"])
        for city in cities
    )
    api = pipeline["open_meteo"]
    print(
        "Configuration valid: "
        f"{active_count} active cities, "
        f"{len(api['hourly_variables'])} hourly variables, "
        f"{api['forecast_days']} forecast days."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
