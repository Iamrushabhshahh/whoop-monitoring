"""Turn nested WHOOP records into flat rows for OpenObserve.

Rules:
- Nested objects become `parent_child` columns (score.stage_summary.x -> score_stage_summary_x).
- `_timestamp` (microseconds) is the record's event time, not the ingest time.
- `local_date` is the calendar day in the member's own timezone.
- Millisecond durations also get an hours column, for readable dashboards.
- `record_key` = id + updated_at. It identifies one version of one record.
"""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from whoopmon.whoop.resources import Resource

MS_PER_HOUR = 3_600_000


def _flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in obj.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, f"{name}_"))
        else:
            out[name] = value
    return out


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _tz(offset: str | None) -> timezone:
    if not offset:
        return UTC
    sign = -1 if offset.startswith("-") else 1
    hours, minutes = offset.lstrip("+-").split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))


def recovery_zone(score: float | None) -> str | None:
    """WHOOP's own bands: red 0-33, yellow 34-66, green 67-100."""
    if score is None:
        return None
    if score >= 67:
        return "green"
    if score >= 34:
        return "yellow"
    return "red"


def to_row(
    resource: Resource, record: dict[str, Any], observed_at: datetime | None = None
) -> dict[str, Any]:
    row = _flatten(record)
    row["record_type"] = resource.name
    row["deleted"] = False

    event_time_raw = record.get(resource.time_field)
    event_time = parse_ts(event_time_raw) if event_time_raw else (observed_at or datetime.now(UTC))
    row["_timestamp"] = int(event_time.timestamp() * 1_000_000)
    date_raw = record.get(resource.date_field) if resource.date_field else None
    date_time = parse_ts(date_raw) if date_raw else event_time
    row["local_date"] = date_time.astimezone(_tz(record.get("timezone_offset"))).date().isoformat()

    if start := record.get("start"):
        end = record.get("end")
        if end:
            row["duration_hours"] = round(
                (parse_ts(end) - parse_ts(start)).total_seconds() / 3600, 3
            )

    for key in [k for k in row if k.endswith("_milli") and isinstance(row[k], int | float)]:
        row[key.removesuffix("_milli") + "_hours"] = round(row[key] / MS_PER_HOUR, 3)

    if resource.name == "recovery":
        row["recovery_zone"] = recovery_zone(row.get("score_recovery_score"))

    if resource.id_field:
        record_id = record.get(resource.id_field)
        row["record_id"] = str(record_id) if record_id is not None else None
        row["record_key"] = f"{record_id}@{record.get('updated_at', '')}"
    return row


def tombstone(resource: Resource, record_id: str, trace_id: str) -> dict[str, Any]:
    """Row written when WHOOP sends a *.deleted webhook. Dashboards exclude these ids."""
    now = datetime.now(UTC)
    return {
        "_timestamp": int(now.timestamp() * 1_000_000),
        "record_type": resource.name,
        "record_id": record_id,
        "record_key": f"{record_id}@deleted",
        "deleted": True,
        "webhook_trace_id": trace_id,
    }
