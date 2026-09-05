# Open-Meteo Forecast API contract

This document records what Stage 2 learned from one live request for Kyiv. It
separates the stable response structure our code may rely on from forecast
values that change on every request.

## Exploration request

Endpoint:

```text
GET https://api.open-meteo.com/v1/forecast
```

Parameters:

```text
latitude=50.4501
longitude=30.5234
hourly=temperature_2m,precipitation,wind_speed_10m,weather_code
forecast_days=7
timezone=UTC
temperature_unit=celsius
precipitation_unit=mm
wind_speed_unit=kmh
```

The captured response and its request metadata are stored separately:

- `tests/fixtures/open_meteo_kyiv_forecast.json`
- `tests/fixtures/open_meteo_kyiv_forecast.metadata.json`

The forecast fixture is pretty-printed for review. It preserves the returned
JSON values but not the response's original whitespace or byte formatting.

## Response shape

The useful top-level fields are:

| Field | Meaning | Pipeline use |
| --- | --- | --- |
| `latitude`, `longitude` | Selected forecast grid-cell coordinates | Response metadata and debugging |
| `elevation` | Grid-cell elevation in metres | Response metadata |
| `generationtime_ms` | API processing time | Diagnostics only |
| `utc_offset_seconds` | Offset applied to returned times | Time validation |
| `timezone` | Timezone used by the response | Time validation |
| `timezone_abbreviation` | Display abbreviation | Metadata only |
| `hourly_units` | Unit for each hourly field | Contract validation |
| `hourly` | Parallel arrays containing forecast values | Normalized hourly rows |

`generationtime_ms` is neither the forecast model's issue time nor our
retrieval time. The ingestion client must create `retrieved_at` itself.

## Hourly fields and units

| Field | Observed unit | Meaning |
| --- | --- | --- |
| `time` | `iso8601` | Hour being forecast |
| `temperature_2m` | `°C` | Air temperature two metres above ground |
| `precipitation` | `mm` | Precipitation total for the preceding hour |
| `wind_speed_10m` | `km/h` | Wind speed ten metres above ground |
| `weather_code` | `wmo code` | Numeric WMO weather-condition code |

Variable definitions come from the
[official Open-Meteo documentation](https://open-meteo.com/en/docs).

## How parallel arrays become rows

Open-Meteo does not return one JSON object per hour. Every hourly field is a
separate array, and values at the same array position belong together:

```text
hourly.time[0]
hourly.temperature_2m[0]
hourly.precipitation[0]
hourly.wind_speed_10m[0]
hourly.weather_code[0]
```

These five values become one normalized database row. Before normalization,
the parser must verify that all arrays exist and have equal lengths. Python's
`zip()` alone is unsafe because it silently stops at the shortest array.

## Observed facts

- Seven forecast days returned 168 hourly positions: `7 × 24`.
- The range began at midnight on the current UTC date, not at retrieval time.
- Requesting `timezone=UTC` returned timezone label `GMT` with offset zero.
- Kyiv's requested coordinates were `(50.4501, 30.5234)`, while the response
  identified forecast grid cell `(50.4375, 30.5)`.
- Every requested hourly array had the same 168 positions.
- The response did not include our retrieval timestamp or a single model issue
  timestamp.

## Contract assumptions for implementation

The ingestion code may rely on:

- A successful response being valid JSON.
- `hourly` and `hourly_units` being objects.
- The configured hourly fields being present.
- All configured hourly arrays having identical lengths.
- Offset zero when UTC is requested, even if the label is `GMT` rather than
  the literal string `UTC`.
- Returned coordinates potentially differing from requested city coordinates.

The ingestion code must not rely on:

- Forecast values remaining constant.
- JSON object key order.
- The first forecast hour being later than `retrieved_at`.
- Returned coordinates exactly matching city coordinates.
- `generationtime_ms` identifying a forecast version.
- A weather measurement always being non-null without validation.

## Consequences for later stages

Stage 3 now enforces this contract in `src/weather_pipeline/validation.py`.
For the configured UTC daily window, our ingestion policy requires exactly
`forecast_days * 24` consecutive, unique hours starting at midnight. This is a
pipeline acceptance rule based on the explored request, not a promise that every
future API response will satisfy it. Null measurements are accepted as missing;
other measurements must be finite numbers, and weather codes must be integers.
Weather-code membership and physical value ranges are not checked yet.

Ingestion saves raw bytes before validation. A validation failure returns exit
code 1 and reports the retained snapshot path. `_SUCCESS` means only that raw
saving completed; later loaders must validate the saved response themselves.

- Capture an aware UTC `retrieved_at` timestamp in Python.
- Interpret offset-zero hourly strings as UTC before database insertion.
- Keep requested city coordinates in `dim_city` and returned grid coordinates
  with response metadata.
- Preserve forecast rows earlier than retrieval time if the API includes them;
  do not enforce `retrieved_at <= forecast_at` as a universal test.
- Store each retrieval snapshot instead of overwriting an existing
  `(city_id, forecast_at)` forecast.
- Validate the unit mapping so an upstream unit change fails visibly.
