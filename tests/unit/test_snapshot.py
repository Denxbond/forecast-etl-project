"""Check replay preparation using temporary completed snapshots."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from weather_pipeline.client import build_request_params
from weather_pipeline.config import PROJECT_ROOT, validate_city_config, validate_pipeline_config
from weather_pipeline.raw import save_raw_snapshot
from weather_pipeline.snapshot import prepare_snapshot


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.body = (PROJECT_ROOT / "tests/fixtures/open_meteo_kyiv_forecast.json").read_bytes()
        api = validate_pipeline_config()["open_meteo"]
        city = next(c for c in validate_city_config() if c["city_id"] == "kyiv")
        self.retrieved_at = datetime(2026, 9, 5, 9, 25, 40, tzinfo=timezone.utc)
        self.path = save_raw_snapshot(self.body, self.retrieved_at, "kyiv", api["base_url"],
                                      build_request_params(api, city), Path(self.temporary.name))

    def test_preparation_preserves_snapshot_and_source_files(self):
        before = {p.name: p.read_bytes() for p in self.path.iterdir()}
        result = prepare_snapshot(self.path)
        self.assertEqual(len(result["hourly_rows"]), 168)
        self.assertEqual(result["snapshot"]["retrieved_at"], self.retrieved_at)
        self.assertEqual(result["snapshot"]["grid_latitude"], 50.4375)
        self.assertEqual(result, prepare_snapshot(self.path))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.path.iterdir()})

    def test_incomplete_directory_is_rejected(self):
        (self.path / "_SUCCESS").unlink()
        with self.assertRaisesRegex(ValueError, "completion marker"):
            prepare_snapshot(self.path)

    def test_invalid_metadata_is_rejected(self):
        original = json.loads((self.path / "metadata.json").read_bytes())
        cases = [[], {**original, "retrieved_at": "2026-09-05T09:25:40"},
                 {**original, "city_id": "../kyiv"},
                 {**original, "request_params": {}},
                 {**original, "endpoint": "https://example.invalid"}]
        for metadata in cases:
            with self.subTest(metadata=metadata):
                (self.path / "metadata.json").write_text(json.dumps(metadata))
                with self.assertRaises(ValueError):
                    prepare_snapshot(self.path)

    def test_saved_request_defines_horizon(self):
        metadata = json.loads((self.path / "metadata.json").read_bytes())
        metadata["request_params"]["forecast_days"] = 1
        (self.path / "metadata.json").write_text(json.dumps(metadata))
        payload = json.loads(self.body)
        payload["hourly"] = {key: values[:24] for key, values in payload["hourly"].items()}
        (self.path / "response.json").write_text(json.dumps(payload))
        self.assertEqual(len(prepare_snapshot(self.path)["hourly_rows"]), 24)

    def test_completion_marker_does_not_bypass_response_validation(self):
        (self.path / "response.json").write_bytes(b"invalid JSON")
        with self.assertRaises(ValueError):
            prepare_snapshot(self.path)
