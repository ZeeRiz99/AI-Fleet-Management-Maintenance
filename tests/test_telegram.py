"""FleetLog AI phase 2: Telegram channel, voice, location, webhook, .env loader. Telegram and the speech APIs are
faked; no network."""
import importlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "processed" / "alerts.csv").exists(), reason="run the pipeline first")

from ops import brain, core, env as E, llm as L, settings as S, speech as SP, store as ST  # noqa: E402
from ops import setup_telegram, telegram as T, workshops as W  # noqa: E402

WED = datetime(2026, 10, 21, 10, 0, tzinfo=W.PKT)
DRIVER, MANAGER = 111, 999


class FakeTelegram:
    """Records Bot API calls; answers the few methods the channel reads back."""
    def __init__(self, fail_for=()):
        self.calls, self.fail_for = [], set(fail_for)

    def __call__(self, method, params):
        self.calls.append((method, params))
        if str(params.get("chat_id")) in self.fail_for:
            return {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}
        if method == "getFile":
            return {"ok": True, "result": {"file_path": "voice/file_1.oga"}}
        return {"ok": True, "result": True}

    def sent(self, chat_id=None):
        return [p for m, p in self.calls
                if m == "sendMessage" and (chat_id is None or str(p["chat_id"]) == str(chat_id))]

    def methods(self):
        return [m for m, _ in self.calls]


class FakeTranscriber:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.audio = text, error, None

    def __bool__(self):
        return True

    def transcribe(self, audio, mime="audio/ogg"):
        self.audio = (audio, mime)
        if self.error:
            raise self.error
        return self.text


@pytest.fixture
def tg():
    cfg = S.Settings()
    cfg.manager_ids, cfg.demo_mode = [], True
    api = FakeTelegram()
    bot = T.Bot("123:test", transport=api, fetch=lambda path: b"OGG" + path.encode())
    store = ST.SQLiteStore()
    counter = iter(range(1, 10_000))

    def send(chat, kind="text", value=None, chat_type="private", transcriber=None, now=WED):
        msg = {"message_id": 1, "chat": {"id": chat, "type": chat_type}}
        if kind == "text":
            msg["text"] = value
        elif kind == "voice":
            msg["voice"] = {"file_id": "F1", "duration": 4, "mime_type": "audio/ogg", **(value or {})}
        elif kind == "location":
            msg["location"] = {"latitude": value[0], "longitude": value[1]}
        upd = {"update_id": next(counter), "message": msg}
        return T.handle_update(upd, bot=bot, store=store, settings=cfg, chain=L.Chain([]), transcriber=transcriber,
                               now=now)

    def press(chat, action, message_id=7):
        upd = {"update_id": next(counter), "callback_query": {
            "id": "cb1", "data": action, "from": {"id": chat},
            "message": {"message_id": message_id, "chat": {"id": chat, "type": "private"}}}}
        return T.handle_update(upd, bot=bot, store=store, settings=cfg, chain=L.Chain([]), now=WED)

    return {"api": api, "bot": bot, "store": store, "settings": cfg, "send": send, "press": press}


def subscribe_manager(tg):
    tg["send"](MANAGER, "text", "manager")
    tg["send"](MANAGER, "text", "subscribe")


# ----------------------------------------------------------------------------- .env loader
@pytest.mark.parametrize("raw,value", [
    ('"AQ.abc-123"', "AQ.abc-123"), ("'gsk_x'  # comment", "gsk_x"), ("plain   # comment", "plain"),
    ("# only a comment", ""), ("", ""), ('"has # hash"', "has # hash"), ("a=b", "a=b"),
])
def test_env_value_parsing(raw, value):
    assert E.parse_value(raw) == value


def test_env_load_never_overrides_the_host(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('export A_KEY="from-file"\nB_KEY=from-file\n# C_KEY=x\nEMPTY_KEY=   # nothing\n', encoding="utf-8")
    monkeypatch.setenv("A_KEY", "from-host")
    for k in ("B_KEY", "C_KEY", "EMPTY_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert E.load(f) == ["B_KEY"]
    import os
    assert os.environ["A_KEY"] == "from-host" and os.environ["B_KEY"] == "from-file"
    assert "C_KEY" not in os.environ and "EMPTY_KEY" not in os.environ


def test_make_secret_writes_once(tmp_path):
    f = tmp_path / ".env"
    f.write_text("TELEGRAM_BOT_TOKEN=\nTELEGRAM_WEBHOOK_SECRET=   # set me\nOTHER=1\n", encoding="utf-8")
    assert setup_telegram.make_secret(f) is True
    text = f.read_text(encoding="utf-8")
    secret = E.parse_value(text.split("TELEGRAM_WEBHOOK_SECRET=")[1].splitlines()[0])
    assert len(secret) >= 40 and set(secret) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
    assert "OTHER=1" in text and "TELEGRAM_BOT_TOKEN=" in text
    assert setup_telegram.make_secret(f) is False and f.read_text(encoding="utf-8") == text


# ----------------------------------------------------------------------------- messages
def test_text_message_gets_typing_and_reply(tg):
    assert tg["send"](DRIVER, "text", "/start") == "text:command"
    assert tg["api"].methods()[:2] == ["sendChatAction", "sendMessage"]
    assert "FleetLog AI" in tg["api"].sent(DRIVER)[-1]["text"]
    assert "parse_mode" not in tg["api"].sent(DRIVER)[-1]          # plain text: nothing to escape


def test_escalated_issue_reaches_subscribed_manager_with_buttons(tg):
    subscribe_manager(tg)
    tg["send"](DRIVER, "text", "driver LEA-22-2030")
    tg["send"](DRIVER, "text", "brake se awaaz aa rahi hai")
    alert = tg["api"].sent(MANAGER)[-1]
    assert "ISS-1001" in alert["text"]
    labels = [b["callback_data"] for row in alert["reply_markup"]["inline_keyboard"] for b in row]
    assert labels and all(len(x.encode()) <= 64 for x in labels)
    driver_reply = tg["api"].sent(DRIVER)[-1]
    assert driver_reply["text"].startswith("⚠️ Hifazat pehle") and "Demo" in driver_reply["text"]


def test_demo_copy_carries_buttons_but_driver_cannot_press_them(tg):
    tg["send"](DRIVER, "text", "driver LEA-22-2030")
    tg["send"](DRIVER, "text", "brake se awaaz aa rahi hai")
    reply = tg["api"].sent(DRIVER)[-1]
    assert reply.get("reply_markup")                                # demo: the visitor sees the manager's buttons
    assert tg["press"](DRIVER, "resolve ISS-1001") == "button:not_manager"
    answer = [p for m, p in tg["api"].calls if m == "answerCallbackQuery"][-1]
    assert answer["show_alert"] and "manager" in answer["text"]
    assert core.get_record(tg["store"], "issue", "ISS-1001")["status"] != "resolved"


def test_manager_button_approves_and_driver_is_told(tg):
    subscribe_manager(tg)
    for text in ("driver LEA-22-2030", "brake se awaaz", "slot", "pehla wala"):
        tg["send"](DRIVER, "text", text)
    assert "BK-2001" in tg["api"].sent(MANAGER)[-1]["text"]
    assert tg["press"](MANAGER, "approve BK-2001") == "button:approve"
    assert core.get_record(tg["store"], "booking", "BK-2001")["status"] == "confirmed"
    assert "confirm" in tg["api"].sent(DRIVER)[-1]["text"]
    assert ("editMessageReplyMarkup", {"chat_id": MANAGER, "message_id": 7, "reply_markup": {"inline_keyboard": []}}) \
        in tg["api"].calls                                         # one-shot buttons removed after use
    assert "approve nahi ho sakti" in (tg["press"](MANAGER, "approve BK-2001") and tg["api"].sent(MANAGER)[-1]["text"])


def test_call_button_keeps_the_keyboard(tg):
    subscribe_manager(tg)
    tg["send"](DRIVER, "text", "driver LEA-22-2030")
    tg["send"](DRIVER, "text", "accident ho gaya")
    n = len(tg["api"].calls)
    assert tg["press"](MANAGER, "call ISS-1001") == "button:call"
    assert "editMessageReplyMarkup" not in [m for m, _ in tg["api"].calls[n:]]


def test_duplicate_update_is_processed_once(tg):
    upd = {"update_id": 42, "message": {"message_id": 1, "chat": {"id": DRIVER, "type": "private"}, "text": "/start"}}
    kw = {"bot": tg["bot"], "store": tg["store"], "settings": tg["settings"], "chain": L.Chain([]), "now": WED}
    assert T.handle_update(upd, **kw) == "text:command"
    assert T.handle_update(upd, **kw) == "duplicate"
    assert len(tg["api"].sent()) == 1


def test_group_chats_are_ignored(tg):
    assert tg["send"](-100123, "text", "manager", chat_type="supergroup") == "ignored:not_private"
    assert tg["api"].calls == []


def test_blocked_target_does_not_break_the_driver_reply(tg):
    subscribe_manager(tg)
    tg["api"].fail_for.add(str(MANAGER))
    tg["send"](DRIVER, "text", "driver LEA-22-2030")
    assert tg["send"](DRIVER, "text", "brake fail ho gaye") == "text:offline"
    assert "ISS-1001" in tg["api"].sent(DRIVER)[-1]["text"]


def test_internal_error_sends_an_apology(tg, monkeypatch):
    monkeypatch.setattr(brain, "handle", lambda *a, **k: 1 / 0)
    assert tg["send"](DRIVER, "text", "hello") == "error"
    assert tg["api"].sent(DRIVER)[-1]["text"] == T.SORRY


def test_long_reply_is_split_under_the_limit(tg):
    tg["bot"].send(DRIVER, ("line of text\n" * 800).strip(), buttons=[{"text": "OK", "action": "call ISS-1"}])
    parts = tg["api"].sent(DRIVER)
    assert len(parts) == 3 and all(len(p["text"]) <= T.MAX_TEXT for p in parts)
    assert "reply_markup" in parts[-1] and "reply_markup" not in parts[0]


def test_bot_call_raises_on_api_error():
    bot = T.Bot("t", transport=lambda m, p: {"ok": False, "error_code": 401, "description": "Unauthorized"})
    with pytest.raises(T.TelegramError, match="401"):
        bot.call("getMe")


# ----------------------------------------------------------------------------- voice
def test_voice_note_is_transcribed_then_handled(tg):
    tg["send"](DRIVER, "text", "driver LEA-22-2030")
    stt = FakeTranscriber("brake se awaaz aa rahi hai")
    assert tg["send"](DRIVER, "voice", transcriber=stt) == "voice:offline"
    assert stt.audio == (b"OGGvoice/file_1.oga", "audio/ogg")
    reply = tg["api"].sent(DRIVER)[-1]["text"]
    assert reply.startswith('🎤 "brake se awaaz aa rahi hai"') and "ISS-1001" in reply


@pytest.mark.parametrize("voice,stt,expect", [
    ({"duration": 600}, FakeTranscriber("x"), "chhota"),
    ({}, FakeTranscriber(error=SP.SpeechUnavailable("quota")), "samajh nahi"),
    ({}, SP.Transcriber([]), "set up nahi"),
])
def test_voice_problems_get_a_clear_answer(tg, voice, stt, expect):
    assert tg["send"](DRIVER, "voice", voice, transcriber=stt) == "voice:failed"
    assert expect in tg["api"].sent(DRIVER)[-1]["text"]


def test_gemini_transcriber_request_and_parse():
    seen = {}

    def transport(url, data, headers):
        seen.update(url=url, body=json.loads(data), headers=headers)
        return {"candidates": [{"content": {"parts": [{"text": " gaari garam ho rahi hai "}]}}]}

    out = SP.Gemini("k", "gemini-x", transport=transport).transcribe(b"abc", "audio/ogg")
    assert out == "gaari garam ho rahi hai"
    assert seen["url"].endswith("/models/gemini-x:generateContent") and seen["headers"]["x-goog-api-key"] == "k"
    inline = seen["body"]["contents"][0]["parts"][1]["inline_data"]
    assert inline == {"mime_type": "audio/ogg", "data": "YWJj"}


def test_groq_whisper_multipart_and_chain_fallback():
    seen = {}

    def groq(url, data, headers):
        seen.update(url=url, data=data, headers=headers)
        return {"text": "brake kharab hai"}

    def broken(url, data, headers):
        raise OSError("quota")

    chain = SP.Transcriber([SP.Gemini("k", "m", transport=broken), SP.GroqWhisper("q", "whisper-x", transport=groq)])
    assert chain.transcribe(b"\x00audio", "audio/ogg") == "brake kharab hai" and chain.last_used == "groq"
    assert seen["url"].endswith("/audio/transcriptions") and seen["headers"]["Authorization"] == "Bearer q"
    assert b'name="model"\r\n\r\nwhisper-x' in seen["data"] and b'filename="voice.ogg"' in seen["data"]
    assert b"\x00audio" in seen["data"]


def test_speech_from_env(monkeypatch):
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OPS_GEMINI_STT_MODEL", "OPS_GEMINI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert not SP.from_env()
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("GROQ_API_KEY", "q")
    assert [e.name for e in SP.from_env().engines] == ["gemini", "gemini", "groq"]
    monkeypatch.setenv("OPS_GEMINI_STT_MODEL", "gemini-stt")
    assert [e.model for e in SP.from_env().engines] == ["gemini-stt", "whisper-large-v3-turbo"]


# ----------------------------------------------------------------------------- location
def test_location_after_emergency_goes_to_manager(tg):
    subscribe_manager(tg)
    tg["send"](DRIVER, "text", "driver LEA-22-2030")
    tg["send"](DRIVER, "text", "accident ho gaya")
    assert "location share nahi hui" in tg["api"].sent(MANAGER)[-1]["text"]
    assert tg["send"](DRIVER, "location", (31.52, 74.35), now=WED + timedelta(minutes=5)) == "location:command"
    live = tg["api"].sent(MANAGER)[-1]
    assert "maps.google.com/?q=31.52,74.35" in live["text"] and "ISS-1001" in live["text"]
    assert "manager ko bhej di" in tg["api"].sent(DRIVER)[-1]["text"]


def test_location_shared_first_is_attached_to_the_emergency(tg):
    subscribe_manager(tg)
    tg["send"](DRIVER, "text", "driver LEA-22-2030")
    tg["send"](DRIVER, "location", (24.86, 67.0))
    assert "Location mil gayi" in tg["api"].sent(DRIVER)[-1]["text"]
    tg["send"](DRIVER, "text", "accident ho gaya", now=WED + timedelta(minutes=10))
    assert "maps.google.com/?q=24.86,67.0" in tg["api"].sent(MANAGER)[-1]["text"]


def test_old_location_is_not_reused(tg):
    subscribe_manager(tg)
    tg["send"](DRIVER, "text", "driver LEA-22-2030")
    tg["send"](DRIVER, "location", (24.86, 67.0))
    tg["send"](DRIVER, "text", "accident ho gaya", now=WED + timedelta(hours=2))
    assert "location share nahi hui" in tg["api"].sent(MANAGER)[-1]["text"]


# ----------------------------------------------------------------------------- webhook
@pytest.fixture
def web(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(E, "load", lambda *a, **k: [])               # never read the real .env in tests
    web = importlib.import_module("ops.web")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setitem(web._BOT, "bot", T.Bot("123:test", transport=FakeTelegram()))
    monkeypatch.setattr(brain, "_DEFAULT", {"settings": S.Settings(), "store": ST.SQLiteStore(), "chain": L.Chain([])})
    seen = []
    monkeypatch.setattr(T, "handle_update", lambda update, bot: seen.append(update) or "text:command")
    return TestClient(web.app), seen


def test_webhook_rejects_wrong_or_missing_secret(web, monkeypatch):
    client, seen = web
    update = {"update_id": 1, "message": {"chat": {"id": 1, "type": "private"}, "text": "hi"}}
    assert client.post("/webhooks/telegram", json=update).status_code == 403
    assert client.post("/webhooks/telegram", json=update,
                       headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}).status_code == 403
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")                 # fail closed without a secret
    assert client.post("/webhooks/telegram", json=update,
                       headers={"X-Telegram-Bot-Api-Secret-Token": ""}).status_code == 403
    assert seen == []


def test_webhook_accepts_the_secret_and_processes(web):
    client, seen = web
    update = {"update_id": 1, "message": {"chat": {"id": 1, "type": "private"}, "text": "hi"}}
    r = client.post("/webhooks/telegram", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
    assert r.status_code == 200 and seen == [update]


def test_health_shows_no_secrets(web):
    client, _ = web
    body = client.get("/health").json()
    assert body["ok"] and body["telegram"] is True and body["llm"] == "offline"
    assert "s3cret" not in json.dumps(body) and "123:test" not in json.dumps(body)


def test_transcriber_rests_a_timed_out_engine():
    calls = []

    class Engine:
        def __init__(self, name, ok):
            self.name, self.ok = name, ok

        def transcribe(self, audio, mime):
            calls.append(self.name)
            if not self.ok:
                raise TimeoutError()
            return "theek hai"

    stt = SP.Transcriber([Engine("slow", False), Engine("fast", True)], clock=lambda: 0.0)
    assert stt.transcribe(b"a") == stt.transcribe(b"a") == "theek hai"
    assert calls == ["slow", "fast", "fast"]
