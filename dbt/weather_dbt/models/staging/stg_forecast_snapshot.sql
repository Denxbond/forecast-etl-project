{{ config(materialized='view') }}

select
    city_id,
    retrieved_at,
    raw_response_path,
    request_params,
    grid_latitude,
    grid_longitude
from {{ source('weather_raw', 'forecast_snapshot') }}
