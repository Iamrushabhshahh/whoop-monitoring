"""Client + engine against a mocked WHOOP API and a mocked OpenObserve."""

import json
import time

import httpx
import pytest
import respx

from tests.fixtures.sample import BODY, make_days
from whoopmon.auth.oauth import TokenManager
from whoopmon.auth.token_store import TokenSet, TokenStore
from whoopmon.sinks.openobserve import OpenObserveSink
from whoopmon.sync.engine import SyncEngine
from whoopmon.sync.state import StateStore
from whoopmon.whoop.client import WhoopAPIError, WhoopClient

API = "https://api.prod.whoop.com/developer"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
O2 = "http://localhost:5080/api/default"
PATHS = {
    "cycle": "/v2/cycle",
    "recovery": "/v2/recovery",
    "sleep": "/v2/activity/sleep",
    "workout": "/v2/activity/workout",
}


@pytest.fixture
def store(settings):
    s = TokenStore(settings.token_file)
    s.save(TokenSet("access-1", "refresh-1", time.time() + 3600, "offline read:sleep", time.time()))
    return s


@pytest.fixture
def client(settings, store):
    c = WhoopClient(settings, TokenManager(settings, store), sleep=lambda _s: None)
    yield c
    c.close()


def _ingested(route):
    rows = []
    for call in route.calls:
        rows.extend(json.loads(call.request.content))
    return rows


@respx.mock
def test_pagination_follows_next_token(client):
    route = respx.get(f"{API}/v2/cycle").mock(
        side_effect=[
            httpx.Response(200, json={"records": [{"id": 1}], "next_token": "abc"}),
            httpx.Response(200, json={"records": [{"id": 2}], "next_token": None}),
        ]
    )
    assert [r["id"] for r in client.paginate("/v2/cycle")] == [1, 2]
    assert route.calls[1].request.url.params["nextToken"] == "abc"
    assert route.calls[0].request.url.params["limit"] == "25"


@respx.mock
def test_429_waits_then_succeeds(client):
    waits = []
    client._sleep = waits.append
    respx.get(f"{API}/v2/user/measurement/body").mock(
        side_effect=[
            httpx.Response(429, headers={"X-RateLimit-Reset": "7"}),
            httpx.Response(200, json=BODY),
        ]
    )
    assert client.get("/v2/user/measurement/body") == BODY
    assert waits == [8.0]


@respx.mock
def test_5xx_retries_then_fails(client):
    respx.get(f"{API}/v2/cycle").mock(return_value=httpx.Response(503))
    with pytest.raises(WhoopAPIError):
        client.get("/v2/cycle")


@respx.mock
def test_401_refreshes_token_once_and_rotates(client, store):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "access-2",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
                "scope": "offline",
            },
        )
    )
    api = respx.get(f"{API}/v2/user/measurement/body").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=BODY)]
    )
    assert client.get("/v2/user/measurement/body") == BODY
    assert api.calls[1].request.headers["Authorization"] == "Bearer access-2"
    assert store.load().refresh_token == "refresh-2"


@respx.mock
def test_engine_ships_once_and_reships_on_update(settings, client):
    data = make_days(5)
    for name, path in PATHS.items():
        respx.get(f"{API}{path}").mock(
            side_effect=lambda _req, n=name: httpx.Response(
                200, json={"records": data[n], "next_token": None}
            )
        )
    respx.get(f"{API}/v2/user/measurement/body").mock(return_value=httpx.Response(200, json=BODY))
    ingest = respx.post(url__regex=rf"{O2}/whoop_\w+/_json").mock(
        side_effect=lambda req: httpx.Response(
            200,
            json={
                "code": 200,
                "status": [{"name": "s", "successful": len(json.loads(req.content)), "failed": 0}],
            },
        )
    )

    engine = SyncEngine(settings, client, OpenObserveSink(settings), StateStore(settings.state_db))
    first = engine.run()
    assert first.ok
    assert first.resources["sleep"].shipped == 5
    assert first.resources["body"].shipped == 1

    second = engine.run()
    assert all(r.shipped == 0 for r in second.resources.values())

    # A record re-scored by WHOOP gets a new updated_at -> one new row.
    data["recovery"][0] = {**data["recovery"][0], "updated_at": "2099-01-01T00:00:00.000Z"}
    third = engine.run()
    assert third.resources["recovery"].shipped == 1
    assert len(_ingested(ingest)) == 5 * 3 + len(data["workout"]) + 1 + 1


@respx.mock
def test_engine_reports_failure_without_raising(settings, client):
    respx.get(f"{API}/v2/cycle").mock(return_value=httpx.Response(400))
    engine = SyncEngine(settings, client, OpenObserveSink(settings), StateStore(settings.state_db))
    result = engine.run()
    assert not result.ok and "400" in result.error
