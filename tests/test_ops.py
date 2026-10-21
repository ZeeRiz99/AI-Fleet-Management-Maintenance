"""FleetLog AI (ops/) tests: workflow core, store contract, offline router, LLM path with fakes. No network."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "processed" / "alerts.csv").exists(), reason="run the pipeline first")

from ops import brain, core, llm as L, registry as R, settings as S, store as ST, workshops as W  # noqa: E402

WED = datetime(2026, 10, 21, 10, 0, tzinfo=W.PKT)   # a Wednesday morning
MANAGER = "telegram:999"


class FakeRedis:
    """Just enough of Redis for the Upstash REST store (commands arrive as lists of strings)."""
    def __init__(self):
        self.kv, self.lists, self.sets = {}, {}, {}

    def __call__(self, cmd):
        op, *a = cmd
        if op == "GET":
            return self.kv.get(a[0])
        if op == "SET":
            if "NX" in a[2:] and a[0] in self.kv:
                return None
            self.kv[a[0]] = a[1]
            return "OK"
        if op == "DEL":
            for d in (self.kv, self.lists, self.sets):
                d.pop(a[0], None)
            return 1
        if op == "INCR":
            self.kv[a[0]] = str(int(self.kv.get(a[0], "0")) + 1)
            return int(self.kv[a[0]])
        if op == "EXPIRE":
            return 1
        if op == "RPUSH":
            self.lists.setdefault(a[0], []).append(a[1])
            return len(self.lists[a[0]])
        if op == "LRANGE":
            return ST._slice(self.lists.get(a[0], []), int(a[1]), int(a[2]))
        if op == "LTRIM":
            self.lists[a[0]] = ST._slice(self.lists.get(a[0], []), int(a[1]), int(a[2]))
            return "OK"
        if op == "SADD":
            self.sets.setdefault(a[0], set()).add(a[1])
            return 1
        if op == "SREM":
            self.sets.get(a[0], set()).discard(a[1])
            return 1
        if op == "SMEMBERS":
            return list(self.sets.get(a[0], set()))
        raise AssertionError(f"unexpected command {cmd}")


def make_store(kind):
    return ST.SQLiteStore() if kind == "sqlite" else ST.RedisStore("https://fake", "t", transport=FakeRedis())


@pytest.fixture
def env():
    cfg = S.Settings()
    cfg.manager_ids = [MANAGER]
    cfg.demo_mode = True
    return {"store": ST.SQLiteStore(), "settings": cfg, "chain": L.Chain([])}


def say(env, user, text, now=WED, **kw):
    return brain.handle(user, text, store=env["store"], settings=env["settings"], chain=kw.get("chain", env["chain"]),
                        now=now)


def low_risk_registration():
    return next(v["registration"] for v in R.all_vehicles() if v["risk_tier"] == "Low")


# ----------------------------------------------------------------------------- pieces
@pytest.mark.parametrize("raw", ["lea 22 2030", "LEA222030", "lea-22-2030", "Aaj LEA 22-2030 chala raha hoon"])
def test_registration_normalisation(raw):
    assert R.normalize(raw) == "LEA-22-2030"


def test_unknown_registration_is_not_a_vehicle():
    assert R.vehicle("XYZ-99-9999") is None


@pytest.mark.parametrize("text,cat,sev", [
    ("brake se awaaz aa rahi hai", "brakes", "medium"),
    ("engine bohat garam ho raha hai", "overheating", "high"),
    ("brake fail ho gaye", "brakes", "critical"),
    ("accident ho gaya", "accident", "critical"),
    ("tyre puncture", "tyres", "medium"),
    ("thori si awaaz", "engine", "low"),
])
def test_classify(text, cat, sev):
    assert core.classify(text) == (cat, sev)


def test_escalation_rule():
    assert core.should_escalate("high", "other", "Low")
    assert core.should_escalate("low", "engine", "High")
    assert core.should_escalate("medium", "brakes", "Low")
    assert not core.should_escalate("low", "brakes", "Low")
    assert not core.should_escalate("medium", "tyres", "Medium")


def test_slots_skip_sunday_past_and_too_soon():
    sat_eve = datetime(2026, 10, 24, 15, 30, tzinfo=W.PKT)  # Saturday 3:30 pm
    slots = W.candidate_slots("Lahore", sat_eve)
    starts = {s["start"] for s in slots}
    assert all(s.weekday() != 6 for s in starts)                     # no Sunday
    assert min(starts) >= sat_eve + timedelta(hours=1)               # >= 1 hour ahead
    assert min(starts).date() == datetime(2026, 10, 26).date()       # next slot is Monday morning
    assert {s["code"] for s in slots} == {"LHR1", "LHR2"}


def test_parse_slot():
    s = W.parse_slot("lhr1-20261021-14")
    assert s["slot_id"] == "LHR1-20261021-14" and s["city"] == "Lahore" and s["start"].hour == 14
    assert W.parse_slot("LHR1-20261021-10") is None   # not a slot hour
    assert W.parse_slot("ZZZ1-20261021-09") is None


# ----------------------------------------------------------------------------- store contract
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
def test_store_contract(kind):
    s = make_store(kind)
    assert s.get("k") is None and s.get("k", 5) == 5
    s.set("k", {"a": 1})
    assert s.get("k") == {"a": 1}
    assert s.set_nx("lock", "x") is True and s.set_nx("lock", "y") is False and s.get("lock") == "x"
    assert [s.incr("n"), s.incr("n")] == [1, 2]
    for i in range(5):
        s.rpush("l", i)
    assert s.lrange("l", -2, -1) == [3, 4]
    s.ltrim("l", -3, -1)
    assert s.lrange("l") == [2, 3, 4]
    s.sadd("set", "a"), s.sadd("set", "b"), s.srem("set", "a")
    assert s.smembers("set") == {"b"}
    s.delete("k")
    assert s.get("k") is None


def test_sqlite_ttl_expires(monkeypatch):
    s = ST.SQLiteStore()
    s.set("t", 1, ttl=10)
    real = ST.time.time
    monkeypatch.setattr(ST.time, "time", lambda: real() + 11)
    assert s.get("t") is None


# ----------------------------------------------------------------------------- driver flow (offline)
def test_identify_first(env):
    r = say(env, "telegram:1", "brake kharab hai")
    assert "driver LEA-22-2030" in r["reply"] and r["mode"] == "command"
    assert "manager" in r["reply"]


def test_bad_registration_rejected(env):
    r = say(env, "telegram:1", "driver XYZ-99-9999")
    assert "nahi mili" in r["reply"] and r["profile"].get("role") is None


def test_full_driver_flow_reaches_manager(env):
    say(env, "telegram:1", "driver lea 22 2030")
    r = say(env, "telegram:1", "brake se awaaz aa rahi hai")
    assert r["reply"].startswith("⚠️ Hifazat pehle")                     # safety advice first
    assert "ISS-1001" in r["reply"]
    alert = next(e for e in r["events"] if e["type"] == "notify")
    assert alert["to"] == [MANAGER] and "URGENT" in alert["text"] and alert["buttons"]
    assert any(e.get("name") == "issue.reported" for e in r["events"])
    slots = say(env, "telegram:1", "slot")
    assert "LHR1-20261021-11" in slots["reply"]
    b = say(env, "telegram:1", "pehla wala")
    assert "BK-2001" in b["reply"]
    assert any(e.get("name") == "booking.created" for e in b["events"])
    issue = core.get_record(env["store"], "issue", "ISS-1001")
    assert issue["status"] == "service_booked"
    assert core.get_record(env["store"], "booking", "BK-2001")["issue_id"] == "ISS-1001"


def test_low_risk_minor_issue_is_logged_not_escalated(env):
    say(env, "telegram:2", f"driver {low_risk_registration()}")
    r = say(env, "telegram:2", "tyre mein thori si hawa kam lagti hai")
    assert "subah ki report" in r["reply"]
    assert not [e for e in r["events"] if e["type"] == "notify"]
    assert core.get_record(env["store"], "issue", "ISS-1001")["escalated"] is False


def test_demo_mode_on_and_off(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    assert brain.DEMO_HEADER in say(env, "telegram:1", "brake se awaaz")["reply"]
    env["settings"].demo_mode = False
    assert brain.DEMO_HEADER not in say(env, "telegram:1", "brake se phir awaaz")["reply"]


def test_no_double_booking_and_booking_rules(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    say(env, "telegram:3", "driver LEA-22-2030")
    assert "BK-2001" in say(env, "telegram:1", "LHR1-20261021-14")["reply"]
    assert "kisi aur ne le liya" in say(env, "telegram:3", "LHR1-20261021-14")["reply"]       # taken
    assert "Islamabad" in say(env, "telegram:3", "ISB1-20261021-14")["reply"]                # wrong city
    assert "guzar chuka" in say(env, "telegram:3", "LHR1-20261020-14")["reply"]               # past
    assert "sunday" in say(env, "telegram:3", "LHR1-20261025-09")["reply"].lower()            # Sunday closed


def test_booking_lock_is_atomic_on_redis():
    s = make_store("redis")
    assert s.set_nx("slot:LHR1-20261021-09", "BK-2001") and not s.set_nx("slot:LHR1-20261021-09", "BK-2002")


def test_fuel_log_normal_and_abnormal(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    _, base = R.fuel_baselines()
    normal_km = round(base["LEA-22-2030"]["baseline_km_per_l"] * 40)
    ok = say(env, "telegram:1", f"40 litre diesel, {normal_km} km")
    assert "Normal" in ok["reply"] and not [e for e in ok["events"] if e["type"] == "notify"]
    bad = say(env, "telegram:1", "45 litre diesel, 200 km")
    assert "zyada" in bad["reply"] and any(e.get("name") == "fuel.abnormal" for e in bad["events"])


def test_fuel_km_from_odometer(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    say(env, "telegram:1", "shift meter 45000")
    r = say(env, "telegram:1", "fuel 40 litre meter 45340")
    assert "340 km" in r["reply"]


def test_pretrip_failures_become_issues(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    ctx = core.Ctx(env["store"], env["settings"], "telegram:1", core.load_profile(env["store"], "telegram:1"), WED)
    r = core.run_tool(ctx, "pretrip_check", {"brakes": False, "lights": False})
    assert r["failed"] == ["brakes", "lights"] and len(r["issues"]) == 2


def test_emergency_with_location(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    ctx = core.Ctx(env["store"], env["settings"], "telegram:1", core.load_profile(env["store"], "telegram:1"), WED)
    r = core.run_tool(ctx, "report_emergency", {"description": "accident ho gaya", "latitude": 31.5, "longitude": 74.3})
    alert = next(e for e in ctx.events if e.get("kind") == "emergency")
    assert "maps.google.com/?q=31.5,74.3" in alert["text"] and r["issue_id"].startswith("ISS-")


# ----------------------------------------------------------------------------- privacy and roles
def test_driver_cannot_use_manager_tools(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    ctx = core.Ctx(env["store"], env["settings"], "telegram:1", core.load_profile(env["store"], "telegram:1"), WED)
    for name in ("fleet_overview", "high_risk_vehicles", "plan_services", "open_issues", "approve_booking"):
        assert core.run_tool(ctx, name, {})["ok"] is False
    names = {t["name"] for t in core.tools_for("driver")}
    assert "high_risk_vehicles" not in names and "fuel_summary" not in names and "report_issue" in names


def test_restrict_manager(env):
    env["settings"].restrict_manager = True
    assert "sirf registered" in say(env, "telegram:5", "manager")["reply"]
    assert "Manager mode" in say(env, MANAGER, "manager")["reply"]


# ----------------------------------------------------------------------------- manager
def test_manager_actions_notify_driver(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    say(env, "telegram:1", "brake se awaaz")
    say(env, "telegram:1", "slot")
    say(env, "telegram:1", "1")
    say(env, MANAGER, "manager")
    r = say(env, MANAGER, "approve BK-2001")
    note = next(e for e in r["events"] if e["type"] == "notify")
    assert note["to"] == ["telegram:1"] and "confirm" in note["text"]
    assert core.get_record(env["store"], "booking", "BK-2001")["status"] == "confirmed"
    r = say(env, MANAGER, "reschedule BK-2001")
    assert env["store"].get("slot:LHR1-20261021-11") is None
    assert "approve" in say(env, MANAGER, "approve BK-2001")["reply"]       # rescheduled cannot be approved
    say(env, MANAGER, "resolve ISS-1001")
    assert core.get_record(env["store"], "issue", "ISS-1001")["status"] == "resolved"


def test_plan_services_stays_within_budget(env):
    say(env, MANAGER, "manager")
    ctx = core.Ctx(env["store"], env["settings"], MANAGER, {"role": "manager"}, WED)
    r = core.run_tool(ctx, "plan_services", {"budget_pkr": 100_000})
    assert 0 < r["spent_pkr"] <= 100_000
    assert r["saving_pkr"] == sum(v["net_saving_pkr"] for v in r["vehicles"])
    assert brain.router.parse_money("budget 1 lakh") == 100_000 and brain.router.parse_money("50k") == 50_000


def test_what_if_matches_the_saving_formula(env):
    ctx = core.Ctx(env["store"], env["settings"], MANAGER, {"role": "manager"}, WED)
    v = R.vehicle("BAB-21-6978")
    r = core.run_tool(ctx, "what_if", {"registrations": ["bab 21 6978", "NOPE-1"]})
    assert r["net_pkr"] == round(v["expected_loss_pkr"] * 0.6 - v["service_cost_pkr"])
    assert r["not_found"] == ["NOPE-1"]


def test_morning_brief_counts_live_records(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    say(env, "telegram:1", "brake se awaaz")
    say(env, MANAGER, "manager")
    r = say(env, MANAGER, "brief")
    assert "Driver reports (24 ghante): 1 (1 urgent)" in r["reply"] and "simulated" in r["reply"]


def test_manager_data_question_uses_existing_tools(env):
    say(env, MANAGER, "manager")
    assert "BAB-21-6978" in say(env, MANAGER, "kaun si gaariyan risk mein hain")["reply"]


# ----------------------------------------------------------------------------- limits and history
def test_rate_limit_and_length(env):
    env["settings"].max_msgs_per_user_day = 2
    say(env, "telegram:1", "/start")
    say(env, "telegram:1", "/start")
    assert "had poori" in say(env, "telegram:1", "/start")["reply"]
    assert "lamba" in say(env, "telegram:8", "x" * 3000)["reply"]


def test_history_excludes_demo_copy_and_is_trimmed(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    say(env, "telegram:1", "brake se awaaz")
    hist = env["store"].lrange("hist:telegram:1")
    assert hist and all(brain.DEMO_HEADER not in h["content"] for h in hist)
    for i in range(15):
        say(env, "telegram:1", f"mera score {i}")
    assert len(env["store"].lrange("hist:telegram:1")) == 2 * env["settings"].history_turns


# ----------------------------------------------------------------------------- LLM path (fake provider)
def scripted(responses, seen):
    def transport(url, headers, payload):
        seen.append(payload)
        return {"choices": [{"message": responses.pop(0)}]}
    return transport


def test_llm_agent_calls_role_tools_and_answers(env):
    seen = []
    replies = [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
            "name": "report_issue", "arguments": json.dumps({"description": "brake se awaaz", "category": "brakes",
                                                            "severity": "medium"})}}]},
        {"role": "assistant", "content": "Report ISS-1001 ban gayi. 'slot' likhein."},
    ]
    chain = L.Chain([L.Provider("fake", "https://fake/v1", "k", "m", transport=scripted(replies, seen))])
    say(env, "telegram:1", "driver LEA-22-2030")
    r = say(env, "telegram:1", "yaar brake ki awaaz aa rahi hai", chain=chain)
    assert r["mode"] == "llm:fake" and "ISS-1001" in r["reply"]
    tool_names = {t["function"]["name"] for t in seen[0]["tools"]}
    assert "report_issue" in tool_names and "high_risk_vehicles" not in tool_names   # driver-scoped tools
    assert seen[0]["messages"][0]["role"] == "system" and "FleetLog AI" in seen[0]["messages"][0]["content"]
    assert brain.DEMO_HEADER in r["reply"]                                           # demo copy for the visitor
    sent_to_model = json.dumps(seen[1]["messages"])
    assert brain.DEMO_HEADER not in sent_to_model                                    # never fed to the model


def test_llm_failure_falls_back_to_offline(env):
    def broken(url, headers, payload):
        raise OSError("network down")
    chain = L.Chain([L.Provider("gemini", "https://x", "k", "m", transport=broken),
                     L.Provider("groq", "https://y", "k", "m", transport=broken)])
    say(env, "telegram:1", "driver LEA-22-2030")
    r = say(env, "telegram:1", "brake se awaaz aa rahi hai", chain=chain)
    assert r["mode"] == "offline" and "ISS-1001" in r["reply"]


def test_llm_chain_uses_next_provider(env):
    seen = []
    def broken(url, headers, payload):
        raise OSError("quota")
    chain = L.Chain([L.Provider("gemini", "https://x", "k", "m", transport=broken),
                     L.Provider("groq", "https://y", "k", "m", transport=scripted(
                         [{"role": "assistant", "content": "Salam! Kya madad karun?"}], seen))])
    say(env, "telegram:1", "driver LEA-22-2030")
    r = say(env, "telegram:1", "salam bhai kaise ho", chain=chain)
    assert r["mode"] == "llm:groq" and r["reply"].startswith("Salam")


def test_llm_budget_exhausted_goes_offline(env):
    env["settings"].max_llm_calls_per_day = 0
    seen = []
    chain = L.Chain([L.Provider("fake", "https://f", "k", "m", transport=scripted([], seen))])
    say(env, "telegram:1", "driver LEA-22-2030")
    r = say(env, "telegram:1", "brake se awaaz", chain=chain)
    assert r["mode"] == "offline" and not seen


def test_from_env_builds_the_chain(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OLLAMA_BASE_URL", "OPS_LLM_PROVIDER",
              "OPS_GEMINI_MODEL", "OPS_GROQ_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert not L.from_env()
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("GROQ_API_KEY", "q")
    assert [p.name for p in L.from_env().providers] == ["gemini", "gemini", "groq"]   # two Gemini models by default
    monkeypatch.setenv("OPS_GEMINI_MODEL", " gemini-a , gemini-b,")
    assert [p.model for p in L.from_env().providers][:2] == ["gemini-a", "gemini-b"]
    monkeypatch.setenv("OPS_LLM_PROVIDER", "offline")
    assert not L.from_env()


# ----------------------------------------------------------------------------- phase 2 fixes from the live run
def test_filtered_slots_pehla_books_the_first_slot_shown(env):
    """Live bug: the LLM showed tomorrow-morning slots, driver said 'pehla wala', today's slot got booked."""
    say(env, "telegram:1", "driver LEA-22-2030")
    r = say(env, "telegram:1", "kal subah ka koi slot mil jayega?")
    assert r["reply"].splitlines()[1].startswith("1. Thu 22 Oct, 09:00 AM")
    assert "Wed 21 Oct" not in r["reply"] and "02:00 PM" not in r["reply"]
    say(env, "telegram:1", "pehla wala book kar do")
    assert core.get_record(env["store"], "booking", "BK-2001")["slot_id"] == "LHR1-20261022-09"


def test_slot_filters_on_the_tool(env):
    say(env, "telegram:1", "driver LEA-22-2030")
    ctx = core.Ctx(env["store"], env["settings"], "telegram:1", core.load_profile(env["store"], "telegram:1"), WED)
    r = core.run_tool(ctx, "find_service_slots", {"date": "2026-10-22", "part": "afternoon"})
    assert r["slots"] and all("20261022-14" in s["slot_id"] or "20261022-16" in s["slot_id"] for s in r["slots"])
    assert ctx.profile["last_offer"] == [s["slot_id"] for s in r["slots"]]
    none = core.run_tool(ctx, "find_service_slots", {"date": "2026-10-25"})            # a Sunday
    assert none["slots"] == [] and "Us waqt" in none["message"]


@pytest.mark.parametrize("text,want", [
    ("kal subah slot", {"date": "2026-10-22", "part": "morning"}),
    ("aaj shaam ko workshop", {"date": "2026-10-21", "part": "afternoon"}),
    ("parson ka slot", {"date": "2026-10-23"}),
    ("slot chahiye", {}),
])
def test_parse_when(env, text, want):
    from ops import router
    ctx = core.Ctx(env["store"], env["settings"], "telegram:1", {}, WED)
    assert router.parse_when(ctx, text) == want


def test_chain_rests_a_failing_provider():
    clock = [0.0]
    calls = []

    def busy(url, headers, payload):
        calls.append("busy")
        raise OSError("503")

    def ok(url, headers, payload):
        calls.append("ok")
        return {"choices": [{"message": {"content": "hi"}}]}

    chain = L.Chain([L.Provider("gemini", "u", "k", "a", transport=busy), L.Provider("gemini", "u", "k", "b", transport=ok)],
                    clock=lambda: clock[0])
    chain.chat([])
    chain.chat([])
    assert calls == ["busy", "ok", "ok"]                     # the busy model is not waited on twice
    clock[0] += L.Chain.COOLDOWN_S + 1
    chain.chat([])
    assert calls[-2:] == ["busy", "ok"]                      # retried after the cooldown


def test_llm_failure_after_a_tool_ran_does_not_duplicate_it(env):
    """The model reports the issue, then the provider dies: reply from the tool result, no second report."""
    calls = []

    def flaky(url, headers, payload):
        calls.append(1)
        if len(calls) > 1:
            raise OSError("503 busy")
        return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "report_issue", "arguments": json.dumps(
                {"description": "brake se awaaz", "category": "brakes", "severity": "medium"})}}]}}]}

    chain = L.Chain([L.Provider("gemini", "https://x", "k", "m", transport=flaky)])
    say(env, "telegram:1", "driver LEA-22-2030")
    r = say(env, "telegram:1", "brake se awaaz aa rahi hai", chain=chain)
    assert r["mode"] == "tools" and "ISS-1001" in r["reply"]
    assert [i["id"] for i in core.list_records(env["store"], "issue")] == ["ISS-1001"]


def test_plain_strips_markdown():
    assert brain.plain("## Report\n**Waqt:** kal\n* one\n- two\n__x__") == "Report\nWaqt: kal\n• one\n• two\nx"
