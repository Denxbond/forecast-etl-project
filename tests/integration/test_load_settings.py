"""Offline settings checks; requires warehouse dependencies, not PostgreSQL."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from weather_pipeline.load import connection_settings


class ConnectionSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.values = {
            "WAREHOUSE_HOST": "localhost",
            "WAREHOUSE_PORT": "5433",
            "WAREHOUSE_DATABASE": "test_weather",
            "WAREHOUSE_USER": "test_user",
            "WAREHOUSE_PASSWORD": "test_password",
        }
        self.write_env(self.values)
        self.enterContext(patch("weather_pipeline.load.PROJECT_ROOT", self.root))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def write_env(self, values):
        (self.root / ".env").write_text(
            "".join(f"{key}={value}\n" for key, value in values.items())
        )

    def test_dotenv_settings_map_to_connection_arguments(self):
        self.assertEqual(connection_settings(), {
            "host": "localhost", "port": "5433", "dbname": "test_weather",
            "user": "test_user", "password": "test_password",
            "connect_timeout": 10, "options": "-c timezone=UTC",
        })

    def test_exported_values_override_dotenv(self):
        with patch.dict(os.environ, {"WAREHOUSE_PORT": "6543"}):
            settings = connection_settings()
        self.assertEqual(settings["port"], "6543")
        self.assertEqual(settings["dbname"], "test_weather")

    def test_missing_or_empty_required_values_fail(self):
        for field in self.values:
            for value in (None, ""):
                values = self.values.copy()
                if value is None:
                    del values[field]
                else:
                    values[field] = value
                self.write_env(values)
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError) as error:
                        connection_settings()
                    self.assertIn(field, str(error.exception))
                    self.assertNotIn("test_password", str(error.exception))

    def test_empty_export_does_not_fall_back_to_dotenv(self):
        with patch.dict(os.environ, {"WAREHOUSE_PASSWORD": ""}):
            with self.assertRaisesRegex(ValueError, "WAREHOUSE_PASSWORD"):
                connection_settings()

    def test_environment_only_setup_needs_no_dotenv_file(self):
        (self.root / ".env").unlink()
        with patch.dict(os.environ, self.values):
            self.assertEqual(connection_settings()["dbname"], "test_weather")

    def test_password_interpolation_is_disabled(self):
        self.write_env({**self.values, "WAREHOUSE_PASSWORD": "literal${VARIABLE}"})
        with patch.dict(os.environ, {"VARIABLE": "expanded"}):
            self.assertEqual(connection_settings()["password"], "literal${VARIABLE}")
