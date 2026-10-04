from whoopmon.provision.alerts import build_alerts
from whoopmon.provision.dashboards import build_all


def test_dashboards_fit_the_grid_and_have_unique_ids():
    dashboards = build_all()
    assert len(dashboards) == 4
    for dash in dashboards:
        panels = dash["tabs"][0]["panels"]
        assert len({p["id"] for p in panels}) == len(panels)
        for p in panels:
            assert p["layout"]["x"] + p["layout"]["w"] <= 48, p["title"]
            assert p["queries"][0]["query"].startswith("SELECT")


def test_health_queries_use_latest_version():
    for dash in build_all()[:3]:
        for p in dash["tabs"][0]["panels"]:
            assert "ROW_NUMBER()" in p["queries"][0]["query"], p["title"]


def test_alert_names_unique():
    names = [a["name"] for a in build_alerts("whoop_", "default")]
    assert len(names) == len(set(names))
