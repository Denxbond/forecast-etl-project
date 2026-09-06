"""Verify raw preservation using temporary files and simulated write failures."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from weather_pipeline.raw import save_raw_snapshot


class RawTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.retrieved_at = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        # Deliberate whitespace verifies byte preservation, not just JSON equality.
        self.body = b'{ "temperature": null }\n'
        self.params = {"latitude": "50.4501", "longitude": "30.5234"}

    def save(self, body=None):
        return save_raw_snapshot(
            raw_body=self.body if body is None else body,
            retrieved_at=self.retrieved_at,
            city_id="kyiv",
            endpoint="https://api.open-meteo.com/v1/forecast",
            request_params=self.params,
            raw_dir=self.root,
        )

    def test_success_preserves_bytes_metadata_and_completion_marker(self):
        directory = self.save()
        self.assertEqual((directory / "response.json").read_bytes(), self.body)
        metadata = json.loads((directory / "metadata.json").read_bytes())
        self.assertEqual(metadata, {
            "city_id": "kyiv",
            "retrieved_at": self.retrieved_at.isoformat(),
            "endpoint": "https://api.open-meteo.com/v1/forecast",
            "request_params": self.params,
        })
        self.assertEqual((directory / "_SUCCESS").read_bytes(), b"")

    def test_duplicate_save_preserves_every_original_file(self):
        directory = self.save()
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        with self.assertRaises(FileExistsError):
            self.save(b'{"overwrite_attempt": true}')
        after = {path.name: path.read_bytes() for path in directory.iterdir()}
        self.assertEqual(after, before)

    def test_interrupted_writes_never_mark_snapshot_complete(self):
        original_open = Path.open
        for filename in ("response.json", "metadata.json"):
            with self.subTest(filename=filename), TemporaryDirectory() as temporary:
                self.root = Path(temporary)

                def interrupt_write(path, *args, **kwargs):
                    if path.name == filename:
                        # Leave a partial file, as an interrupted write could.
                        with original_open(path, "wb") as file:
                            file.write(b"partial")
                        raise OSError("Simulated interrupted write")
                    return original_open(path, *args, **kwargs)

                with patch.object(Path, "open", interrupt_write):
                    with self.assertRaisesRegex(OSError, "Simulated interrupted write"):
                        self.save()

                directory = next((self.root / "kyiv").iterdir())
                self.assertFalse((directory / "_SUCCESS").exists())
                self.assertEqual((directory / filename).read_bytes(), b"partial")
                if filename == "metadata.json":
                    self.assertEqual((directory / "response.json").read_bytes(), self.body)
                # An incomplete directory must not be silently overwritten either.
                with self.assertRaises(FileExistsError):
                    self.save()
