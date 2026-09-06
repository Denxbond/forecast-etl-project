{{ config(materialized='view') }}

select
    city_id,
    city_name,
    country_code,
    latitude as requested_latitude,
    longitude as requested_longitude,
    timezone as city_timezone,
    active as is_active
from {{ source('weather_raw', 'city') }}
