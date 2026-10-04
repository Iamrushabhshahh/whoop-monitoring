# Data dictionary

All health streams are OpenObserve **logs** streams in org `default`.
Nested WHOOP fields are flattened with `_`: `score.stage_summary.total_rem_sleep_time_milli`
becomes `score_stage_summary_total_rem_sleep_time_milli`.

## Columns on every health row

| Column | Meaning |
|---|---|
| `_timestamp` | Event time (µs). Cycle/sleep/workout: `start`. Recovery: `created_at`. |
| `local_date` | Calendar day in the member's timezone. Sleep uses its **end** (wake-up day). |
| `record_type` | `cycle`, `recovery`, `sleep`, `workout`, `body` |
| `record_id` | WHOOP id (recovery: `cycle_id`) |
| `record_key` | `record_id@updated_at`. One version of one record. |
| `deleted` | `true` only on tombstones from `*.deleted` webhooks |
| `score_state` | `SCORED`, `PENDING_SCORE`, `UNSCORABLE` |
| `*_hours` | Added next to every `*_milli` column, in hours |
| `duration_hours` | `end - start` |

## `whoop_cycle` — one physiological day

| Column | Unit |
|---|---|
| `score_strain` | 0–21 |
| `score_kilojoule` | kJ (÷ 4.184 = kcal) |
| `score_average_heart_rate`, `score_max_heart_rate` | bpm |
| `step_count` | steps (null when not available; added 2026-09-23) |

## `whoop_recovery` — one per cycle

| Column | Unit |
|---|---|
| `score_recovery_score` | % |
| `recovery_zone` | `red` 0–33, `yellow` 34–66, `green` 67–100 |
| `score_hrv_rmssd_milli` | ms |
| `score_resting_heart_rate` | bpm |
| `score_spo2_percentage` | % |
| `score_skin_temp_celsius` | °C |
| `score_user_calibrating` | bool (first days of a new member) |
| `sleep_id` | the sleep this recovery came from |

## `whoop_sleep`

| Column | Unit |
|---|---|
| `nap` | bool |
| `score_stage_summary_total_{in_bed,awake,light_sleep,slow_wave_sleep,rem_sleep,no_data}_time_milli` | ms (+ `_hours`) |
| `score_stage_summary_sleep_cycle_count`, `_disturbance_count` | count |
| `score_sleep_needed_{baseline,need_from_sleep_debt,need_from_recent_strain,need_from_recent_nap}_milli` | ms (+ `_hours`) |
| `score_respiratory_rate` | breaths/min |
| `score_sleep_{performance,consistency,efficiency}_percentage` | % |

## `whoop_workout`

| Column | Unit |
|---|---|
| `sport_name`, `sport_id` | — |
| `score_strain` | 0–21 |
| `score_average_heart_rate`, `score_max_heart_rate` | bpm |
| `score_kilojoule` | kJ |
| `score_percent_recorded` | % |
| `score_distance_meter`, `score_altitude_gain_meter`, `score_altitude_change_meter` | m |
| `score_zone_durations_zone_{zero..five}_milli` | ms (+ `_hours`) |

> Optional fields (`score_distance_meter`, `score_altitude_*`, and SpO2/skin temperature while
> calibrating) are left out of the record by WHOOP when they have no value. OpenObserve creates
> a column only when a row contains it, and a query that names a missing column fails with
> "Search field not found". Use these columns only in your own ad-hoc queries.

## `whoop_body` — one row per day when values change

`height_meter`, `weight_kilogram`, `max_heart_rate`.

## Latest version of a record

OpenObserve appends. A re-scored record adds a row. Use:

```sql
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY record_id ORDER BY updated_at DESC) AS rn
  FROM "whoop_sleep"
) WHERE rn = 1 AND deleted = false AND score_state = 'SCORED'
```

## Not stored

The basic profile (name, email) is read only to show the user id. It is never written.
