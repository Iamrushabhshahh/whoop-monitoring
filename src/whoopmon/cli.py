"""whoopmon command line.

whoopmon auth login      one-time browser login (stores tokens in data/)
whoopmon auth status     show token state and the connected profile
whoopmon sync            one incremental sync
whoopmon backfill        load history from a date
whoopmon run             sync every SYNC_INTERVAL_SECONDS (no HTTP server)
whoopmon serve           scheduler + :8080 /webhook /o2-alert /healthz (container default)
whoopmon provision       create dashboards, alert template, destination and alerts
whoopmon doctor          check config, WHOOP token and OpenObserve reachability
"""

import threading
import time
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import typer

from whoopmon.auth.callback_server import wait_for_callback
from whoopmon.auth.oauth import AuthError, TokenManager, authorize_url, exchange_code, new_state
from whoopmon.auth.token_store import TokenStore
from whoopmon.config import Settings, get_settings
from whoopmon.observability import bootstrap, get_logger, shutdown_telemetry
from whoopmon.sinks.openobserve import OpenObserveSink
from whoopmon.sync.engine import SyncEngine
from whoopmon.sync.scheduler import run_forever
from whoopmon.sync.state import StateStore
from whoopmon.whoop.client import WhoopClient

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
auth_app = typer.Typer(no_args_is_help=True, help="OAuth login and token state.")
app.add_typer(auth_app, name="auth")
log = get_logger("whoopmon.cli")


@dataclass
class Runtime:
    settings: Settings
    store: TokenStore
    tokens: TokenManager
    state: StateStore
    client: WhoopClient
    sink: OpenObserveSink
    engine: SyncEngine


@contextmanager
def runtime() -> Iterator[Runtime]:
    settings = get_settings()
    bootstrap(settings)
    key = (
        settings.token_encryption_key.get_secret_value() if settings.token_encryption_key else None
    )
    store = TokenStore(settings.token_file, key)
    tokens = TokenManager(settings, store)
    state = StateStore(settings.state_db)
    client = WhoopClient(settings, tokens)
    sink = OpenObserveSink(settings)
    try:
        yield Runtime(
            settings, store, tokens, state, client, sink, SyncEngine(settings, client, sink, state)
        )
    finally:
        client.close()
        sink.close()
        state.close()
        shutdown_telemetry()


# -- auth ---------------------------------------------------------------------


@auth_app.command("login")
def auth_login(
    no_browser: bool = typer.Option(False, help="Print the URL instead of opening a browser."),
) -> None:
    """Open the WHOOP consent page and store the tokens."""
    with runtime() as rt:
        state = new_state()
        url = authorize_url(rt.settings, state)
        redirect = urlparse(rt.settings.whoop_redirect_uri)
        typer.echo("Open this URL to connect WHOOP:\n\n  " + url + "\n")
        if not no_browser:
            webbrowser.open(url)
        result = wait_for_callback(
            redirect.hostname or "localhost", redirect.port or 80, redirect.path
        )
        if result.error or not result.code:
            log.error("auth.login.failed", error=result.error)
            raise typer.Exit(1)
        if result.state != state:
            log.error("auth.login.state_mismatch")
            raise typer.Exit(1)
        rt.store.save(exchange_code(rt.settings, result.code))
        profile = rt.client.get("/v2/user/profile/basic") or {}
        log.info("auth.login.completed", user_id=profile.get("user_id"))
        typer.echo(f"Connected WHOOP user {profile.get('user_id')}.")


@auth_app.command("status")
def auth_status() -> None:
    """Show token expiry and the connected user id."""
    with runtime() as rt:
        tokens = rt.store.load()
        if tokens is None:
            typer.echo("Not logged in. Run: whoopmon auth login")
            raise typer.Exit(1)
        left = int(tokens.expires_at - time.time())
        typer.echo(f"Access token expires in {left}s. Scopes: {tokens.scope}")
        profile = rt.client.get("/v2/user/profile/basic") or {}
        typer.echo(f"WHOOP user id: {profile.get('user_id')}")


@auth_app.command("logout")
def auth_logout(revoke: bool = typer.Option(True, help="Also revoke app access at WHOOP.")) -> None:
    """Delete local tokens (and revoke access at WHOOP by default)."""
    with runtime() as rt:
        if revoke and rt.store.load():
            token = rt.tokens.access_token()
            resp = httpx.delete(
                f"{rt.settings.whoop_api_base}/v2/user/access",
                headers={"Authorization": f"Bearer {token}"},
            )
            log.info("auth.access.revoked", status=resp.status_code)
        rt.store.clear()
        typer.echo("Local tokens removed.")


# -- sync ---------------------------------------------------------------------


def _print_result(result: object) -> None:
    for name, res in result.resources.items():  # type: ignore[attr-defined]
        typer.echo(
            f"  {name:<9} fetched={res.fetched:<5} shipped={res.shipped:<5} pending={res.pending}"
        )
    if result.error:  # type: ignore[attr-defined]
        typer.echo(f"FAILED: {result.error}", err=True)  # type: ignore[attr-defined]
        raise typer.Exit(1)


@app.command()
def sync() -> None:
    """Run one incremental sync."""
    with runtime() as rt:
        _print_result(rt.engine.run())


@app.command()
def backfill(
    since: datetime = typer.Option(..., "--since", formats=["%Y-%m-%d"], help="YYYY-MM-DD"),
) -> None:
    """Load all history from SINCE until now."""
    with runtime() as rt:
        _print_result(rt.engine.run(since=since.replace(tzinfo=UTC)))


@app.command()
def run() -> None:
    """Sync on a fixed interval until stopped."""
    with runtime() as rt:
        try:
            rt.tokens.access_token()
        except AuthError as exc:
            log.error("auth.missing", error=str(exc))
            raise typer.Exit(1) from exc
        run_forever(rt.engine, rt.settings.sync_interval_seconds)


@app.command()
def serve(
    with_scheduler: bool = typer.Option(True, help="Also run the interval sync."),
) -> None:
    """Run the webhook receiver (and the scheduler)."""
    import uvicorn

    from whoopmon.webhook.app import create_app

    with runtime() as rt:
        if with_scheduler:
            threading.Thread(
                target=_scheduler_thread, args=(rt,), daemon=True, name="scheduler"
            ).start()
        uvicorn.run(
            create_app(rt.settings, rt.engine, rt.state),
            host=rt.settings.webhook_host,
            port=rt.settings.webhook_port,
            log_config=None,
        )


def _scheduler_thread(rt: Runtime) -> None:
    while True:
        rt.engine.run()
        time.sleep(rt.settings.sync_interval_seconds)


# -- ops ----------------------------------------------------------------------


@app.command()
def provision(
    alert_url: str = typer.Option(
        "",
        help="Where OpenObserve sends alert notifications. Default: ALERT_WEBHOOK_URL.",
    ),
) -> None:
    """Create or update dashboards and alerts in OpenObserve."""
    from whoopmon.provision import provision_all

    settings = get_settings()
    bootstrap(settings)
    try:
        provision_all(settings, alert_url or settings.alert_webhook_url or None)
    finally:
        shutdown_telemetry()


@app.command()
def doctor() -> None:
    """Check that config, WHOOP and OpenObserve are all reachable."""
    with runtime() as rt:
        ok = True
        o2 = httpx.get(f"{rt.settings.o2_url}/healthz", timeout=5)
        typer.echo(f"OpenObserve {rt.settings.o2_url}: {o2.status_code}")
        ok &= o2.status_code == 200
        try:
            profile = rt.client.get("/v2/user/profile/basic") or {}
            typer.echo(f"WHOOP: connected as user {profile.get('user_id')}")
        except AuthError as exc:
            typer.echo(f"WHOOP: {exc}")
            ok = False
        for run_id, started, finished, outcome in rt.state.last_runs():
            typer.echo(f"  run {run_id} {started} -> {finished} {outcome}")
        raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
