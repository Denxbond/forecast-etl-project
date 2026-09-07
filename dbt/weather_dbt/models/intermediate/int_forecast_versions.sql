{{ config(materialized='view') }}

select
    city_id,
    retrieved_at,
    forecast_at,
    forecast_at - retrieved_at as forecast_lead_time,
    extract(epoch from forecast_at - retrieved_at) / 3600.0 as forecast_lead_hours,
    temperature_2m,
    precipitation,
    wind_speed_10m,
    weather_code
from {{ ref('stg_hourly_forecast') }}
