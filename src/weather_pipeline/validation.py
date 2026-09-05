"""Validate raw forecasts before normalization, without modifying them."""

import json
import math
from datetime import datetime, timedelta


EXPECTED_UNITS = {
    "time": "iso8601",
    "temperature_2m": "°C",
    "precipitation": "mm",
    "wind_speed_10m": "km/h",
    "weather_code": "wmo code",
}


def validate_forecast(raw_body: bytes, api: dict) -> dict:
    """Return parsed JSON or raise ValueError describing the contract failure.

    Null measurements are allowed and must remain null during normalization.
    The configured UTC daily window must contain forecast_days * 24 hours.
    """
    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise ValueError("response must be a JSON object")
    if payload.get("error"):
        raise ValueError(f"API error response: {payload.get('reason', 'unknown')}")
    offset = payload.get("utc_offset_seconds")
    if type(offset) not in (int, float) or offset != 0:
        raise ValueError("utc_offset_seconds must be zero")

    for field, limit in (("latitude", 90), ("longitude", 180)):
        value = payload.get(field)
        if type(value) not in (int, float) or not -limit <= value <= limit:
            raise ValueError(f"{field} must be a valid grid coordinate")

    hourly = payload.get("hourly")
    units = payload.get("hourly_units")
    if not isinstance(hourly, dict) or not isinstance(units, dict):
        raise ValueError("hourly and hourly_units must be JSON objects")

    fields = ["time", *api["hourly_variables"]]
    for field in fields:
        if not isinstance(hourly.get(field), list):
            raise ValueError(f"hourly.{field} must be an array")
        if units.get(field) != EXPECTED_UNITS[field]:
            raise ValueError(f"hourly_units.{field}: expected {EXPECTED_UNITS[field]!r}")

    lengths = {field: len(hourly[field]) for field in fields}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"hourly arrays have different lengths: {lengths}")
    expected_count = api["forecast_days"] * 24
    if lengths["time"] != expected_count:
        raise ValueError(f"expected {expected_count} hourly positions, got {lengths['time']}")

    previous = None
    for index, value in enumerate(hourly["time"]):
        try:
            timestamp = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except (TypeError, ValueError) as error:
            raise ValueError(f"hourly.time[{index}] must be YYYY-MM-DDTHH:MM") from error
        if timestamp.strftime("%Y-%m-%dT%H:%M") != value or timestamp.minute != 0:
            raise ValueError(f"hourly.time[{index}] must be an exact hour")
        if previous is None and timestamp.hour != 0:
            raise ValueError("forecast window must start at midnight UTC")
        if previous is not None and timestamp - previous != timedelta(hours=1):
            raise ValueError(f"hourly.time[{index}] must follow the previous hour")
        previous = timestamp

    for field in api["hourly_variables"]:
        for index, value in enumerate(hourly[field]):
            if value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"hourly.{field}[{index}] must be finite numeric or null")
            if field == "weather_code" and type(value) is not int:
                raise ValueError(f"hourly.weather_code[{index}] must be integer or null")
    return payload
