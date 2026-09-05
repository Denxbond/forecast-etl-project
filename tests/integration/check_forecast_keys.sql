-- All test rows are rolled back, including after an assertion failure.
BEGIN;

DO $$
DECLARE
    test_city TEXT := '__key_check_' || gen_random_uuid()::TEXT;
    row_count INTEGER;
BEGIN
    INSERT INTO raw.city
        (city_id, city_name, country_code, latitude, longitude, timezone, active)
    VALUES (test_city, 'Key test', 'UA', 50.4501, 30.5234, 'Europe/Kyiv', false);

    INSERT INTO raw.forecast_snapshot
        (city_id, retrieved_at, raw_response_path, request_params,
         grid_latitude, grid_longitude)
    VALUES
        (test_city, '2026-09-05 06:00+00', 'test-only/first.json', '{}', 50.4375, 30.5),
        (test_city, '2026-09-05 12:00+00', 'test-only/second.json', '{}', 50.4375, 30.5);

    INSERT INTO raw.hourly_forecast
        (city_id, retrieved_at, forecast_at, temperature_2m)
    VALUES
        (test_city, '2026-09-05 06:00+00', '2026-09-06 12:00+00', 22.1),
        (test_city, '2026-09-05 12:00+00', '2026-09-06 12:00+00', 23.4);

    SELECT count(*) INTO row_count FROM raw.hourly_forecast WHERE city_id = test_city;
    IF row_count <> 2 THEN
        RAISE EXCEPTION 'Expected two preserved forecast versions';
    END IF;
    RAISE NOTICE 'PASS: two versions of the same forecast hour coexist.';

    BEGIN
        INSERT INTO raw.hourly_forecast (city_id, retrieved_at, forecast_at)
        VALUES (test_city, '2026-09-05 06:00+00', '2026-09-06 12:00+00');
        RAISE EXCEPTION 'Duplicate forecast was unexpectedly accepted';
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'PASS: duplicate forecast identity rejected.';
    END;

    BEGIN
        INSERT INTO raw.hourly_forecast (city_id, retrieved_at, forecast_at)
        VALUES (test_city, '2026-09-05 18:00+00', '2026-09-06 12:00+00');
        RAISE EXCEPTION 'Forecast without a snapshot was unexpectedly accepted';
    EXCEPTION WHEN foreign_key_violation THEN
        RAISE NOTICE 'PASS: forecast without a snapshot rejected.';
    END;

    -- Midnight precedes retrieval; omitted weather columns remain SQL NULL.
    INSERT INTO raw.hourly_forecast (city_id, retrieved_at, forecast_at)
    VALUES (test_city, '2026-09-05 06:00+00', '2026-09-05 00:00+00');
    RAISE NOTICE 'PASS: earlier forecast hour and null measurements accepted.';
END;
$$;

ROLLBACK;
