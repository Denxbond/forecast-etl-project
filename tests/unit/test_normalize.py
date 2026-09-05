"""Check normalization against the captured response and retrieval metadata."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from weather_pipeline.config import PROJECT_ROOT, validate_pipeline_config
from weather_pipeline.normalize import normalize_forecast


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        fixtures = PROJECT_ROOT / "tests/fixtures"
        self.body = (fixtures / "open_meteo_kyiv_forecast.json").read_bytes()
        metadata = json.loads((fixtures / "open_meteo_kyiv_forecast.metadata.json").read_text())
        self.retrieved_at = datetime.fromisoformat(metadata["captured_at_utc"])
        self.api = validate_pipeline_config()["open_meteo"]

    def test_all_positions_and_snapshot_identity_are_preserved(self):
        rows = normalize_forecast(self.body, self.api, "kyiv", self.retrieved_at)
        hourly = json.loads(self.body)["hourly"]
        self.assertEqual(len(rows), 168)
        for index, row in enumerate(rows):
            self.assertEqual(row["city_id"], "kyiv")
            self.assertEqual(row["retrieved_at"], self.retrieved_at)
            self.assertEqual(row["forecast_at"].tzinfo, timezone.utc)
            self.assertEqual(row["forecast_at"].strftime("%Y-%m-%dT%H:%M"), hourly["time"][index])
            for field in self.api["hourly_variables"]:
                self.assertEqual(row[field], hourly[field][index])
        self.assertLess(rows[0]["forecast_at"], rows[0]["retrieved_at"])

    def test_null_remains_none(self):
        payload = json.loads(self.body)
        payload["hourly"]["temperature_2m"][0] = None
        rows = normalize_forecast(json.dumps(payload).encode(), self.api, "kyiv", self.retrieved_at)
        self.assertIsNone(rows[0]["temperature_2m"])

    def test_bad_arrays_are_rejected_before_normalization(self):
        payload = json.loads(self.body)
        payload["hourly"]["precipitation"].pop()
        with self.assertRaisesRegex(ValueError, "different lengths"):
            normalize_forecast(json.dumps(payload).encode(), self.api, "kyiv", self.retrieved_at)

    def test_retrieval_timezone_is_required_and_converted(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            normalize_forecast(self.body, self.api, "kyiv", self.retrieved_at.replace(tzinfo=None))
        local_time = self.retrieved_at.astimezone(timezone(timedelta(hours=3)))
        rows = normalize_forecast(self.body, self.api, "kyiv", local_time)
        self.assertEqual(rows[0]["retrieved_at"], self.retrieved_at)
        self.assertEqual(rows[0]["retrieved_at"].tzinfo, timezone.utc)

    def test_replay_is_stable_but_new_retrieval_has_a_new_identity(self):
        first = normalize_forecast(self.body, self.api, "kyiv", self.retrieved_at)
        self.assertEqual(first, normalize_forecast(self.body, self.api, "kyiv", self.retrieved_at))
        later = normalize_forecast(self.body, self.api, "kyiv", self.retrieved_at + timedelta(hours=6))
        self.assertEqual(first[0]["forecast_at"], later[0]["forecast_at"])
        self.assertNotEqual(first[0]["retrieved_at"], later[0]["retrieved_at"])
