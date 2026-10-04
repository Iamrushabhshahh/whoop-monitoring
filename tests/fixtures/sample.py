"""Synthetic WHOOP v2 records that follow the OpenAPI schemas. Not real data."""

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

TZ = "+05:30"
USER_ID = 10129


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_days(
    days: int = 14, end: datetime | None = None, seed: int = 7
) -> dict[str, list[dict[str, Any]]]:
    rnd = random.Random(seed)  # noqa: S311
    end = end or datetime.now(UTC).replace(hour=1, minute=0, second=0, microsecond=0)
    out: dict[str, list[dict[str, Any]]] = {"cycle": [], "recovery": [], "sleep": [], "workout": []}
    for i in range(days, 0, -1):
        wake = end - timedelta(days=i)
        bed = wake - timedelta(hours=rnd.uniform(6.2, 8.4))
        cycle_id = 900_000_000 + i
        sleep_id = str(uuid.UUID(int=rnd.getrandbits(128)))
        in_bed = int((wake - bed).total_seconds() * 1000)
        awake = rnd.randint(20, 60) * 60_000
        sws, rem = int(in_bed * 0.2), int(in_bed * 0.24)
        light = in_bed - awake - sws - rem
        out["sleep"].append(
            {
                "id": sleep_id,
                "cycle_id": cycle_id,
                "v1_id": None,
                "user_id": USER_ID,
                "created_at": _iso(wake + timedelta(minutes=5)),
                "updated_at": _iso(wake + timedelta(minutes=9)),
                "start": _iso(bed),
                "end": _iso(wake),
                "timezone_offset": TZ,
                "nap": False,
                "score_state": "SCORED",
                "score": {
                    "stage_summary": {
                        "total_in_bed_time_milli": in_bed,
                        "total_awake_time_milli": awake,
                        "total_no_data_time_milli": 0,
                        "total_light_sleep_time_milli": light,
                        "total_slow_wave_sleep_time_milli": sws,
                        "total_rem_sleep_time_milli": rem,
                        "sleep_cycle_count": rnd.randint(3, 6),
                        "disturbance_count": rnd.randint(5, 18),
                    },
                    "sleep_needed": {
                        "baseline_milli": 27_000_000,
                        "need_from_sleep_debt_milli": rnd.randint(0, 3_600_000),
                        "need_from_recent_strain_milli": rnd.randint(0, 1_800_000),
                        "need_from_recent_nap_milli": 0,
                    },
                    "respiratory_rate": round(rnd.uniform(14.5, 16.5), 2),
                    "sleep_performance_percentage": rnd.randint(62, 98),
                    "sleep_consistency_percentage": rnd.randint(55, 92),
                    "sleep_efficiency_percentage": round(rnd.uniform(84, 96), 1),
                },
            }
        )
        recovery = rnd.randint(18, 95)
        out["recovery"].append(
            {
                "cycle_id": cycle_id,
                "sleep_id": sleep_id,
                "user_id": USER_ID,
                "created_at": _iso(wake + timedelta(minutes=10)),
                "updated_at": _iso(wake + timedelta(minutes=11)),
                "score_state": "SCORED",
                "score": {
                    "user_calibrating": False,
                    "recovery_score": recovery,
                    "resting_heart_rate": rnd.randint(52, 64),
                    "hrv_rmssd_milli": round(rnd.uniform(38, 92), 3),
                    "spo2_percentage": round(rnd.uniform(94.5, 98.5), 2),
                    "skin_temp_celsius": round(rnd.uniform(33.1, 34.4), 2),
                },
            }
        )
        out["cycle"].append(
            {
                "id": cycle_id,
                "user_id": USER_ID,
                "created_at": _iso(wake),
                "updated_at": _iso(wake + timedelta(hours=23)),
                "start": _iso(wake),
                "end": _iso(wake + timedelta(hours=23, minutes=30)),
                "timezone_offset": TZ,
                "score_state": "SCORED",
                "score": {
                    "strain": round(rnd.uniform(6, 17), 4),
                    "kilojoule": round(rnd.uniform(8000, 12500), 1),
                    "average_heart_rate": rnd.randint(64, 78),
                    "max_heart_rate": rnd.randint(140, 182),
                },
                "step_count": rnd.randint(4000, 14000),
            }
        )
        if rnd.random() < 0.6:
            w_start = wake + timedelta(hours=rnd.uniform(1, 11))
            minutes = rnd.randint(25, 80)
            ms = minutes * 60_000
            out["workout"].append(
                {
                    "id": str(uuid.UUID(int=rnd.getrandbits(128))),
                    "v1_id": None,
                    "user_id": USER_ID,
                    "created_at": _iso(w_start + timedelta(minutes=minutes + 2)),
                    "updated_at": _iso(w_start + timedelta(minutes=minutes + 3)),
                    "start": _iso(w_start),
                    "end": _iso(w_start + timedelta(minutes=minutes)),
                    "timezone_offset": TZ,
                    "sport_name": rnd.choice(["running", "weightlifting", "cycling", "yoga"]),
                    "sport_id": 0,
                    "score_state": "SCORED",
                    "score": {
                        "strain": round(rnd.uniform(5, 15), 3),
                        "average_heart_rate": rnd.randint(110, 150),
                        "max_heart_rate": rnd.randint(150, 185),
                        "kilojoule": round(rnd.uniform(800, 3000), 1),
                        "percent_recorded": 100.0,
                        "distance_meter": round(rnd.uniform(0, 9000), 1),
                        "altitude_gain_meter": round(rnd.uniform(0, 80), 1),
                        "altitude_change_meter": 0.0,
                        "zone_durations": {
                            "zone_zero_milli": int(ms * 0.05),
                            "zone_one_milli": int(ms * 0.25),
                            "zone_two_milli": int(ms * 0.35),
                            "zone_three_milli": int(ms * 0.2),
                            "zone_four_milli": int(ms * 0.1),
                            "zone_five_milli": int(ms * 0.05),
                        },
                    },
                }
            )
    return out


BODY = {"height_meter": 1.75, "weight_kilogram": 72.4, "max_heart_rate": 192}
