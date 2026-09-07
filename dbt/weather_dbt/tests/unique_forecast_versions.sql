select
    city_id,
    retrieved_at,
    forecast_at,
    count(*) as row_count
from {{ ref('int_forecast_versions') }}
group by city_id, retrieved_at, forecast_at
having count(*) > 1
