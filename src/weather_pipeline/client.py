from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode
from urllib.request import urlopen
from time import sleep
from urllib.error import HTTPError, URLError

def build_request_params(api: dict, city: dict) -> dict:
    """Build request parameters from validated configuration."""
    return {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": ",".join(api["hourly_variables"]),
        "forecast_days": api["forecast_days"],
        "timezone": api["timezone"],
        "timeformat": api["timeformat"],
        "temperature_unit": api["temperature_unit"],
        "precipitation_unit": api["precipitation_unit"],
        "wind_speed_unit": api["wind_speed_unit"],
    }

def _fetch_once(
    api: dict,
    city: dict,
    timeout_seconds: float,
) -> tuple[bytes, datetime]:
    """Fetch one response and record when its body finishes downloading."""
    params = build_request_params(api, city)
    url = f"{api['base_url']}?{urlencode(params)}"

    with urlopen(url, timeout=timeout_seconds) as response:
        raw_body = response.read()
        retrieved_at = datetime.now(timezone.utc)

    return raw_body, retrieved_at

def _retry_after_seconds(value: str | None, now: datetime) -> float | None:
    """Parse Retry-After seconds or an HTTP date; ignore invalid values."""
    if value is None:
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdigit():
            return float(int(value))
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            return None
        return max(0.0, (retry_at - now).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def fetch_forecast(
    api: dict,
    city: dict,
    timeout_seconds: float,
    *,
    max_retries: int = 0,
    retry_backoff_seconds: float = 2,
) -> tuple[bytes, datetime]:
    """Fetch a forecast, retrying selected temporary failures."""
    if max_retries < 0 or retry_backoff_seconds < 0:
        raise ValueError("Retry count and backoff cannot be negative")

    for attempt in range(max_retries + 1):
        delay = retry_backoff_seconds * (2 ** attempt)
        try:
            return _fetch_once(api, city, timeout_seconds)
        except HTTPError as error:
            error.close()
            if error.code not in {429, 500, 502, 503, 504}:
                raise
            if attempt == max_retries:
                raise
            retry_after = _retry_after_seconds(
                error.headers.get("Retry-After") if error.headers else None,
                datetime.now(timezone.utc),
            )
            if retry_after is not None:
                delay = max(delay, retry_after)
        except URLError as error:
            if not isinstance(error.reason, (TimeoutError, ConnectionError)):
                raise
            if attempt == max_retries:
                raise
        except (TimeoutError, ConnectionError):
            if attempt == max_retries:
                raise

        sleep(delay)
