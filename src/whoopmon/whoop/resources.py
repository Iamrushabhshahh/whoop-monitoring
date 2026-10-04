"""The WHOOP v2 resources this collector reads. One entry per OpenObserve stream."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Resource:
    name: str  # also the stream suffix: whoop_<name>
    path: str
    paginated: bool = True
    # Field used as the record's event time in OpenObserve.
    time_field: str = "start"
    # Field that identifies one record. Recovery has no `id`; it is keyed by cycle.
    id_field: str = "id"
    # Field whose local calendar day labels the record. WHOOP labels a night by its wake-up day.
    date_field: str | None = None


CYCLE = Resource("cycle", "/v2/cycle")
RECOVERY = Resource("recovery", "/v2/recovery", time_field="created_at", id_field="cycle_id")
SLEEP = Resource("sleep", "/v2/activity/sleep", date_field="end")
WORKOUT = Resource("workout", "/v2/activity/workout")
PROFILE = Resource("profile", "/v2/user/profile/basic", paginated=False, id_field="user_id")
BODY = Resource("body", "/v2/user/measurement/body", paginated=False, id_field="")

TIME_SERIES = (CYCLE, RECOVERY, SLEEP, WORKOUT)
SNAPSHOTS = (BODY,)
BY_NAME = {r.name: r for r in (*TIME_SERIES, PROFILE, BODY)}

# Webhook event prefix -> resource, and the single-record path for that resource.
WEBHOOK_RESOURCES = {
    "sleep": (SLEEP, "/v2/activity/sleep/{id}"),
    "workout": (WORKOUT, "/v2/activity/workout/{id}"),
    # v2 recovery webhooks carry the sleep UUID; read the sleep, then its cycle's recovery.
    "recovery": (RECOVERY, "/v2/activity/sleep/{id}"),
}
