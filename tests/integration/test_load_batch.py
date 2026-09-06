"""Batch orchestration checks alongside warehouse integration tests."""

import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import psycopg

from weather_pipeline.load import load_batch, load_directory, main


class BatchTests(unittest.TestCase):
    def test_counts_and_continuation_after_failures(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('a', 'b', 'c', 'd', 'e'):
                directory = root / 'kyiv' / name
                directory.mkdir(parents=True)
                if name != 'e':
                    (directory / '_SUCCESS').touch()
            with patch('weather_pipeline.load.load_directory', side_effect=[
                (True, 168), ValueError('invalid response'),
                psycopg.OperationalError('connection lost'), (False, 168),
            ]) as load, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                counts = load_batch(root, {}, {})
            self.assertEqual(counts, dict(loaded=1, already_loaded=1, failed=2, incomplete=1))
            self.assertEqual(load.call_count, 4)

    def test_missing_and_empty_roots_fail(self):
        with TemporaryDirectory() as tmp:
            for root in (Path(tmp), Path(tmp) / 'missing'):
                with self.subTest(root=root), self.assertRaises(ValueError):
                    load_batch(root, {}, {})

    def test_batch_failure_returns_nonzero(self):
        with patch('weather_pipeline.load.validate_city_config', return_value=[]), \
             patch('weather_pipeline.load.connection_settings', return_value={}), \
             patch('weather_pipeline.load.load_batch', return_value={'failed': 1}):
            self.assertEqual(main(['--all', 'data/raw']), 1)

    def test_fresh_connections_are_used_for_each_snapshot(self):
        prepared = {'snapshot': {'city_id': 'kyiv'}, 'hourly_rows': [{}]}
        with patch('weather_pipeline.load.prepare_snapshot', return_value=prepared), \
             patch('weather_pipeline.load.psycopg.connect') as connect, \
             patch('weather_pipeline.load.load_prepared', return_value=True):
            for path in ('first', 'second'):
                self.assertEqual(load_directory(Path(path), {'kyiv': {}}, {}), (True, 1))
            self.assertEqual(connect.call_count, 2)
