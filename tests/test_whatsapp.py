"""FleetLog AI phase 6: WhatsApp Cloud API channel. Meta's Graph API and the speech APIs are faked; no network."""
import hashlib
import hmac
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "processed" / "alerts.csv").exists(), reason="run the pipeline first")

from ops import brain, core, env as E, llm as L, settings as S, store as ST, workshops as W  # noqa: E402
from ops import whatsapp as WA  # noqa: E402

WED = datetime(2026, 10, 21, 10, 0, tzinfo=W.PKT)
DRIVER, MANAGER = "923001110000", "923009990000"


class FakeGraph:
    def __init__(self, fail_codes=None):
        self.calls, self.fail_codes = [], dict(fail_codes or {})   # recipient -> Graph error code

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        to = (payload or {}).get("to")
        if to in self.fail_codes and (payload or {}).get("type") != "template":
            return {"error": {"code": self.fail_codes[to], "message": "Re-engagement message"}}
        if method == "GET":
            return {"url": "https://lookaside.example/media/1", "mime_type": "audio/ogg; codecs=opus", "file_size": 2048}
        return {"messages": [{"id": "wamid.out"}]}

    def sent(self, to=None):
        return [p for m, _, p in self.calls if m == "POST" and p and p.get("to") and (to is None or p["to"] == to)]

    def texts(self, to):
        out = []
        for p in self.sent(to):
            if p["type"] == "text":
                out.append(p["text"]["body"])
            elif p["type"] == "interactive":
                out.append(p["interactive"]["body"]["text"])
        return out


class FakeSTT:
    def __init__(self, text):
        self.text, self.got = text, None

    def __bool__(self):
        return True

    def transcribe(self, audio, mime):
        self.got = (audio, mime)
        return self.text


@pytest.fixture
def wa():
    cfg = S.Settings()
    cfg.manager_ids, cfg.demo_mode = [], True
    graph = FakeGraph()
    client = WA.Client("tok", "PHONE1", transport=graph, fetch=lambda url: b"OGG:" + url.encode())
    store = ST.SQLiteStore()
    n = iter(range(1, 10_000))

    def send(frm, kind="text", value=None, stt=None):
        msg = {"from": frm, "id": f"wamid.{next(n)}", "timestamp": "1", "type": kind}
        if kind == "text":
            msg["text"] = {"body": value}
        elif kind == "interactive":
            msg["interactive"] = {"type": "button_reply", "button_reply": {"id": value, "title": "x"}}
        elif kind == "location":
            msg["location"] = {"latitude": value[0], "longitude": value[1]}
        elif kind == "audio":
            msg["audio"] = {"id": "MEDIA1", "mime_type": "audio/ogg; codecs=opus", "voice": True}
        return WA.handle_message(msg, client=client, store=store, settings=cfg, chain=L.Chain([]), transcriber=stt, now=WED)

    return {"graph": graph, "client": client, "store": store, "settings": cfg, "send": send}


def manager_on(wa):
    wa["send"](MANAGER, "text", "manager")
    wa["send"](MANAGER, "text", "subscribe")


def test_signature_and_handshake():
    body = b'{"object":"whatsapp_business_account"}'
    good = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    assert WA.verify_signature(body, good, "appsecret")
    assert not WA.verify_signature(body + b" ", good, "appsecret")              # re-serialised body fails
    assert not WA.verify_signature(body, good, "")                              # no secret: fail closed
    assert not WA.verify_signature(body, good[7:], "appsecret")                 # missing prefix
    ok = {"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "12345"}
    assert WA.verify_subscription(ok, "vt") == "12345"
    assert WA.verify_subscription({**ok, "hub.verify_token": "no"}, "vt") is None
    assert WA.verify_subscription(ok, "") is None


def test_text_flow_reaches_whatsapp_manager_with_buttons(wa):
    manager_on(wa)
    wa["send"](DRIVER, "text", "driver LEA-22-2030")
    assert wa["send"](DRIVER, "text", "brake fail ho gaye") == "text:offline"
    alert = [p for p in wa["graph"].sent(MANAGER) if p["type"] == "interactive"][-1]["interactive"]
    assert "ISS-1001" in alert["body"]["text"] and len(alert["body"]["text"]) <= WA.MAX_BUTTON_BODY
    buttons = alert["action"]["buttons"]
    assert 1 <= len(buttons) <= 3 and all(len(b["reply"]["title"]) <= 20 for b in buttons)
    assert wa["graph"].texts(DRIVER)[-1].startswith("⚠️ Hifazat pehle")


def test_read_receipt_and_typing_are_sent(wa):
    wa["send"](DRIVER, "text", "/start")
    first = wa["graph"].calls[0][2]
    assert first["status"] == "read" and first["typing_indicator"] == {"type": "text"}


def test_duplicate_message_id_is_processed_once(wa):
    msg = {"from": DRIVER, "id": "wamid.same", "type": "text", "text": {"body": "/start"}}
    kw = {"client": wa["client"], "store": wa["store"], "settings": wa["settings"], "chain": L.Chain([]), "now": WED}
    assert WA.handle_message(msg, **kw) == "text:command"
    assert WA.handle_message(msg, **kw) == "duplicate"                            # Meta retried the delivery


def test_button_reply_runs_the_action_for_managers_only(wa):
    manager_on(wa)
    for t in ("driver LEA-22-2030", "brake se awaaz", "slot", "1"):
        wa["send"](DRIVER, "text", t)
    assert wa["send"](DRIVER, "interactive", "approve BK-2001") == "button:not_manager"
    assert wa["send"](MANAGER, "interactive", "approve BK-2001").startswith("button:approve")
    assert core.get_record(wa["store"], "booking", "BK-2001")["status"] == "confirmed"
    assert "confirm" in wa["graph"].texts(DRIVER)[-1]


def test_voice_note_is_downloaded_and_transcribed(wa):
    wa["send"](DRIVER, "text", "driver LEA-22-2030")
    stt = FakeSTT("gaari garam ho rahi hai")
    assert wa["send"](DRIVER, "audio", stt=stt) == "voice:offline"
    assert stt.got == (b"OGG:https://lookaside.example/media/1", "audio/ogg")
    assert ("GET", "MEDIA1?phone_number_id=PHONE1", None) in wa["graph"].calls
    assert wa["graph"].texts(DRIVER)[-1].startswith('🎤 "gaari garam ho rahi hai"')


def test_location_after_emergency(wa):
    manager_on(wa)
    wa["send"](DRIVER, "text", "driver LEA-22-2030")
    wa["send"](DRIVER, "text", "accident ho gaya")
    wa["send"](DRIVER, "location", (31.5, 74.3))
    assert any("maps.google.com/?q=31.5,74.3" in t for t in wa["graph"].texts(MANAGER))


def test_long_text_with_buttons_is_split(wa):
    wa["client"].send(DRIVER, "x" * 1500, [{"text": f"B{i}", "action": f"call ISS-{i}"} for i in range(5)])
    sent = wa["graph"].sent(DRIVER)
    assert [p["type"] for p in sent] == ["text", "interactive", "interactive"]   # text, then 3 + 2 buttons
    assert [len(p["interactive"]["action"]["buttons"]) for p in sent[1:]] == [3, 2]


def test_outside_24h_window_falls_back_to_the_template(wa):
    graph = FakeGraph(fail_codes={MANAGER: WA.OUTSIDE_WINDOW})
    plain = WA.Client("tok", "P", transport=graph)
    with pytest.raises(WA.WhatsAppError):
        plain.send(MANAGER, "alert")                                               # no template: the error surfaces
    templ = WA.Client("tok", "P", transport=graph, template="fleetlog_alert")
    templ.send(MANAGER, "🔔 URGENT ISS-1001")
    t = graph.sent(MANAGER)[-1]
    assert t["type"] == "template" and t["template"]["name"] == "fleetlog_alert"
    assert t["template"]["components"][0]["parameters"][0]["text"] == "🔔 URGENT ISS-1001"


def test_payload_parsing_skips_status_updates():
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [
        {"field": "messages", "value": {"statuses": [{"id": "wamid.x", "status": "delivered"}]}},
        {"field": "messages", "value": {"contacts": [{"wa_id": DRIVER, "profile": {"name": "Ali"}}],
                                        "messages": [{"from": DRIVER, "id": "wamid.1", "type": "text",
                                                      "text": {"body": "hi"}}]}}]}]}
    got = list(WA.messages_in(payload))
    assert len(got) == 1 and got[0][1] == "Ali"


def test_manager_numbers_are_normalised(monkeypatch):
    monkeypatch.setenv("WHATSAPP_MANAGER_NUMBERS", "+92 300-999 0000, 923001110000")
    monkeypatch.setenv("TELEGRAM_MANAGER_CHAT_IDS", "")
    assert S.Settings().manager_ids == ["whatsapp:923009990000", "whatsapp:923001110000"]


# ----------------------------------------------------------------------------- web routes
@pytest.fixture
def web(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(E, "load", lambda *a, **k: [])
    web = importlib.import_module("ops.web")
    graph = FakeGraph()
    monkeypatch.setitem(web._BOT, "wa", WA.Client("tok", "P", transport=graph))
    monkeypatch.setitem(web._BOT, "bot", None)
    monkeypatch.setattr(brain, "_DEFAULT", {"settings": S.Settings(), "store": ST.SQLiteStore(), "chain": L.Chain([])})
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "appsecret")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "vt")
    return TestClient(web.app), graph


def test_webhook_routes(web):
    client, graph = web
    r = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "777"})
    assert r.status_code == 200 and r.text == "777"
    assert client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x",
                                                    "hub.challenge": "1"}).status_code == 403
    body = json.dumps({"entry": [{"changes": [{"field": "messages", "value": {"messages": [
        {"from": DRIVER, "id": "wamid.web1", "type": "text", "text": {"body": "/start"}}]}}]}]}).encode()
    assert client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 403
    sig = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    r = client.post("/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r.status_code == 200 and any("FleetLog AI" in t for t in graph.texts(DRIVER))
