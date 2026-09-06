{{ config(materialized='view') }}

select
    city_id,
    retrieved_at,
    forecast_at,
    temperature_2m,
    precipitation,
    wind_speed_10m,
    weather_code
from {{ source('weather_raw', 'hourly_forecast') }}
