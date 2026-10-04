from tests.fixtures.sample import make_days
from whoopmon.transform.flatten import recovery_zone, to_row, tombstone
from whoopmon.whoop.resources import CYCLE, RECOVERY, SLEEP, WORKOUT

DATA = make_days(3)


def test_sleep_row_is_flat_with_hours_and_wake_day():
    rec = DATA["sleep"][0]
    row = to_row(SLEEP, rec)
    assert "score" not in row
    assert row["score_stage_summary_total_rem_sleep_time_milli"] > 0
    hours = row["score_stage_summary_total_rem_sleep_time_hours"]
    assert hours == round(row["score_stage_summary_total_rem_sleep_time_milli"] / 3_600_000, 3)
    # Night is labelled by its wake-up day in the member's timezone (+05:30).
    assert row["local_date"] == "".join(rec["end"][:10]) or row["local_date"] > rec["start"][:10]
    assert row["record_key"] == f"{rec['id']}@{rec['updated_at']}"
    assert row["deleted"] is False


def test_timestamp_is_event_time_in_micros():
    rec = DATA["cycle"][0]
    row = to_row(CYCLE, rec)
    from whoopmon.transform.flatten import parse_ts

    assert row["_timestamp"] == int(parse_ts(rec["start"]).timestamp() * 1_000_000)
    assert row["step_count"] == rec["step_count"]


def test_recovery_keyed_by_cycle_with_zone():
    rec = DATA["recovery"][0]
    row = to_row(RECOVERY, rec)
    assert row["record_id"] == str(rec["cycle_id"])
    assert row["recovery_zone"] == recovery_zone(rec["score"]["recovery_score"])


def test_recovery_zones_match_whoop_bands():
    assert recovery_zone(33) == "red"
    assert recovery_zone(34) == "yellow"
    assert recovery_zone(66) == "yellow"
    assert recovery_zone(67) == "green"
    assert recovery_zone(None) is None


def test_workout_zone_columns():
    if not DATA["workout"]:
        return
    row = to_row(WORKOUT, DATA["workout"][0])
    assert "score_zone_durations_zone_two_milli" in row
    assert "score_zone_durations_zone_two_hours" in row


def test_pending_record_without_score_still_flattens():
    rec = {**DATA["sleep"][0], "score_state": "PENDING_SCORE"}
    rec.pop("score")
    row = to_row(SLEEP, rec)
    assert row["score_state"] == "PENDING_SCORE"


def test_tombstone():
    row = tombstone(SLEEP, "abc", "trace-1")
    assert row["deleted"] is True and row["record_id"] == "abc"
