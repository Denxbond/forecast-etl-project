"""Exercise the real request code with a simulated HTTP boundary."""

import ssl
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from weather_pipeline.client import fetch_forecast
from weather_pipeline.config import validate_city_config, validate_pipeline_config


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.api = validate_pipeline_config()["open_meteo"]
        self.city = next(c for c in validate_city_config() if c["city_id"] == "kyiv")
        self.response = MagicMock()
        self.response.__enter__.return_value = self.response
        self.body = b'{ "example": null }\n'
        self.response.read.return_value = self.body

    def test_request_parameters_timeout_bytes_and_retrieval_order(self):
        retrieved_at = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        events = []

        def read():
            events.append("body_read")
            return self.body

        def now(tz):
            self.assertEqual(tz, timezone.utc)
            events.append("timestamp")
            return retrieved_at

        self.response.read.side_effect = read
        with patch("weather_pipeline.client.urlopen", return_value=self.response) as open_url, \
             patch("weather_pipeline.client.datetime") as clock:
            clock.now.side_effect = now
            result = fetch_forecast(self.api, self.city, 12.5)

        url = urlsplit(open_url.call_args.args[0])
        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", self.api["base_url"])
        self.assertEqual(parse_qs(url.query), {
            "latitude": ["50.4501"], "longitude": ["30.5234"],
            "hourly": ["temperature_2m,precipitation,wind_speed_10m,weather_code"],
            "forecast_days": ["7"], "timezone": ["UTC"], "timeformat": ["iso8601"],
            "temperature_unit": ["celsius"], "precipitation_unit": ["mm"],
            "wind_speed_unit": ["kmh"],
        })
        self.assertEqual(open_url.call_args.kwargs, {"timeout": 12.5})
        self.assertEqual(result, (self.body, retrieved_at))
        self.assertEqual(events, ["body_read", "timestamp"])
        self.response.__exit__.assert_called_once_with(None, None, None)

    def test_wrapped_temporary_network_errors_retry(self):
        for reason in (TimeoutError("timeout"), ConnectionResetError("reset")):
            with self.subTest(reason=reason), \
                 patch("weather_pipeline.client.urlopen", side_effect=[
                     URLError(reason), self.response,
                 ]) as open_url, patch("weather_pipeline.client.sleep") as sleep:
                body, _ = fetch_forecast(self.api, self.city, 30, max_retries=3)
                self.assertEqual(body, self.body)
                self.assertEqual(open_url.call_count, 2)
                sleep.assert_called_once_with(2)

    def test_certificate_error_fails_without_retrying(self):
        error = URLError(ssl.SSLCertVerificationError("certificate rejected"))
        with patch("weather_pipeline.client.urlopen", side_effect=error) as open_url, \
             patch("weather_pipeline.client.sleep") as sleep:
            with self.assertRaises(URLError) as raised:
                fetch_forecast(self.api, self.city, 30, max_retries=3)
            self.assertIs(raised.exception, error)
            open_url.assert_called_once()
            sleep.assert_not_called()

    def test_body_read_failure_exits_response_before_retry(self):
        failed_response = MagicMock()
        failed_response.__enter__.return_value = failed_response
        error = TimeoutError("read timed out")
        failed_response.read.side_effect = error
        with patch("weather_pipeline.client.urlopen", side_effect=[
            failed_response, self.response,
        ]) as open_url, patch("weather_pipeline.client.sleep"):
            body, _ = fetch_forecast(self.api, self.city, 30, max_retries=1)
        self.assertEqual(body, self.body)
        self.assertEqual(open_url.call_count, 2)
        failed_response.__exit__.assert_called_once()
        self.assertIs(failed_response.__exit__.call_args.args[1], error)
