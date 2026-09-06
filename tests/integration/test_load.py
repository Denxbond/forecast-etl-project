"""Real PostgreSQL transaction checks; all test records are rolled back."""

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg

from weather_pipeline.client import build_request_params
from weather_pipeline.config import PROJECT_ROOT, validate_city_config, validate_pipeline_config
from weather_pipeline.load import connection_settings, load_prepared
from weather_pipeline.normalize import normalize_forecast


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(**connection_settings(), autocommit=True)
        self.addCleanup(self.conn.close)
        self.city = validate_city_config()[0].copy()
        self.city['city_id'] = 'test_' + uuid4().hex
        body = (PROJECT_ROOT / 'tests/fixtures/open_meteo_kyiv_forecast.json').read_bytes()
        api = validate_pipeline_config()['open_meteo']
        retrieved = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        payload = json.loads(body)
        self.prepared = {
            'snapshot': {'city_id': self.city['city_id'], 'retrieved_at': retrieved,
                         'raw_response_path': 'test-only/response.json',
                         'request_params': build_request_params(api, self.city),
                         'grid_latitude': payload['latitude'],
                         'grid_longitude': payload['longitude']},
            'hourly_rows': normalize_forecast(body, api, self.city['city_id'], retrieved),
        }

    def count(self, table):
        # Table identifiers are fixed test constants, never external input.
        from psycopg import sql
        row = self.conn.execute(
            sql.SQL('SELECT count(*) FROM raw.{} WHERE city_id = %s').format(sql.Identifier(table)),
            (self.city['city_id'],)).fetchone()
        if row is None:
            raise AssertionError('COUNT query unexpectedly returned no row')
        return row[0]

    def test_insert_replay_and_new_version(self):
        with self.conn.transaction(force_rollback=True):
            self.assertTrue(load_prepared(self.conn, self.prepared, self.city))
            self.assertFalse(load_prepared(self.conn, self.prepared, self.city))
            self.assertEqual(self.count('hourly_forecast'), 168)
            later = copy.deepcopy(self.prepared)
            later['snapshot']['retrieved_at'] += timedelta(hours=6)
            for row in later['hourly_rows']:
                row['retrieved_at'] = later['snapshot']['retrieved_at']
            self.assertTrue(load_prepared(self.conn, later, self.city))
            self.assertEqual(self.count('forecast_snapshot'), 2)
            self.assertEqual(self.count('hourly_forecast'), 336)
        self.assertEqual(self.count('city'), 0)

    def test_sql_failure_rolls_back_city_snapshot_and_hours(self):
        broken = copy.deepcopy(self.prepared)
        broken['hourly_rows'].append(broken['hourly_rows'][0].copy())
        with self.conn.transaction(force_rollback=True):
            with self.assertRaises(psycopg.errors.UniqueViolation):
                load_prepared(self.conn, broken, self.city)
            for table in ('city', 'forecast_snapshot', 'hourly_forecast'):
                self.assertEqual(self.count(table), 0)

    def test_conflicting_replay_is_rejected(self):
        with self.conn.transaction(force_rollback=True):
            load_prepared(self.conn, self.prepared, self.city)
            changed = copy.deepcopy(self.prepared)
            changed['hourly_rows'][0]['temperature_2m'] = 999
            with self.assertRaisesRegex(ValueError, 'different content'):
                load_prepared(self.conn, changed, self.city)
            self.assertFalse(load_prepared(self.conn, self.prepared, self.city))
