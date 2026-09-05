"""Verify CLI wiring with a stored response and temporary raw storage."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from weather_pipeline.config import PROJECT_ROOT, validate_city_config, validate_pipeline_config
from weather_pipeline.ingest import main


class IngestTests(unittest.TestCase):
    def test_batch_success_and_partial_failures(self):
        body = (PROJECT_ROOT / "tests/fixtures/open_meteo_kyiv_forecast.json").read_bytes()
        cities = validate_city_config()
        for failure in (None, "network", "contract"):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                def fetch(api, city, timeout, **kwargs):
                    if city["city_id"] == "kyiv" and failure == "network":
                        raise TimeoutError("simulated timeout")
                    response = b"invalid JSON" if (
                        city["city_id"] == "kyiv" and failure == "contract"
                    ) else body
                    return response, datetime.now(timezone.utc)

                with patch("weather_pipeline.ingest.fetch_forecast", side_effect=fetch) as request, \
                     redirect_stdout(io.StringIO()) as output, \
                     redirect_stderr(io.StringIO()):
                    status = main(["--all", "--raw-dir", directory])
                self.assertEqual(status, 1 if failure else 0)
                self.assertEqual(request.call_count, 10)
                self.assertIn("9 succeeded, 1 failed" if failure else
                              "10 succeeded, 0 failed", output.getvalue())
                for city in cities:
                    city_dir = Path(directory) / city["city_id"]
                    if city["city_id"] == "kyiv" and failure == "network":
                        self.assertFalse(city_dir.exists())
                        continue
                    snapshot = next(city_dir.iterdir())
                    self.assertTrue((snapshot / "_SUCCESS").is_file())
                    metadata = json.loads((snapshot / "metadata.json").read_text())
                    self.assertEqual(metadata["city_id"], city["city_id"])

    def test_batch_skips_inactive_and_rejects_empty_selection(self):
        for active_count in (0, 1):
            cities = validate_city_config()
            for index, city in enumerate(cities):
                city["active"] = "true" if index < active_count else "false"
            with self.subTest(active_count=active_count), \
                 patch("weather_pipeline.ingest.validate_city_config", return_value=cities), \
                 patch("weather_pipeline.ingest.ingest_city") as ingest, \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--all"]), 0 if active_count else 1)
                self.assertEqual(ingest.call_count, active_count)

    def test_city_and_all_are_mutually_exclusive(self):
        with redirect_stderr(io.StringIO()), \
             patch("weather_pipeline.ingest.fetch_forecast") as fetch:
            with self.assertRaises(SystemExit) as error:
                main(["--city", "kyiv", "--all"])
            self.assertEqual(error.exception.code, 2)
            fetch.assert_not_called()

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
