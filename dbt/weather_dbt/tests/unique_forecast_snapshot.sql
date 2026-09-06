-- A test returns violating rows: no results means the key is unique.
select
    city_id,
    retrieved_at,
    count(*) as row_count
from {{ ref('stg_forecast_snapshot') }}
group by city_id, retrieved_at
having count(*) > 1
