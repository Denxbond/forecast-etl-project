"""Convert validated raw response arrays into hourly forecast records."""

from datetime import datetime, timezone

from weather_pipeline.validation import validate_forecast


def normalize_forecast(
    raw_body: bytes,
    api: dict,
    city_id: str,
    retrieved_at: datetime,
) -> list[dict]:
    """Validate first, then preserve one row per hour and retrieval snapshot."""
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    retrieved_at = retrieved_at.astimezone(timezone.utc)
    payload = validate_forecast(raw_body, api)
    hourly = payload["hourly"]

    rows = []
    for index, time_string in enumerate(hourly["time"]):
        # Validation established that these offset-free strings represent UTC.
        forecast_at = datetime.fromisoformat(time_string).replace(tzinfo=timezone.utc)
        row = {
            "city_id": city_id,
            "retrieved_at": retrieved_at,
            "forecast_at": forecast_at,
        }
        for field in api["hourly_variables"]:
            row[field] = hourly[field][index]
        rows.append(row)
    return rows
