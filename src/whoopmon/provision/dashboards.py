"""Dashboards as code. `build_all()` returns OpenObserve dashboard JSON (schema v5).

Every health query reads the latest version of each record (see LATEST below),
because OpenObserve appends and WHOOP re-scores records after they first appear.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Panel widths are written in 1/192ths for finer control; OpenObserve v5 uses a 48-column grid.
GRID_COLUMNS = 192
GRID_SCALE = 4


def latest(stream: str, where: str = "") -> str:
    """Sub-query: newest row per record_id, without deleted records."""
    extra = f" AND {where}" if where else ""
    return (
        "(SELECT * FROM (SELECT *, ROW_NUMBER() OVER "
        "(PARTITION BY record_id ORDER BY updated_at DESC) AS rn "
        f'FROM "{stream}") WHERE rn = 1 AND (deleted IS NULL OR deleted = false){extra})'
    )


@dataclass
class Panel:
    title: str
    type: str  # line | bar | area | metric | table | pie | h-bar | area-stacked | stacked
    sql: str
    stream: str
    x: list[tuple[str, str]] = field(default_factory=list)  # (alias, label)
    y: list[tuple[str, str]] = field(default_factory=list)
    breakdown: list[tuple[str, str]] = field(default_factory=list)
    w: int = 96
    h: int = 9
    unit: str | None = None
    decimals: int = 1
    description: str = ""
    stream_type: str = "logs"
    # alias -> hex. Fixed series colours (e.g. WHOOP recovery zones) instead of the palette.
    colors: dict[str, str] = field(default_factory=dict)


def _axis(
    alias: str, label: str, agg: str | None = None, color: str | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "label": label,
        "alias": alias,
        "column": alias,
        "color": color,
        "isDerived": False,
    }
    if agg:
        out["aggregationFunction"] = agg
    return out


def _config(p: Panel) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "show_legends": True,
        "legends_position": "bottom",
        "decimals": p.decimals,
        "line_thickness": 1.5,
        "show_symbol": True,
        "line_interpolation": "smooth",
        "connect_nulls": True,
        "no_value_replacement": "",
        "wrap_table_cells": False,
        "table_transpose": False,
        "table_dynamic_columns": False,
        "axis_border_show": False,
        "top_results_others": False,
        "label_option": {"rotate": 0},
        "legend_width": {"unit": "px"},
        "drilldown": [],
        "mark_line": [],
        "override_config": [],
        "mappings": [],
        "color": {
            "mode": "palette-classic-by-series",
            "fixedColor": ["#53ca53"],
            "seriesBy": "last",
        },
        "trellis": {"layout": None, "num_of_columns": 1},
    }
    colors = p.colors or (
        {alias: SERIES_PALETTE[i % len(SERIES_PALETTE)] for i, (alias, _) in enumerate(p.y)}
        if len(p.y) > 1 and not p.breakdown and p.type not in ("table", "metric")
        else {}
    )
    if colors:
        # Pin series colours by label (e.g. WHOOP recovery zones).
        labels = dict(p.y)
        cfg["color"]["colorBySeries"] = [
            {"type": "fixedColor", "value": labels[alias], "color": color}
            for alias, color in colors.items()
            if alias in labels
        ]
    if p.unit:
        cfg["unit"] = "custom"
        cfg["unit_custom"] = p.unit
    return cfg


def _panel_json(index: int, p: Panel, x: int, y: int) -> dict[str, Any]:
    return {
        "id": f"Panel_ID{index:04d}",
        "type": p.type,
        "title": p.title,
        "description": p.description,
        "config": _config(p),
        "queryType": "sql",
        "queries": [
            {
                "query": p.sql,
                "vrlFunctionQuery": "",
                "customQuery": True,
                "fields": {
                    "stream": p.stream,
                    "stream_type": p.stream_type,
                    "x": [_axis(a, label) for a, label in p.x],
                    "y": [_axis(a, label, "max", p.colors.get(a)) for a, label in p.y],
                    "z": [],
                    "breakdown": [_axis(a, label) for a, label in p.breakdown],
                    "filter": {"filterType": "group", "logicalOperator": "AND", "conditions": []},
                },
                "config": {
                    "promql_legend": "",
                    "layer_type": "scatter",
                    "weight_fixed": 1,
                    "limit": 0,
                    "min": 0,
                    "max": 100,
                    "time_shift": [],
                },
            }
        ],
        "layout": {
            "x": x // GRID_SCALE,
            "y": y,
            "w": p.w // GRID_SCALE,
            "h": p.h,
            "i": index,
            "moved": False,
        },
        "htmlContent": "",
        "markdownContent": "",
        "customChartContent": "",
    }


def dashboard(
    dashboard_id: str, title: str, description: str, panels: list[Panel], period: str = "30d"
) -> dict[str, Any]:
    out, x, y, row_h = [], 0, 0, 0
    for i, p in enumerate(panels, start=1):
        if x + p.w > GRID_COLUMNS:
            x, y, row_h = 0, y + row_h, 0
        out.append(_panel_json(i, p, x, y))
        x, row_h = x + p.w, max(row_h, p.h)
    return {
        "version": 5,
        "dashboardId": dashboard_id,
        "title": title,
        "description": description,
        "role": "",
        "owner": "",
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tabs": [{"tabId": "default", "name": "Default", "panels": out}],
        "variables": {"list": [], "showDynamicFilters": False},
        "defaultDatetimeDuration": {
            "type": "relative",
            "relativeTimePeriod": period,
            "startTime": 0,
            "endTime": 0,
        },
    }


ZONE_COLORS = {"red": "#e5484d", "yellow": "#f5c518", "green": "#16a34a"}
SLEEP_STAGE_COLORS = {"deep": "#6d28d9", "rem": "#0ea5e9", "light": "#93c5fd", "awake": "#9ca3af"}
# Distinct colours for multi-series panels without their own map. The default palette
# hashes series names, so two series can get the same colour.
SERIES_PALETTE = ("#3b82f6", "#f97316", "#10b981", "#e11d48", "#a855f7", "#eab308")


def _day(col: str = "local_date") -> tuple[str, str]:
    return (col, "Day")


# -- Readiness ----------------------------------------------------------------


def readiness(prefix: str) -> dict[str, Any]:
    s = f"{prefix}recovery"
    rec = latest(s, "score_state = 'SCORED'")
    kpi = 48
    return dashboard(
        "whoop_readiness",
        "WHOOP · Readiness",
        "Recovery, HRV, resting heart rate, SpO2 and skin temperature. One point per day.",
        [
            Panel(
                "Recovery today",
                "metric",
                f"SELECT score_recovery_score AS y FROM {rec} ORDER BY _timestamp DESC LIMIT 1",
                s,
                y=[("y", "Recovery")],
                w=kpi,
                h=6,
                unit="%",
                decimals=0,
            ),
            Panel(
                "HRV today",
                "metric",
                f"SELECT score_hrv_rmssd_milli AS y FROM {rec} ORDER BY _timestamp DESC LIMIT 1",
                s,
                y=[("y", "HRV")],
                w=kpi,
                h=6,
                unit="ms",
                decimals=0,
            ),
            Panel(
                "Resting HR today",
                "metric",
                f"SELECT score_resting_heart_rate AS y FROM {rec} ORDER BY _timestamp DESC LIMIT 1",
                s,
                y=[("y", "RHR")],
                w=kpi,
                h=6,
                unit="bpm",
                decimals=0,
            ),
            Panel(
                "HRV vs period mean",
                "metric",
                f"SELECT ROUND(100.0 * (MAX(CASE WHEN rk = 1 THEN score_hrv_rmssd_milli END) "
                f"/ AVG(score_hrv_rmssd_milli) - 1), 1) AS y FROM (SELECT *, ROW_NUMBER() OVER "
                f"(ORDER BY _timestamp DESC) AS rk FROM {rec})",
                s,
                y=[("y", "Δ HRV")],
                w=kpi,
                h=6,
                unit="%",
            ),
            Panel(
                "Recovery %",
                "stacked",
                f"SELECT local_date, "
                f"CASE WHEN recovery_zone = 'red' THEN score_recovery_score ELSE 0 END AS red, "
                f"CASE WHEN recovery_zone = 'yellow' THEN score_recovery_score ELSE 0 END AS yellow, "
                f"CASE WHEN recovery_zone = 'green' THEN score_recovery_score ELSE 0 END AS green "
                f"FROM {rec} ORDER BY local_date",
                s,
                x=[_day()],
                y=[("red", "Red"), ("yellow", "Yellow"), ("green", "Green")],
                colors=ZONE_COLORS,
                w=192,
                unit="%",
                decimals=0,
            ),
            Panel(
                "HRV (rMSSD)",
                "line",
                f"SELECT local_date, score_hrv_rmssd_milli AS hrv, "
                f"AVG(score_hrv_rmssd_milli) OVER (ORDER BY local_date ROWS BETWEEN 6 PRECEDING "
                f"AND CURRENT ROW) AS hrv_7d FROM {rec} ORDER BY local_date",
                s,
                x=[_day()],
                y=[("hrv", "HRV"), ("hrv_7d", "7-day mean")],
                unit="ms",
            ),
            Panel(
                "Resting heart rate",
                "line",
                f"SELECT local_date, score_resting_heart_rate AS rhr "
                f"FROM {rec} ORDER BY local_date",
                s,
                x=[_day()],
                y=[("rhr", "RHR")],
                unit="bpm",
                decimals=0,
            ),
            Panel(
                "Blood oxygen (SpO2)",
                "line",
                f"SELECT local_date, score_spo2_percentage AS spo2 FROM {rec} ORDER BY local_date",
                s,
                x=[_day()],
                y=[("spo2", "SpO2")],
                unit="%",
            ),
            Panel(
                "Skin temperature",
                "line",
                f"SELECT local_date, score_skin_temp_celsius AS temp "
                f"FROM {rec} ORDER BY local_date",
                s,
                x=[_day()],
                y=[("temp", "Skin temp")],
                unit="°C",
                decimals=2,
            ),
            Panel(
                "Days per recovery zone",
                "bar",
                f"SELECT 'days' AS period, "
                f"SUM(CASE WHEN recovery_zone = 'red' THEN 1 ELSE 0 END) AS red, "
                f"SUM(CASE WHEN recovery_zone = 'yellow' THEN 1 ELSE 0 END) AS yellow, "
                f"SUM(CASE WHEN recovery_zone = 'green' THEN 1 ELSE 0 END) AS green FROM {rec}",
                s,
                x=[("period", "Period")],
                y=[("red", "Red"), ("yellow", "Yellow"), ("green", "Green")],
                colors=ZONE_COLORS,
                w=64,
                decimals=0,
            ),
            Panel(
                "Recent recoveries",
                "table",
                f"SELECT local_date, score_recovery_score AS "
                f"recovery, recovery_zone AS zone, score_hrv_rmssd_milli AS hrv_ms, "
                f"score_resting_heart_rate AS rhr, score_spo2_percentage AS spo2 FROM {rec} "
                f"ORDER BY local_date DESC LIMIT 14",
                s,
                x=[("local_date", "Day"), ("zone", "Zone")],
                y=[("recovery", "Recovery"), ("hrv_ms", "HRV"), ("rhr", "RHR"), ("spo2", "SpO2")],
                w=128,
            ),
        ],
    )


# -- Sleep --------------------------------------------------------------------


def sleep(prefix: str) -> dict[str, Any]:
    s = f"{prefix}sleep"
    night = latest(s, "score_state = 'SCORED' AND nap = false")
    return dashboard(
        "whoop_sleep",
        "WHOOP · Sleep",
        "Sleep stages, performance, need vs actual and respiratory rate. Naps are excluded "
        "unless stated.",
        [
            Panel(
                "Avg sleep (h)",
                "metric",
                f"SELECT AVG(score_stage_summary_total_in_bed_time_hours "
                f"- score_stage_summary_total_awake_time_hours) AS y FROM {night}",
                s,
                y=[("y", "Asleep")],
                w=48,
                h=6,
                unit="h",
            ),
            Panel(
                "Avg performance",
                "metric",
                f"SELECT AVG(score_sleep_performance_percentage) AS y FROM {night}",
                s,
                y=[("y", "Performance")],
                w=48,
                h=6,
                unit="%",
                decimals=0,
            ),
            Panel(
                "Avg efficiency",
                "metric",
                f"SELECT AVG(score_sleep_efficiency_percentage) AS y FROM {night}",
                s,
                y=[("y", "Efficiency")],
                w=48,
                h=6,
                unit="%",
                decimals=0,
            ),
            Panel(
                "Avg consistency",
                "metric",
                f"SELECT AVG(score_sleep_consistency_percentage) AS y FROM {night}",
                s,
                y=[("y", "Consistency")],
                w=48,
                h=6,
                unit="%",
                decimals=0,
            ),
            Panel(
                "Sleep stages per night",
                "stacked",
                f"SELECT local_date, score_stage_summary_total_slow_wave_sleep_time_hours AS deep, "
                f"score_stage_summary_total_rem_sleep_time_hours AS rem, "
                f"score_stage_summary_total_light_sleep_time_hours AS light, "
                f"score_stage_summary_total_awake_time_hours AS awake FROM {night} "
                f"ORDER BY local_date",
                s,
                x=[_day()],
                y=[("deep", "Deep (SWS)"), ("rem", "REM"), ("light", "Light"), ("awake", "Awake")],
                colors=SLEEP_STAGE_COLORS,
                w=192,
                unit="h",
                decimals=2,
            ),
            Panel(
                "Sleep need vs actual",
                "line",
                f"SELECT local_date, (score_sleep_needed_baseline_hours + "
                f"score_sleep_needed_need_from_sleep_debt_hours + "
                f"score_sleep_needed_need_from_recent_strain_hours + "
                f"score_sleep_needed_need_from_recent_nap_hours) AS need, "
                f"(score_stage_summary_total_in_bed_time_hours - "
                f"score_stage_summary_total_awake_time_hours) AS actual FROM {night} "
                f"ORDER BY local_date",
                s,
                x=[_day()],
                y=[("need", "Need"), ("actual", "Asleep")],
                unit="h",
                decimals=2,
            ),
            Panel(
                "Performance · efficiency · consistency",
                "line",
                f"SELECT local_date, score_sleep_performance_percentage AS performance, "
                f"score_sleep_efficiency_percentage AS efficiency, "
                f"score_sleep_consistency_percentage AS consistency FROM {night} "
                f"ORDER BY local_date",
                s,
                x=[_day()],
                y=[
                    ("performance", "Performance"),
                    ("efficiency", "Efficiency"),
                    ("consistency", "Consistency"),
                ],
                unit="%",
                decimals=0,
            ),
            Panel(
                "Respiratory rate",
                "line",
                f"SELECT local_date, score_respiratory_rate AS rr FROM {night} ORDER BY local_date",
                s,
                x=[_day()],
                y=[("rr", "Breaths/min")],
                unit="rpm",
                decimals=1,
            ),
            Panel(
                "Disturbances and cycles",
                "bar",
                f"SELECT local_date, score_stage_summary_disturbance_count AS disturbances, "
                f"score_stage_summary_sleep_cycle_count AS cycles FROM {night} "
                f"ORDER BY local_date",
                s,
                x=[_day()],
                y=[("disturbances", "Disturbances"), ("cycles", "Sleep cycles")],
                decimals=0,
            ),
            Panel(
                "Naps",
                "table",
                f"SELECT local_date, duration_hours AS hours, "
                f"score_sleep_performance_percentage AS performance FROM "
                f"{latest(s, 'nap = true')} ORDER BY local_date DESC LIMIT 20",
                s,
                x=[("local_date", "Day")],
                y=[("hours", "Hours"), ("performance", "Performance")],
                w=192,
                h=7,
            ),
        ],
    )


# -- Strain & training --------------------------------------------------------


def strain(prefix: str) -> dict[str, Any]:
    c, w = f"{prefix}cycle", f"{prefix}workout"
    cyc = latest(c, "score_state = 'SCORED'")
    wo = latest(w, "score_state = 'SCORED'")
    return dashboard(
        "whoop_strain",
        "WHOOP · Strain & Training",
        "Day strain, steps, energy and workouts with heart-rate zones.",
        [
            Panel(
                "Avg day strain",
                "metric",
                f"SELECT AVG(score_strain) AS y FROM {cyc}",
                c,
                y=[("y", "Strain")],
                w=48,
                h=6,
            ),
            Panel(
                "Avg steps / day",
                "metric",
                f"SELECT AVG(step_count) AS y FROM {cyc} WHERE step_count IS NOT NULL",
                c,
                y=[("y", "Steps")],
                w=48,
                h=6,
                decimals=0,
            ),
            Panel(
                "Workouts",
                "metric",
                f"SELECT COUNT(*) AS y FROM {wo}",
                w,
                y=[("y", "Workouts")],
                w=48,
                h=6,
                decimals=0,
            ),
            Panel(
                "Training hours",
                "metric",
                f"SELECT SUM(duration_hours) AS y FROM {wo}",
                w,
                y=[("y", "Hours")],
                w=48,
                h=6,
                unit="h",
            ),
            Panel(
                "Day strain (0–21)",
                "bar",
                f"SELECT local_date, score_strain AS strain FROM {cyc} ORDER BY local_date",
                c,
                x=[_day()],
                y=[("strain", "Strain")],
                w=192,
            ),
            Panel(
                "Steps",
                "bar",
                f"SELECT local_date, step_count AS steps FROM {cyc} "
                f"WHERE step_count IS NOT NULL ORDER BY local_date",
                c,
                x=[_day()],
                y=[("steps", "Steps")],
                decimals=0,
            ),
            Panel(
                "Energy burned (kcal)",
                "line",
                f"SELECT local_date, score_kilojoule / 4.184 AS kcal "
                f"FROM {cyc} ORDER BY local_date",
                c,
                x=[_day()],
                y=[("kcal", "kcal")],
                decimals=0,
            ),
            Panel(
                "Heart-rate zone time per week (min)",
                "stacked",
                f"SELECT date_trunc('week', to_timestamp_micros(_timestamp)) AS week, "
                f"SUM(score_zone_durations_zone_one_milli) / 60000 AS z1, "
                f"SUM(score_zone_durations_zone_two_milli) / 60000 AS z2, "
                f"SUM(score_zone_durations_zone_three_milli) / 60000 AS z3, "
                f"SUM(score_zone_durations_zone_four_milli) / 60000 AS z4, "
                f"SUM(score_zone_durations_zone_five_milli) / 60000 AS z5 FROM {wo} "
                f"GROUP BY week ORDER BY week",
                w,
                x=[("week", "Week")],
                y=[
                    ("z1", "Zone 1"),
                    ("z2", "Zone 2"),
                    ("z3", "Zone 3"),
                    ("z4", "Zone 4"),
                    ("z5", "Zone 5"),
                ],
                decimals=0,
            ),
            Panel(
                "Sport mix",
                "pie",
                f"SELECT sport_name, COUNT(*) AS n FROM {wo} GROUP BY sport_name ORDER BY n DESC",
                w,
                x=[("sport_name", "Sport")],
                y=[("n", "Workouts")],
                w=64,
                decimals=0,
            ),
            Panel(
                "Recent workouts",
                "table",
                f"SELECT local_date, sport_name, score_strain AS strain, "
                f"duration_hours AS hours, score_average_heart_rate AS avg_hr, "
                # No distance column: WHOOP omits it for non-GPS workouts, so the field may
                # not exist in the stream and OpenObserve rejects the whole query.
                f"score_max_heart_rate AS max_hr, score_kilojoule / 4.184 AS kcal FROM {wo} "
                f"ORDER BY _timestamp DESC LIMIT 20",
                w,
                x=[("local_date", "Day"), ("sport_name", "Sport")],
                y=[
                    ("strain", "Strain"),
                    ("hours", "Hours"),
                    ("avg_hr", "Avg HR"),
                    ("max_hr", "Max HR"),
                    ("kcal", "kcal"),
                ],
                w=128,
            ),
        ],
    )


# -- Collector health ---------------------------------------------------------


def collector() -> dict[str, Any]:
    s = "whoopmon_app"
    return dashboard(
        "whoopmon_collector",
        "WHOOP · Collector Health",
        "Health of the whoopmon collector: sync runs, shipped rows, API errors and rate limits.",
        [
            Panel(
                "Sync runs OK",
                "metric",
                f'SELECT COUNT(*) AS y FROM "{s}" WHERE '
                f"body = 'sync.run.finished' AND outcome = 'success'",
                s,
                y=[("y", "Runs")],
                w=48,
                h=6,
                decimals=0,
            ),
            Panel(
                "Sync runs failed",
                "metric",
                f'SELECT COUNT(*) AS y FROM "{s}" WHERE '
                f"body = 'sync.run.finished' AND outcome = 'failure'",
                s,
                y=[("y", "Failed")],
                w=48,
                h=6,
                decimals=0,
            ),
            Panel(
                "429 rate limits",
                "metric",
                f"SELECT COUNT(*) AS y FROM \"{s}\" WHERE body = 'whoop.request.rate_limited'",
                s,
                y=[("y", "429s")],
                w=48,
                h=6,
                decimals=0,
            ),
            Panel(
                "Errors",
                "metric",
                f"SELECT COUNT(*) AS y FROM \"{s}\" WHERE severity IN ('ERROR', 'FATAL')",
                s,
                y=[("y", "Errors")],
                w=48,
                h=6,
                decimals=0,
            ),
            Panel(
                "Rows shipped per stream",
                "stacked",
                f'SELECT histogram(_timestamp) AS t, stream, SUM(CAST(rows AS BIGINT)) AS rows FROM "{s}" '
                f"WHERE body = 'sink.write.completed' GROUP BY t, stream ORDER BY t",
                s,
                x=[("t", "Time")],
                y=[("rows", "Rows")],
                breakdown=[("stream", "Stream")],
                w=192,
                decimals=0,
            ),
            Panel(
                "Log events by severity",
                "stacked",
                f'SELECT histogram(_timestamp) AS t, severity, COUNT(*) AS n FROM "{s}" '
                f"GROUP BY t, severity ORDER BY t",
                s,
                x=[("t", "Time")],
                y=[("n", "Events")],
                breakdown=[("severity", "Severity")],
                decimals=0,
            ),
            Panel(
                "Sync run duration (ms)",
                "line",
                f'SELECT histogram(_timestamp) AS t, MAX(duration_ms) AS ms FROM "{s}" '
                f"WHERE body = 'sync.run.finished' GROUP BY t ORDER BY t",
                s,
                x=[("t", "Time")],
                y=[("ms", "Duration")],
                unit="ms",
                decimals=0,
            ),
            Panel(
                "Recent warnings and errors",
                "table",
                f'SELECT _timestamp, severity, body, logger, run_id FROM "{s}" '
                f"WHERE severity IN ('WARN', 'ERROR', 'FATAL') ORDER BY _timestamp DESC "
                f"LIMIT 50",
                s,
                x=[
                    ("_timestamp", "Time"),
                    ("severity", "Severity"),
                    ("body", "Event"),
                    ("logger", "Logger"),
                ],
                y=[],
                w=192,
                h=9,
            ),
        ],
        period="24h",
    )


def build_all(prefix: str = "whoop_") -> list[dict[str, Any]]:
    return [readiness(prefix), sleep(prefix), strain(prefix), collector()]
