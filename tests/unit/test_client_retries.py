"""Offline checks for retry policy; no requests or real sleeping."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError

from weather_pipeline.client import _retry_after_seconds, fetch_forecast


class RetryTests(unittest.TestCase):
    def test_retry_after_formats(self):
        now = datetime(2026, 9, 5, 10, tzinfo=timezone.utc)
        cases = [
            ("12", 12),
            ("Sat, 05 Sep 2026 10:00:30 GMT", 30),
            ("Sat, 05 Sep 2026 09:00:00 GMT", 0),
            (None, None),
            ("invalid", None),
            ("-1", None),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(_retry_after_seconds(value, now), expected)

    def test_http_recovery_and_delay(self):
        for status, header, delay in [
            (429, "12", 12), (429, "0", 2), (429, "invalid", 2),
            (500, None, 2), (502, None, 2),
            (503, "12", 12), (504, None, 2),
        ]:
            with self.subTest(status=status, header=header):
                error = HTTPError("https://example.invalid", status, "error",
                                  {"Retry-After": header} if header else {}, None)
                expected = (b"{}", datetime.now(timezone.utc))
                with patch("weather_pipeline.client._fetch_once",
                           side_effect=[error, expected]) as request, \
                     patch("weather_pipeline.client.sleep") as sleep:
                    self.assertEqual(fetch_forecast({}, {}, 30, max_retries=3),
                                     expected)
                    self.assertEqual(request.call_count, 2)
                    sleep.assert_called_once_with(delay)

    def test_bad_request_is_not_retried(self):
        error = HTTPError("https://example.invalid", 400, "bad request", {}, None)
        with patch("weather_pipeline.client._fetch_once", side_effect=error) as request, \
             patch("weather_pipeline.client.sleep") as sleep:
            with self.assertRaises(HTTPError):
                fetch_forecast({}, {}, 30, max_retries=3)
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()

    def test_retry_limit(self):
        errors = [TimeoutError("timeout"),
                  HTTPError("https://example.invalid", 429, "limited", {}, None)]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                with patch("weather_pipeline.client._fetch_once", side_effect=error) as request, \
                     patch("weather_pipeline.client.sleep") as sleep:
                    with self.assertRaises(type(error)):
                        fetch_forecast({}, {}, 30, max_retries=3)
                    self.assertEqual(request.call_count, 4)
                    self.assertEqual([call.args[0] for call in sleep.call_args_list],
                                     [2, 4, 8])
