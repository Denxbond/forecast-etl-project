select
    city_id,
    retrieved_at,
    forecast_at,
    count(*) as row_count
from {{ ref('stg_hourly_forecast') }}
group by city_id, retrieved_at, forecast_at
having count(*) > 1
