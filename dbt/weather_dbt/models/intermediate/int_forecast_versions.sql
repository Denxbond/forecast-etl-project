{{ config(materialized='view') }}

select
    city_id,
    retrieved_at,
    forecast_at,
    forecast_at - retrieved_at as forecast_lead_time,
    extract(epoch from forecast_at - retrieved_at) / 3600.0 as forecast_lead_hours,
    row_number() over (
        partition by city_id, forecast_at
        order by retrieved_at
    ) as forecast_version_number,
    retrieved_at = max(retrieved_at) over (
        partition by city_id, forecast_at
    ) as is_latest_forecast_version,
    temperature_2m,
    precipitation,
    wind_speed_10m,
    weather_code
from {{ ref('stg_hourly_forecast') }}
