"""Telegram channel: Bot API client + update handling. The same code serves the webhook (ops.web, Vercel) and the
local long-polling runner (python -m ops.setup_telegram poll).

* private chats only; every update is processed once (update_id lock in the store)
* text -> brain.handle; voice/audio -> speech-to-text -> brain.handle; location pin -> brain.share_location
* inline buttons carry manager actions ("approve BK-2001"); presses run the same commands as typing them
* notify events from the brain are delivered to their Telegram targets (WhatsApp targets come in phase 6)
"""
import json
import logging
import os
import urllib.error
import urllib.request

from . import brain, core

log = logging.getLogger("fleetlog.telegram")
API = "https://api.telegram.org"
MAX_TEXT = 4000                 # Telegram limit is 4096 characters per message
MAX_VOICE_SECONDS = 120         # longer notes are refused (free-tier speech quota)
MAX_VOICE_BYTES = 5_000_000
UPDATE_TTL = 2 * 24 * 3600      # Telegram retries failed deliveries for about a day
ONE_SHOT_ACTIONS = ("approve", "reschedule", "resolve")  # buttons removed after use; "call" stays until resolved
SORRY = "Maazrat, abhi kuch masla aa gaya. Thori der baad dobara bhejein."


class TelegramError(Exception):
    pass


class Bot:
    def __init__(self, token, transport=None, fetch=None, timeout=20):
        self.token, self.timeout = token, timeout
        self.transport = transport or self._http
        self.fetch = fetch or self._download

    def _http(self, method, params):
        req = urllib.request.Request(f"{API}/bot{self.token}/{method}", data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout + params.get("timeout", 0)) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:  # Telegram explains errors in the JSON body
            return json.loads(e.read().decode() or "{}")

    def _download(self, file_path):
        with urllib.request.urlopen(f"{API}/file/bot{self.token}/{file_path}", timeout=self.timeout) as resp:
            return resp.read()

    def call(self, method, **params):
        body = self.transport(method, params)
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('error_code')} {body.get('description')}")
        return body.get("result")

    def send(self, chat_id, text, buttons=None):
        """Plain text (no parse_mode: nothing to escape), split under the size limit; buttons on the last part."""
        parts = _split(text or "…")
        for n, part in enumerate(parts, 1):
            params = {"chat_id": chat_id, "text": part, "disable_web_page_preview": True}
            if buttons and n == len(parts):
                params["reply_markup"] = keyboard(buttons)
            self.call("sendMessage", **params)

    def file_bytes(self, file_id):
        return self.fetch(self.call("getFile", file_id=file_id)["file_path"])


def keyboard(buttons):
    """[{"text", "action"}] -> inline keyboard, two buttons per row; callback_data is the action text (<= 64 bytes)."""
    keys = [{"text": b["text"], "callback_data": b["action"][:64]} for b in buttons]
    return {"inline_keyboard": [keys[i:i + 2] for i in range(0, len(keys), 2)]}


def _split(text):
    parts = []
    while len(text) > MAX_TEXT:
        cut = text.rfind("\n", 0, MAX_TEXT)
        cut = cut if cut > MAX_TEXT // 2 else MAX_TEXT
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts + [text]


def user_id(chat_id):
    return f"telegram:{chat_id}"


def chat_id(uid):
    return uid.split(":", 1)[1] if uid.startswith("telegram:") else None


# ----------------------------------------------------------------------------- update handling
def handle_update(update, *, bot, store=None, settings=None, chain=None, transcriber=None, now=None):
    """Process one Telegram update. Returns a short status (for logs/tests); never raises for bad input."""
    d = brain._defaults() if store is None or settings is None else {}
    store, settings = store or d["store"], settings or d["settings"]
    uid = update.get("update_id")
    if uid is not None and not store.set_nx(f"tg:update:{uid}", 1, ttl=UPDATE_TTL):
        return "duplicate"
    kw = {"store": store, "settings": settings, "now": now}
    if "callback_query" in update:
        return _button(update["callback_query"], bot, chain, kw)
    msg = update.get("message")
    if not msg:
        return "ignored"
    chat = msg.get("chat", {})
    if chat.get("type") != "private":  # group chats would leak driver/manager data to everyone in the group
        return "ignored:not_private"
    cid, sender = chat["id"], user_id(chat["id"])
    try:
        bot.call("sendChatAction", chat_id=cid, action="typing")
    except Exception:
        pass
    try:
        if "location" in msg:
            loc = msg["location"]
            out = brain.share_location(sender, loc["latitude"], loc["longitude"], **kw)
            status = "location"
        elif "voice" in msg or "audio" in msg:
            heard, problem = _transcribe(msg.get("voice") or msg["audio"], bot, transcriber)
            if problem:
                bot.send(cid, problem)
                return "voice:failed"
            out = brain.handle(sender, heard, chain=chain, **kw)
            out["reply"] = f"🎤 \"{heard}\"\n\n{out['reply']}"
            status = "voice"
        elif "text" in msg:
            out = brain.handle(sender, msg["text"], chain=chain, **kw)
            status = "text"
        else:
            bot.send(cid, "Abhi text, voice note aur location chalti hai.")
            return "unsupported"
        bot.send(cid, out["reply"], out.get("buttons"))
        deliver(out["events"], bot)
        return f"{status}:{out['mode']}"
    except Exception:
        log.exception("telegram update %s failed", uid)
        try:
            bot.send(cid, SORRY)
        except Exception:
            pass
        return "error"


def _transcribe(media, bot, transcriber):
    """(transcript, None), or (None, message for the user) when the note is refused or not understood."""
    if transcriber is None:
        from . import speech
        transcriber = speech.from_env()
    if not transcriber:
        return None, "Voice note abhi set up nahi. Meharbani kar ke likh kar bhejein."
    if media.get("duration", 0) > MAX_VOICE_SECONDS or media.get("file_size", 0) > MAX_VOICE_BYTES:
        return None, f"Voice note {MAX_VOICE_SECONDS // 60} minute se chhota bhejein."
    try:
        audio = bot.file_bytes(media["file_id"])
        return transcriber.transcribe(audio, media.get("mime_type") or "audio/ogg"), None
    except Exception as e:
        log.warning("voice transcription failed: %s", type(e).__name__)
        return None, "Voice samajh nahi aayi. Dobara bolein ya likh kar bhejein."


def _button(cq, bot, chain, kw):
    action, msg = (cq.get("data") or "").strip(), cq.get("message") or {}
    cid = msg.get("chat", {}).get("id") or cq.get("from", {}).get("id")
    sender = user_id(cid)
    if core.load_profile(kw["store"], sender).get("role") != "manager":
        bot.call("answerCallbackQuery", callback_query_id=cq["id"], show_alert=True,
                 text="Ye button manager ke liye hai. Demo: 'manager' likh kar phir dabayein.")
        return "button:not_manager"
    bot.call("answerCallbackQuery", callback_query_id=cq["id"])
    out = brain.handle(sender, action, chain=chain, **kw)
    if action.split(" ", 1)[0] in ONE_SHOT_ACTIONS and msg.get("message_id"):
        try:
            bot.call("editMessageReplyMarkup", chat_id=cid, message_id=msg["message_id"],
                     reply_markup={"inline_keyboard": []})
        except Exception:
            pass
    bot.send(cid, out["reply"])
    deliver(out["events"], bot)
    return f"button:{action.split(' ', 1)[0]}"


def deliver(events, bot):
    """Send queued notify events to their Telegram targets; one failed target does not stop the others."""
    sent = 0
    for e in events:
        if e.get("type") != "notify":
            continue
        for target in e["to"]:
            cid = chat_id(target)
            if cid is None:
                continue
            try:
                bot.send(cid, e["text"], e.get("buttons"))
                sent += 1
            except Exception as ex:
                log.warning("notify %s failed: %s", target, ex)
    return sent


def from_env(**kw):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    return Bot(token, **kw) if token else None
