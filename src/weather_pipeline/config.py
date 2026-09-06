"""Load and validate shared pipeline and city configuration."""

from __future__ import annotations

import csv
import math
import re
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CONFIG = PROJECT_ROOT / "config" / "pipeline.toml"
CITY_CONFIG = PROJECT_ROOT / "config" / "cities.csv"

EXPECTED_VARIABLES = {
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
}
EXPECTED_CITY_COLUMNS = {
    "city_id",
    "city_name",
    "country_code",
    "latitude",
    "longitude",
    "timezone",
    "active",
}
CITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_pipeline_config() -> dict:
    with PIPELINE_CONFIG.open("rb") as config_file:
        config = tomllib.load(config_file)

    api = config.get("open_meteo", {})
    ingestion = config.get("ingestion", {})

    if api.get("base_url") != "https://api.open-meteo.com/v1/forecast":
        raise ValueError("open_meteo.base_url must use the Forecast API endpoint")

    variables = api.get("hourly_variables", [])
    if set(variables) != EXPECTED_VARIABLES or len(variables) != len(
        EXPECTED_VARIABLES
    ):
        raise ValueError(
            "open_meteo.hourly_variables must contain each expected variable once"
        )

    forecast_days = api.get("forecast_days")
    if type(forecast_days) is not int or not 1 <= forecast_days <= 16:
        raise ValueError("open_meteo.forecast_days must be an integer from 1 to 16")

    if api.get("timezone") != "UTC":
        raise ValueError("open_meteo.timezone must be UTC for warehouse consistency")
    if api.get("timeformat") != "iso8601":
        raise ValueError("open_meteo.timeformat must be iso8601")
    for field, expected in (
        ("temperature_unit", "celsius"),
        ("precipitation_unit", "mm"),
        ("wind_speed_unit", "kmh"),
    ):
        if api.get(field) != expected:
            raise ValueError(f"open_meteo.{field} must be {expected}")

    retries = ingestion.get("max_retries")
    if type(retries) is not int or retries < 0:
        raise ValueError("ingestion.max_retries must be a non-negative integer")
    for field in ("request_timeout_seconds", "retry_backoff_seconds"):
        value = ingestion.get(field)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"ingestion.{field} must be a finite number")
        if field == "request_timeout_seconds" and value <= 0:
            raise ValueError(f"ingestion.{field} must be positive")
        if field == "retry_backoff_seconds" and value < 0:
            raise ValueError(f"ingestion.{field} cannot be negative")

    return config


def parse_boolean(value: str, *, city_id: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{city_id}: active must be true or false")
    return normalized == "true"


def validate_city_config() -> list[dict[str, str]]:
    with CITY_CONFIG.open(newline="", encoding="utf-8") as config_file:
        reader = csv.DictReader(config_file)
        columns = reader.fieldnames or []
        if set(columns) != EXPECTED_CITY_COLUMNS or len(columns) != len(EXPECTED_CITY_COLUMNS):
            raise ValueError(
                "cities.csv columns do not match the expected configuration contract"
            )
        cities = list(reader)

    if not cities:
        raise ValueError("cities.csv must contain at least one city")

    seen_ids: set[str] = set()
    for row_number, city in enumerate(cities, start=2):
        if None in city or any(value is None for value in city.values()):
            raise ValueError(f"cities.csv row {row_number}: wrong number of columns")
        city_id = city["city_id"].strip()
        if not CITY_ID_PATTERN.fullmatch(city_id):
            raise ValueError(f"Invalid stable city_id: {city_id!r}")
        if city_id in seen_ids:
            raise ValueError(f"Duplicate city_id: {city_id}")
        seen_ids.add(city_id)

        country_code = city["country_code"].strip()
        if len(country_code) != 2 or not country_code.isupper():
            raise ValueError(f"{city_id}: country_code must be two uppercase letters")

        latitude = float(city["latitude"])
        longitude = float(city["longitude"])
        if not -90 <= latitude <= 90:
            raise ValueError(f"{city_id}: latitude is outside [-90, 90]")
        if not -180 <= longitude <= 180:
            raise ValueError(f"{city_id}: longitude is outside [-180, 180]")

        try:
            ZoneInfo(city["timezone"].strip())
        except ZoneInfoNotFoundError as error:
            raise ValueError(
                f"{city_id}: unknown IANA timezone {city['timezone']!r}"
            ) from error

        parse_boolean(city["active"], city_id=city_id)

    return cities
