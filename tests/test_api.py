"""FastAPI backend tests (runs the real model on a temporary copy of the database)."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["FLEET_RUNTIME_DIR"] = tempfile.mkdtemp(prefix="fleet_api_test_")  # before the api package is imported

import config as C  # noqa: E402
from db import query  # noqa: E402

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "fleet.db").exists(), reason="run src/run_pipeline.py first")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    original_db = C.DB_PATH
    with TestClient(app) as c:
        yield c
    C.DB_PATH = original_db  # other test modules read the committed database


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "fleet123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health_is_public(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["vehicles"] == 58


def test_auth_required_and_bad_login(client):
    assert client.get("/api/v1/dashboard").status_code == 401
    assert client.get("/api/v1/dashboard", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "", "password": "x"}).status_code == 422


def test_me(client, auth):
    assert client.get("/api/v1/auth/me", headers=auth).json() == {"username": "admin", "full_name": "Fleet Manager", "role": "admin"}


def test_dashboard_is_consistent(client, auth):
    d = client.get("/api/v1/dashboard", headers=auth).json()
    assert d["fleet"]["total_vehicles"] == 58 and d["fleet"]["drivers"] == 24
    assert d["risk"]["high"] + d["risk"]["medium"] + d["risk"]["low"] == 58
    assert d["health"]["good"] + d["health"]["watch"] + d["health"]["critical"] == 58
    assert d["fleet"]["critical"] == d["risk"]["high"]
    assert len(d["risk"]["top"]) == 5 and d["risk"]["top"][0]["risk_probability"] >= d["risk"]["top"][-1]["risk_probability"]
    assert len(d["fuel"]["monthly"]) == 12 and d["recent_alerts"]
    expected = query("SELECT SUM(fuel_cost_pkr) c FROM trips WHERE trip_date > '2025-12-01'").c[0]
    assert abs(d["fuel"]["cost"] - expected) <= 1


def test_vehicle_list_filters_and_sorting(client, auth):
    rows = client.get("/api/v1/vehicles", headers=auth).json()
    assert len(rows) == 58
    risks = [r["risk_probability"] for r in rows]
    assert risks == sorted(risks, reverse=True)
    high = client.get("/api/v1/vehicles", params={"risk_tier": "High"}, headers=auth).json()
    assert high and all(r["risk_tier"] == "High" for r in high)
    reg = rows[0]["registration"]
    assert [r["registration"] for r in client.get("/api/v1/vehicles", params={"search": reg}, headers=auth).json()] == [reg]
    assert all(0 <= r["health_score"] <= 100 for r in rows)


def test_vehicle_detail_explains_prediction(client, auth):
    vid = client.get("/api/v1/vehicles", headers=auth).json()[0]["id"]
    d = client.get(f"/api/v1/vehicles/{vid}", headers=auth).json()
    p = d["prediction"]
    assert d["registration"] in p["explanation"] and "%" in p["explanation"]
    assert p["factors"] and {"label", "display", "impact", "direction"} <= set(p["factors"][0])
    assert p["recommendation"]["service"] in C.SERVICES
    assert len(d["upcoming_services"]) == len(C.SERVICES)
    assert d["maintenance"]["history"] and d["recent_trips"]
    assert client.get("/api/v1/vehicles/9999", headers=auth).status_code == 404


def test_validation_errors(client, auth):
    assert client.get("/api/v1/fuel/summary", params={"days": 0}, headers=auth).status_code == 422
    assert client.get("/api/v1/vehicles", params={"risk_tier": "Extreme"}, headers=auth).status_code == 422
    bad = client.post("/api/v1/maintenance", json={"vehicle_id": 1, "service": "Car Wash"}, headers=auth)
    assert bad.status_code == 422 and "unknown service" in bad.text


def test_maintenance_schedule(client, auth):
    overdue = client.get("/api/v1/maintenance/schedule", params={"status": "overdue"}, headers=auth).json()
    assert overdue and all(i["status"] == "overdue" and i["overdue_pct"] >= 0 for i in overdue)
    soon = client.get("/api/v1/maintenance/schedule", params={"status": "due_soon"}, headers=auth).json()
    days = [i["due_in_days"] for i in soon if i["due_in_days"] is not None]
    assert days == sorted(days)
    summary = client.get("/api/v1/maintenance/summary", headers=auth).json()
    assert summary["overdue"] >= len(overdue[:100]) and 0 < summary["breakdown_share"] < 1
    hist = client.get("/api/v1/maintenance/history", params={"kind": "Breakdown", "limit": 5}, headers=auth).json()
    assert len(hist["items"]) == 5 and all(i["kind"] == "Breakdown" for i in hist["items"])


def test_alert_read_flow(client, auth):
    first = client.get("/api/v1/alerts", headers=auth).json()
    assert first["items"] and first["unread"] == first["total"]
    cats = {a["category"] for a in first["items"]}
    assert {"high_risk", "maintenance_overdue"} <= cats
    target = first["items"][0]["id"]
    assert client.post(f"/api/v1/alerts/{target}/read", headers=auth).status_code == 200
    after = client.get("/api/v1/alerts", headers=auth).json()
    assert after["unread"] == first["unread"] - 1
    assert next(a for a in after["items"] if a["id"] == target)["read"] is True
    assert client.post("/api/v1/alerts/nope:0/read", headers=auth).status_code == 404
    client.post("/api/v1/alerts/read-all", headers=auth)
    assert client.get("/api/v1/alerts", headers=auth).json()["unread"] == 0


def test_fuel_summary_and_anomalies(client, auth):
    s = client.get("/api/v1/fuel/summary", params={"days": 7}, headers=auth).json()
    expected = query("SELECT SUM(fuel_cost_pkr) c FROM trips WHERE trip_date > '2025-12-24'").c[0]
    assert abs(s["totals"]["cost"] - expected) <= 1 and s["by_vehicle"] and s["by_depot"]
    a = client.get("/api/v1/fuel/anomalies", params={"days": 90}, headers=auth).json()
    assert a["count"] > 0 and "km/l" in a["items"][0]["explanation"]
    assert all(i["actual_km_per_l"] < i["baseline_km_per_l"] for i in a["items"])


def test_live_fuel_check(client, auth):
    vid = 1
    base = client.post("/api/v1/ai/fuel-check", json={"vehicle_id": vid, "distance_km": 200, "fuel_litres": 1}, headers=auth).json()
    normal_litres = round(200 / base["baseline_km_per_l"], 1)
    ok = client.post("/api/v1/ai/fuel-check", json={"vehicle_id": vid, "distance_km": 200, "fuel_litres": normal_litres}, headers=auth).json()
    assert ok["verdict"] == "Normal" and not ok["abnormal"]
    bad = client.post("/api/v1/ai/fuel-check", json={"vehicle_id": vid, "distance_km": 200, "fuel_litres": normal_litres * 1.6}, headers=auth).json()
    assert bad["verdict"] == "Abnormal" and bad["excess_litres"] > 0 and "more than expected" in bad["explanation"]


def test_drivers_and_trips(client, auth):
    d = client.get("/api/v1/drivers", headers=auth).json()
    assert len(d["items"]) == 24 and all(0 <= x["safety_score"] <= 100 and 0 <= x["performance_score"] <= 100 for x in d["items"])
    scores = [x["safety_score"] for x in d["items"]]
    assert scores == sorted(scores, reverse=True)
    one = client.get(f"/api/v1/drivers/{d['items'][0]['id']}", headers=auth).json()
    assert one["recent_trips"] and one["safety_formula"]
    t = client.get("/api/v1/trips", params={"limit": 5}, headers=auth).json()
    assert len(t["items"]) == 5 and t["total"] > 40000 and t["active"] == 0
    assert all(i["duration_min"] > 0 for i in t["items"])


def test_recording_a_service_reruns_the_model_and_reset_restores(client, auth):
    top = client.get("/api/v1/vehicles", headers=auth).json()[0]
    before = client.get(f"/api/v1/vehicles/{top['id']}", headers=auth).json()["prediction"]
    service = before["recommendation"]["service"]
    r = client.post("/api/v1/maintenance", json={"vehicle_id": top["id"], "service": service, "notes": "test"}, headers=auth)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["record"]["service"] == service and body["record"]["date"] == C.END_DATE
    assert body["before"]["risk_probability"] == before["risk_probability"]
    assert body["after"]["risk_probability"] < body["before"]["risk_probability"]   # the real model reacts to the service
    sched = client.get("/api/v1/maintenance/schedule", params={"vehicle_id": top["id"]}, headers=auth).json()
    assert next(i for i in sched if i["service"] == service)["since_last_km"] == 0
    assert client.post("/api/v1/admin/reset-demo", headers=auth).status_code == 200
    restored = client.get(f"/api/v1/vehicles/{top['id']}", headers=auth).json()["prediction"]
    assert restored["risk_probability"] == before["risk_probability"]


def test_model_info(client, auth):
    m = client.get("/api/v1/ai/model", headers=auth).json()
    assert m["risk_model"]["metrics"][0]["model"] == "XGBoost" and m["explainability"] and "simulated" in m["data_note"]
