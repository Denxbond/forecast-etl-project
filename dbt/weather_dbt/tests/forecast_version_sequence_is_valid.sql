select
    city_id,
    forecast_at,
    count(*) as version_count,
    min(forecast_version_number) as minimum_version,
    max(forecast_version_number) as maximum_version,
    count(*) filter (where is_latest_forecast_version) as latest_version_count,
    max(forecast_version_number) filter (
        where is_latest_forecast_version
    ) as latest_version_number
from {{ ref('int_forecast_versions') }}
group by city_id, forecast_at
having
    min(forecast_version_number) <> 1
    or max(forecast_version_number) <> count(*)
    or count(*) filter (where is_latest_forecast_version) <> 1
    or max(forecast_version_number) filter (
        where is_latest_forecast_version
    ) <> max(forecast_version_number)
