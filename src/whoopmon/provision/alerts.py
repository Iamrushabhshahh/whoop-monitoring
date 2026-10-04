"""Alerts as code. Notifications go to one HTTP destination (the whoopmon receiver
logs them as `alert.received`; swap the URL for Slack or another webhook)."""

from typing import Any

ALERT_TEMPLATE = "whoopmon_alert"
DESTINATION_NAME = "whoopmon_webhook"

TEMPLATE: dict[str, Any] = {
    "name": ALERT_TEMPLATE,
    "type": "http",
    "title": "whoopmon alert",
    "isPrebuilt": False,
    "body": (
        '{"alert": "{alert_name}", "stream": "{stream_name}", "count": "{alert_count}", '
        '"start": "{alert_start_time}", "end": "{alert_end_time}", "rows": "{rows}", '
        '"url": "{alert_url}"}'
    ),
}

DESTINATION: dict[str, Any] = {
    "name": DESTINATION_NAME,
    "type": "http",
    "method": "post",
    "url": "",  # set at provision time
    "skip_tls_verify": False,
    "headers": {"Content-Type": "application/json"},
    "emails": [],
    "metadata": {},
}


def _alert(
    name: str,
    description: str,
    stream: str,
    sql: str,
    org: str,
    period_min: int,
    frequency_min: int,
    silence_min: int,
) -> dict[str, Any]:
    return {
        "name": name,
        "org_id": org,
        "description": description,
        "stream_type": "logs",
        "stream_name": stream,
        "is_real_time": False,
        "query_condition": {"type": "sql", "sql": sql, "conditions": None, "vrl_function": None},
        "trigger_condition": {
            "period": period_min,
            "operator": ">=",
            "threshold": 1,
            "frequency": frequency_min,
            "frequency_type": "minutes",
            "silence": silence_min,
            "cron": "",
            "align_time": False,
        },
        "destinations": [DESTINATION_NAME],
        "enabled": True,
        "tz_offset": 0,
        "row_template": "",
        "tags": ["whoop"],
        "creates_incident": False,
    }


def build_alerts(prefix: str, org: str) -> list[dict[str, Any]]:
    rec = f"{prefix}recovery"
    app = "whoopmon_app"
    return [
        _alert(
            "whoop_recovery_red",
            "Recovery score is in the red zone (below 34 %). Take it easy today.",
            rec,
            f'SELECT local_date, score_recovery_score FROM "{rec}" '
            "WHERE score_state = 'SCORED' AND score_recovery_score < 34",
            org,
            period_min=60,
            frequency_min=60,
            silence_min=720,
        ),
        _alert(
            "whoop_hrv_drop",
            "Latest HRV is more than 20 % below the 7-day mean.",
            rec,
            "SELECT MAX(CASE WHEN rk = 1 THEN hrv END) AS latest_hrv, AVG(hrv) AS mean_hrv "
            "FROM (SELECT score_hrv_rmssd_milli AS hrv, "
            "ROW_NUMBER() OVER (ORDER BY _timestamp DESC) AS rk "
            f"FROM \"{rec}\" WHERE score_state = 'SCORED') "
            "HAVING MAX(CASE WHEN rk = 1 THEN hrv END) < 0.8 * AVG(hrv)",
            org,
            period_min=7 * 24 * 60,
            frequency_min=60,
            silence_min=24 * 60,
        ),
        _alert(
            "whoopmon_sync_stalled",
            "No successful sync run in the last 60 minutes.",
            app,
            f"SELECT COUNT(*) AS runs FROM \"{app}\" WHERE body = 'sync.run.finished' "
            "AND outcome = 'success' HAVING COUNT(*) = 0",
            org,
            period_min=60,
            frequency_min=30,
            silence_min=120,
        ),
        _alert(
            "whoopmon_sync_failed",
            "A sync run failed. Check the Collector Health dashboard.",
            app,
            f"SELECT run_id FROM \"{app}\" WHERE body = 'sync.run.finished' "
            "AND outcome = 'failure'",
            org,
            period_min=15,
            frequency_min=15,
            silence_min=60,
        ),
        _alert(
            "whoopmon_token_refresh_failed",
            "WHOOP token refresh failed. Run `whoopmon auth login` again.",
            app,
            f"SELECT error FROM \"{app}\" WHERE body = 'auth.token.refresh_failed'",
            org,
            period_min=15,
            frequency_min=15,
            silence_min=60,
        ),
    ]
