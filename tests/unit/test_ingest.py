"""Verify CLI wiring with a stored response and temporary raw storage."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from weather_pipeline.config import PROJECT_ROOT, validate_pipeline_config
from weather_pipeline.ingest import main


class IngestTests(unittest.TestCase):
    def test_contract_failure_retains_raw_snapshot(self):
        with TemporaryDirectory() as directory:
            with patch("weather_pipeline.ingest.fetch_forecast",
                       return_value=(b"not JSON", datetime.now(timezone.utc))), \
                 redirect_stderr(io.StringIO()) as output:
                self.assertEqual(main(["--city", "kyiv", "--raw-dir", directory]), 1)
            snapshot = next((Path(directory) / "kyiv").iterdir())
            self.assertEqual((snapshot / "response.json").read_bytes(), b"not JSON")
            self.assertTrue((snapshot / "_SUCCESS").exists())
            self.assertIn(str(snapshot), output.getvalue())

    def test_saves_original_response_and_passes_retry_policy(self):
        body = (PROJECT_ROOT / "tests/fixtures/open_meteo_kyiv_forecast.json").read_bytes()
        retrieved_at = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        with TemporaryDirectory() as directory:
            with patch("weather_pipeline.ingest.fetch_forecast",
                       return_value=(body, retrieved_at)) as fetch, \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--city", "kyiv", "--raw-dir", directory]), 0)
            snapshot = next((Path(directory) / "kyiv").iterdir())
            self.assertEqual((snapshot / "response.json").read_bytes(), body)
            metadata = json.loads((snapshot / "metadata.json").read_text())
            self.assertEqual(metadata["retrieved_at"], retrieved_at.isoformat())
            self.assertEqual(metadata["city_id"], "kyiv")
            self.assertEqual(metadata["request_params"]["latitude"], "50.4501")
            self.assertTrue((snapshot / "_SUCCESS").is_file())
            policy = validate_pipeline_config()["ingestion"]
            self.assertEqual(fetch.call_args.args[2], policy["request_timeout_seconds"])
            self.assertEqual(fetch.call_args.kwargs, {
                "max_retries": policy["max_retries"],
                "retry_backoff_seconds": policy["retry_backoff_seconds"],
            })

    def test_unknown_city_fails_before_fetch(self):
        with patch("weather_pipeline.ingest.fetch_forecast") as fetch, \
             redirect_stderr(io.StringIO()) as output:
            self.assertEqual(main(["--city", "unknown"]), 1)
            fetch.assert_not_called()
            self.assertIn("Unknown city_id", output.getvalue())

    def test_fetch_failure_does_not_save(self):
        with patch("weather_pipeline.ingest.fetch_forecast",
                   side_effect=TimeoutError("timed out")), \
             patch("weather_pipeline.ingest.save_raw_snapshot") as save, \
             redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--city", "kyiv"]), 1)
            save.assert_not_called()
