"""Exercise the response contract using altered copies of the stored fixture."""

import json
import unittest

from weather_pipeline.config import PROJECT_ROOT, validate_pipeline_config
from weather_pipeline.validation import validate_forecast


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.body = (PROJECT_ROOT / "tests/fixtures/open_meteo_kyiv_forecast.json").read_bytes()
        self.payload = json.loads(self.body)
        self.api = validate_pipeline_config()["open_meteo"]

    def validate(self):
        return validate_forecast(json.dumps(self.payload).encode(), self.api)

    def test_fixture_and_null_measurement(self):
        self.assertEqual(len(validate_forecast(self.body, self.api)["hourly"]["time"]), 168)
        self.payload["hourly"]["temperature_2m"][0] = None
        self.assertIsNone(self.validate()["hourly"]["temperature_2m"][0])

    def test_mismatched_array_is_rejected(self):
        self.payload["hourly"]["precipitation"].pop()
        with self.assertRaisesRegex(ValueError, "different lengths"):
            self.validate()

    def test_truncated_window_is_rejected(self):
        for values in self.payload["hourly"].values():
            values.pop()
        with self.assertRaisesRegex(ValueError, "expected 168"):
            self.validate()

    def test_unit_change_is_rejected(self):
        self.payload["hourly_units"]["temperature_2m"] = "°F"
        with self.assertRaisesRegex(ValueError, "hourly_units.temperature_2m"):
            self.validate()

    def test_nonzero_offset_is_rejected(self):
        self.payload["utc_offset_seconds"] = 3600
        with self.assertRaisesRegex(ValueError, "offset"):
            self.validate()

    def test_duplicate_hour_is_rejected(self):
        self.payload["hourly"]["time"][1] = self.payload["hourly"]["time"][0]
        with self.assertRaisesRegex(ValueError, "previous hour"):
            self.validate()

    def test_invalid_measurements_are_rejected(self):
        for value in (True, "18.3", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.payload["hourly"]["temperature_2m"][0] = value
                with self.assertRaisesRegex(ValueError, "finite numeric"):
                    self.validate()

    def test_invalid_structure_is_rejected(self):
        for body in (b"not JSON", b"[]", b"{}", b'{"error": true}'):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    validate_forecast(body, self.api)
