"""Run every dashboard and alert query against a real OpenObserve.

Ships 30 days of synthetic records to throwaway `whooptest_*` streams, runs each query,
then deletes the streams. Skipped unless OpenObserve is reachable with the .env login.

    pytest -m integration
"""

import time

import httpx
import pytest

from tests.fixtures.sample import make_days
from whoopmon.config import Settings
from whoopmon.provision.alerts import build_alerts
from whoopmon.provision.dashboards import build_all
from whoopmon.transform.flatten import to_row
from whoopmon.whoop.resources import BY_NAME

# Unique per run: OpenObserve deletes streams asynchronously, so a reused name can be
# rejected with "stream is being deleted".
PREFIX = f"whooptest{int(time.time())}_"
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def o2():
    try:
        s = Settings()  # type: ignore[call-arg]
        client = httpx.Client(
            base_url=f"{s.o2_url}/api/{s.o2_org}",
            auth=(s.o2_user, s.o2_password.get_secret_value()),
            timeout=30,
        )
        client.get("/streams").raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"OpenObserve not reachable: {exc}")
    for name, records in make_days(30).items():
        rows = [to_row(BY_NAME[name], r) for r in records]
        client.post(f"/{PREFIX}{name}/_json", json=rows).raise_for_status()
    time.sleep(5)  # let the ingester flush
    yield client
    for name in ("cycle", "recovery", "sleep", "workout"):
        client.delete(f"/streams/{PREFIX}{name}", params={"type": "logs"})
    client.close()


def _queries():
    for dash in build_all(PREFIX)[:3]:  # collector-health reads the live app stream
        for panel in dash["tabs"][0]["panels"]:
            yield pytest.param(
                panel["queries"][0]["query"], id=f"{dash['dashboardId']}:{panel['title']}"
            )
    for alert in build_alerts(PREFIX, "default"):
        if alert["stream_name"].startswith(PREFIX):
            yield pytest.param(alert["query_condition"]["sql"], id=f"alert:{alert['name']}")


@pytest.mark.parametrize("sql", list(_queries()))
def test_query_runs(o2, sql):
    now = int(time.time() * 1_000_000)
    resp = o2.post(
        "/_search",
        json={
            "query": {
                "sql": sql,
                "start_time": now - 40 * 86_400_000_000,
                "end_time": now,
                "size": 10,
            }
        },
    )
    assert resp.status_code == 200, resp.text[:300]
