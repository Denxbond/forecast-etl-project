"""Reject invalid numeric settings before starting ingestion."""

import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from weather_pipeline.config import (
    CITY_CONFIG, PIPELINE_CONFIG, validate_city_config, validate_pipeline_config,
)


class PipelineConfigTests(unittest.TestCase):
    def setUp(self):
        self.original = PIPELINE_CONFIG.read_text()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "pipeline.toml"

    def validate_setting(self, field, literal):
        replacement = "" if literal is None else f"{field} = {literal}"
        text, count = re.subn(rf"^{field} = .*", replacement, self.original, flags=re.MULTILINE)
        self.assertEqual(count, 1)
        self.path.write_text(text)
        with patch("weather_pipeline.config.PIPELINE_CONFIG", self.path):
            return validate_pipeline_config()

    def test_retries_require_a_nonnegative_integer(self):
        for literal in ("1.5", "true", "-1", '"3"', None):
            with self.subTest(literal=literal), self.assertRaisesRegex(ValueError, "max_retries"):
                self.validate_setting("max_retries", literal)

    def test_timeout_requires_a_positive_finite_number(self):
        for literal in ("0", "-1", "true", "inf", "nan", '"30"', None):
            with self.subTest(literal=literal), self.assertRaisesRegex(ValueError, "request_timeout_seconds"):
                self.validate_setting("request_timeout_seconds", literal)

    def test_backoff_requires_a_nonnegative_finite_number(self):
        for literal in ("-1", "true", "inf", "nan", '"2"', None):
            with self.subTest(literal=literal), self.assertRaisesRegex(ValueError, "retry_backoff_seconds"):
                self.validate_setting("retry_backoff_seconds", literal)

    def test_forecast_days_require_an_integer_in_range(self):
        for literal in ("true", "7.0", "0", "17", None):
            with self.subTest(literal=literal), self.assertRaisesRegex(ValueError, "forecast_days"):
                self.validate_setting("forecast_days", literal)

    def test_valid_boundaries_and_fractional_delays(self):
        for field, literal in (
            ("max_retries", "0"), ("retry_backoff_seconds", "0"),
            ("retry_backoff_seconds", "0.5"), ("request_timeout_seconds", "0.5"),
            ("forecast_days", "1"), ("forecast_days", "16"),
        ):
            with self.subTest(field=field, literal=literal):
                self.validate_setting(field, literal)

    def test_unsupported_units_are_rejected(self):
        for field, literal in (
            ("temperature_unit", '"fahrenheit"'),
            ("precipitation_unit", '"inch"'),
            ("wind_speed_unit", '"mph"'),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                self.validate_setting(field, literal)


class CityConfigTests(unittest.TestCase):
    def setUp(self):
        self.lines = CITY_CONFIG.read_text().splitlines()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "cities.csv"

    def validate_lines(self, lines):
        self.path.write_text("\n".join(lines) + "\n")
        with patch("weather_pipeline.config.CITY_CONFIG", self.path):
            return validate_city_config()

    def test_duplicate_city_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate city_id: kyiv"):
            self.validate_lines([*self.lines, self.lines[1]])

    def test_short_and_long_rows_are_rejected(self):
        for row in (self.lines[1].rsplit(",", 1)[0], self.lines[1] + ",extra"):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "row 2: wrong number"):
                self.validate_lines([self.lines[0], row])

    def test_duplicate_missing_and_unexpected_headers_are_rejected(self):
        for header in (
            self.lines[0] + ",city_id",
            self.lines[0].rsplit(",", 1)[0],
            self.lines[0].replace("active", "enabled"),
        ):
            with self.subTest(header=header), self.assertRaisesRegex(ValueError, "columns"):
                self.validate_lines([header, self.lines[1]])

    def test_invalid_city_values_are_rejected(self):
        for index, value, message in (
            (0, "../kyiv", "city_id"),
            (3, "91", "latitude"),
            (4, "181", "longitude"),
            (5, "Invalid/Zone", "timezone"),
            (6, "yes", "active"),
        ):
            fields = self.lines[1].split(",")
            fields[index] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, message):
                self.validate_lines([self.lines[0], ",".join(fields)])

    def test_empty_city_list_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least one city"):
            self.validate_lines([self.lines[0]])

    def test_valid_city_file_is_accepted(self):
        self.assertEqual(len(self.validate_lines(self.lines)), 10)
