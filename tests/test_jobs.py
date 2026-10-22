"""FleetLog AI phase 4: morning brief + reminders (idempotent daily job) and the cron endpoint."""
import importlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "processed" / "alerts.csv").exists(), reason="run the pipeline first")

from ops import brain, core, env as E, jobs, llm as L, registry as R, settings as S, store as ST  # noqa: E402
from ops import workshops as W  # noqa: E402

WED = datetime(2026, 10, 21, 10, 0, tzinfo=W.PKT)
THU_8AM = datetime(2026, 10, 22, 8, 0, tzinfo=W.PKT)


@pytest.fixture
def env():
    cfg = S.Settings()
    cfg.manager_ids, cfg.demo_mode = ["telegram:999"], True
    return {"store": ST.SQLiteStore(), "settings": cfg}


def say(env, user, text, now=WED):
    return brain.handle(user, text, store=env["store"], settings=env["settings"], chain=L.Chain([]), now=now)


def high_and_low():
    vs = R.all_vehicles()
    return (next(v["registration"] for v in vs if v["risk_tier"] == "High"),
            next(v["registration"] for v in vs if v["risk_tier"] == "Low"))


def notes(events, kind):
    return [e for e in events if e.get("type") == "notify" and e["kind"] == kind]


def test_brief_goes_to_managers_once_a_day(env):
    env["store"].sadd("subscribers", "telegram:5")
    summary, events = jobs.morning(env["store"], env["settings"], THU_8AM)
    brief = notes(events, "brief")
    assert summary["status"] == "ok" and summary["brief_to"] == 2
    assert brief[0]["to"] == ["telegram:999", "telegram:5"] and "subah ki report" in brief[0]["text"]
    assert any(e.get("name") == "brief.sent" for e in events)
    again, events2 = jobs.morning(env["store"], env["settings"], THU_8AM + timedelta(minutes=40))   # cron fired twice
    assert again["status"] == "already_ran" and events2 == []
    assert jobs.morning(env["store"], env["settings"], THU_8AM + timedelta(days=1))[0]["status"] == "ok"


def test_driver_with_a_visit_today_is_reminded(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    say(env, "telegram:1", "brake se awaaz")
    say(env, "telegram:1", "kal subah slot")
    say(env, "telegram:1", "pehla wala")                                     # Thu 22 Oct 09:00
    say(env, "telegram:999", "manager")
    say(env, "telegram:999", "approve BK-2001")
    _, events = jobs.morning(env["store"], env["settings"], THU_8AM)
    visit = notes(events, "reminder")
    assert visit and visit[0]["to"] == ["telegram:1"] and "09:00 AM" in visit[0]["text"] and "confirm hai" in visit[0]["text"]
    assert "Approval ka intezar" not in notes(events, "brief")[0]["text"]       # approved: nothing pending


def test_pending_approval_shows_in_the_brief(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    say(env, "telegram:1", "slot")
    say(env, "telegram:1", "1")
    _, events = jobs.morning(env["store"], env["settings"], THU_8AM)
    assert "Approval ka intezar: 1 (BK-2001)" in notes(events, "brief")[0]["text"]


def test_service_nudge_only_for_high_risk_unbooked_weekly(env):
    high, low = high_and_low()
    say(env, "telegram:1", f"driver {high}")
    say(env, "telegram:2", f"driver {low}")
    _, events = jobs.morning(env["store"], env["settings"], THU_8AM)
    nudges = [e for e in notes(events, "reminder") if "due hai" in e["text"]]
    assert [e["to"] for e in nudges] == [["telegram:1"]] and high in nudges[0]["text"]
    _, events = jobs.morning(env["store"], env["settings"], THU_8AM + timedelta(days=1))
    assert not [e for e in notes(events, "reminder") if "due hai" in e["text"]]          # once a week
    _, events = jobs.morning(env["store"], env["settings"], THU_8AM + timedelta(days=8))
    assert [e for e in notes(events, "reminder") if "due hai" in e["text"]]


def test_booked_high_risk_driver_is_not_nudged(env):
    high, _ = high_and_low()
    say(env, "telegram:1", f"driver {high}")
    say(env, "telegram:1", "kal subah slot")                                  # Thu 09:00, after the 08:00 job
    say(env, "telegram:1", "1")
    _, events = jobs.morning(env["store"], env["settings"], THU_8AM)
    assert not [e for e in notes(events, "reminder") if "due hai" in e["text"]]


@pytest.fixture
def client(monkeypatch, env):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(E, "load", lambda *a, **k: [])
    web = importlib.import_module("ops.web")
    monkeypatch.setattr(brain, "_DEFAULT", {"settings": env["settings"], "store": env["store"], "chain": L.Chain([])})
    monkeypatch.setitem(web._BOT, "bot", None)
    return TestClient(web.app)


def test_cron_endpoint_needs_the_secret(client, monkeypatch):
    assert client.get("/cron/morning").status_code == 401                         # no secret configured: closed
    monkeypatch.setenv("CRON_SECRET", "c" * 20)
    assert client.get("/cron/morning", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/cron/morning", headers={"Authorization": "Bearer " + "c" * 20})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert client.get("/cron/morning", headers={"Authorization": "Bearer " + "c" * 20}).json()["status"] == "already_ran"
