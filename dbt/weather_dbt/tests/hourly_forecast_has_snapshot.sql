-- Match both columns: the city alone does not identify a retrieval snapshot.
select
    hourly.city_id,
    hourly.retrieved_at,
    hourly.forecast_at
from {{ ref('stg_hourly_forecast') }} as hourly
where not exists (
    select 1
    from {{ ref('stg_forecast_snapshot') }} as snapshot
    where snapshot.city_id = hourly.city_id
      and snapshot.retrieved_at = hourly.retrieved_at
)
