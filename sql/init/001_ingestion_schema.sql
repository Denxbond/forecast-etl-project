-- Apply explicitly with make db-init, including on an existing Docker volume.
-- IF NOT EXISTS allows rerunning this initial setup; it is not a migration tool.
BEGIN;

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.city (
    city_id TEXT PRIMARY KEY,
    city_name TEXT NOT NULL,
    country_code TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    timezone TEXT NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.forecast_snapshot (
    city_id TEXT NOT NULL REFERENCES raw.city (city_id),
    retrieved_at TIMESTAMPTZ NOT NULL,
    raw_response_path TEXT NOT NULL,
    request_params JSONB NOT NULL CHECK (jsonb_typeof(request_params) = 'object'),
    grid_latitude DOUBLE PRECISION NOT NULL CHECK (grid_latitude BETWEEN -90 AND 90),
    grid_longitude DOUBLE PRECISION NOT NULL CHECK (grid_longitude BETWEEN -180 AND 180),
    PRIMARY KEY (city_id, retrieved_at)
);

CREATE TABLE IF NOT EXISTS raw.hourly_forecast (
    city_id TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    forecast_at TIMESTAMPTZ NOT NULL,
    temperature_2m DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    wind_speed_10m DOUBLE PRECISION,
    weather_code INTEGER,
    PRIMARY KEY (city_id, retrieved_at, forecast_at),
    FOREIGN KEY (city_id, retrieved_at)
        REFERENCES raw.forecast_snapshot (city_id, retrieved_at)
);

COMMENT ON TABLE raw.forecast_snapshot IS
    'One city response per retrieval; raw_response_path identifies the preserved local response.';
COMMENT ON TABLE raw.hourly_forecast IS
    'One forecast hour per retrieval snapshot; earlier-than-retrieval hours and null measurements are allowed.';

COMMIT;
