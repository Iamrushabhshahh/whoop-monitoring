"""Create or update OpenObserve dashboards and alerts from code. Safe to re-run."""

import json
from pathlib import Path
from typing import Any

import httpx

from whoopmon.config import Settings
from whoopmon.observability import get_logger
from whoopmon.provision.alerts import ALERT_TEMPLATE, DESTINATION, TEMPLATE, build_alerts
from whoopmon.provision.dashboards import build_all

log = get_logger(__name__)

EXPORT_DIR = Path("openobserve")


class O2Admin:
    def __init__(self, settings: Settings) -> None:
        self.org = settings.o2_org
        self.http = httpx.Client(
            base_url=settings.o2_url,
            auth=(settings.o2_user, settings.o2_password.get_secret_value()),
            timeout=30,
        )

    def _check(self, resp: httpx.Response, what: str) -> Any:
        if resp.status_code >= 400:
            raise RuntimeError(f"{what}: HTTP {resp.status_code} {resp.text[:400]}")
        return resp.json() if resp.content else None

    # dashboards: match on title, replace in place
    def upsert_dashboard(self, dash: dict[str, Any]) -> str:
        listing = self._check(self.http.get(f"/api/{self.org}/dashboards"), "list dashboards")
        for item in listing.get("dashboards", []):
            body = next(
                (
                    item[k]
                    for k in sorted(item, reverse=True)
                    if k.startswith("v") and isinstance(item[k], dict)
                ),
                None,
            )
            if body and body.get("title") == dash["title"]:
                self._check(
                    self.http.delete(f"/api/{self.org}/dashboards/{body['dashboardId']}"),
                    f"delete dashboard {dash['title']}",
                )
        created = self._check(
            self.http.post(f"/api/{self.org}/dashboards", json=dash),
            f"create dashboard {dash['title']}",
        )
        new_id = (created.get("v5") or created.get("v8") or created).get("dashboardId", "?")
        log.info("provision.dashboard.upserted", title=dash["title"], dashboard_id=new_id)
        return str(new_id)

    def upsert_named(self, kind: str, payload: dict[str, Any]) -> None:
        base = f"/api/{self.org}/alerts/{kind}"
        name = payload["name"]
        exists = self.http.get(f"{base}/{name}").status_code == 200
        resp = (
            self.http.put(f"{base}/{name}", json=payload)
            if exists
            else self.http.post(base, json=payload)
        )
        self._check(resp, f"upsert {kind} {name}")
        log.info("provision.alert_resource.upserted", kind=kind, name=name, updated=exists)

    def upsert_alert(self, alert: dict[str, Any]) -> None:
        base = f"/api/v2/{self.org}/alerts"
        listing = self._check(self.http.get(base), "list alerts")
        existing = next(
            (a for a in listing.get("list", []) if a.get("name") == alert["name"]), None
        )
        if existing:
            alert_id = existing.get("alert_id") or existing.get("id")
            self._check(
                self.http.put(f"{base}/{alert_id}", json={**alert, "id": alert_id}),
                f"update alert {alert['name']}",
            )
        else:
            self._check(self.http.post(base, json=alert), f"create alert {alert['name']}")
        log.info("provision.alert.upserted", name=alert["name"], updated=bool(existing))


def export_files(prefix: str) -> None:
    """Write the generated JSON into the repo, so the UI import path also works."""
    for dash in build_all(prefix):
        path = EXPORT_DIR / "dashboards" / f"{dash['dashboardId']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dash, indent=2) + "\n")
    for alert in build_alerts(prefix, org="default"):
        path = EXPORT_DIR / "alerts" / f"{alert['name']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(alert, indent=2) + "\n")


def provision_all(settings: Settings, alert_url: str | None) -> None:
    """Dashboards always; alerts only when an alert URL is given.

    OpenObserve's SSRF guard rejects private hosts (host.docker.internal, 10.x, ...)
    unless the server runs with ZO_SKIP_SSRF_CHECKS=true. See docs/runbook.md.
    """
    admin = O2Admin(settings)
    prefix = settings.o2_stream_prefix
    export_files(prefix)
    for dash in build_all(prefix):
        admin.upsert_dashboard(dash)
    if not alert_url:
        log.warning("provision.alerts.skipped", reason="no alert URL")
        return
    admin.upsert_named("templates", TEMPLATE)
    admin.upsert_named(
        "destinations", {**DESTINATION, "url": alert_url, "template": ALERT_TEMPLATE}
    )
    for alert in build_alerts(prefix, settings.o2_org):
        admin.upsert_alert(alert)
    log.info("provision.completed")
