"""WhatsApp channel (Meta WhatsApp Cloud API): webhook handling + sending. Mirrors ops/telegram.py.

Verified against Meta's docs (2026-10-22): Graph API v26.0 examples; reply buttons: at most 3, title <= 20 chars,
id <= 256, body <= 1024; webhooks signed with X-Hub-Signature-256 (HMAC-SHA256 of the raw body, app secret);
media: GET /<media-id> -> url (valid 5 min) -> download with the same bearer token; non-200 answers are retried
for up to 7 days, so every message id is processed once.

Free-form messages only reach a user within 24 hours of their last message to the business. Alerts, briefs and
reminders outside that window need an approved template: set WHATSAPP_ALERT_TEMPLATE (one body variable) and
they are re-sent through it; otherwise the failure is logged.
"""
import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request

from . import brain, channels, core

log = logging.getLogger("fleetlog.whatsapp")
GRAPH = "https://graph.facebook.com"
MAX_TEXT = 4000            # WhatsApp text limit is 4096
MAX_BUTTON_BODY = 1024
MAX_BUTTONS = 3
MAX_TITLE = 20
MAX_VOICE_BYTES = 5_000_000
MESSAGE_TTL = 8 * 24 * 3600  # longer than Meta's 7-day retry period
OUTSIDE_WINDOW = 131047      # "re-engagement message": more than 24 h since the user wrote
SORRY = "Maazrat, abhi kuch masla aa gaya. Thori der baad dobara bhejein."


class WhatsAppError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def verify_signature(raw_body, header, app_secret):
    """X-Hub-Signature-256: 'sha256=<hex>' over the exact bytes received. Fails closed without a secret."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], expected)


def verify_subscription(params, verify_token):
    """GET handshake when the webhook is registered: echo hub.challenge if the token matches, else None."""
    if (verify_token and params.get("hub.mode") == "subscribe"
            and hmac.compare_digest(params.get("hub.verify_token", ""), verify_token)):
        return params.get("hub.challenge", "")
    return None


class Client:
    def __init__(self, token, phone_number_id, version="v26.0", transport=None, fetch=None, template=None,
                 template_lang="en", timeout=20):
        self.token, self.phone_id, self.version = token, phone_number_id, version
        self.template, self.template_lang, self.timeout = template, template_lang, timeout
        self.transport = transport or self._http
        self.fetch = fetch or self._download

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                "User-Agent": "fleetlog-ai/1.0"}

    def _http(self, method, path, payload=None):
        req = urllib.request.Request(f"{GRAPH}/{self.version}/{path}", method=method, headers=self._headers(),
                                     data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:  # Graph explains errors in the JSON body
            return json.loads(e.read().decode() or "{}")

    def _download(self, url):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}",
                                                   "User-Agent": "fleetlog-ai/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def call(self, method, path, payload=None):
        body = self.transport(method, path, payload)
        if "error" in body:
            err = body["error"]
            raise WhatsAppError(f"{err.get('code')}: {err.get('message')}", err.get("code"))
        return body

    def _message(self, to, payload):
        return self.call("POST", f"{self.phone_id}/messages",
                         {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **payload})

    def send(self, to, text, buttons=None):
        """Text (split under the limit); buttons as reply-button messages of up to 3. Outside the 24-hour window
        the text goes through the alert template when one is configured."""
        try:
            self._send(to, text or "…", buttons or [])
        except WhatsAppError as e:
            if e.code != OUTSIDE_WINDOW or not self.template:
                raise
            self._message(to, {"type": "template", "template": {
                "name": self.template, "language": {"code": self.template_lang},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": text[:1000]}]}]}})

    def _send(self, to, text, buttons):
        groups = [buttons[i:i + MAX_BUTTONS] for i in range(0, len(buttons), MAX_BUTTONS)]
        if groups and len(text) <= MAX_BUTTON_BODY:
            body, rest = text, groups
        else:
            for part in _split(text):
                self._message(to, {"type": "text", "text": {"body": part, "preview_url": False}})
            body, rest = "👇", groups
        for n, group in enumerate(rest):
            self._message(to, {"type": "interactive", "interactive": {
                "type": "button", "body": {"text": body if n == 0 else "👇"},
                "action": {"buttons": [{"type": "reply", "reply": {"id": b["action"][:256], "title": _title(b["text"])}}
                                       for b in group]}}})

    def mark_read_typing(self, message_id):
        self._message_status({"status": "read", "message_id": message_id, "typing_indicator": {"type": "text"}})

    def _message_status(self, payload):
        self.call("POST", f"{self.phone_id}/messages", {"messaging_product": "whatsapp", **payload})

    def media_bytes(self, media_id):
        meta = self.call("GET", f"{media_id}?phone_number_id={self.phone_id}")
        if int(meta.get("file_size") or 0) > MAX_VOICE_BYTES:
            raise WhatsAppError("media too large")
        return self.fetch(meta["url"]), (meta.get("mime_type") or "audio/ogg").split(";")[0].strip()


def _title(text):
    return text if len(text) <= MAX_TITLE else text[:MAX_TITLE - 1] + "…"


def _split(text):
    parts = []
    while len(text) > MAX_TEXT:
        cut = text.rfind("\n", 0, MAX_TEXT)
        cut = cut if cut > MAX_TEXT // 2 else MAX_TEXT
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts + [text]


def user_id(number):
    return f"whatsapp:{''.join(ch for ch in str(number) if ch.isdigit())}"


# ----------------------------------------------------------------------------- webhook payload handling
def messages_in(payload):
    """(message, contact name) pairs from a webhook payload; status updates (sent/delivered/read) are skipped."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if change.get("field") != "messages":
                continue
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                yield m, names.get(m.get("from"))


def handle_payload(payload, *, client, store=None, settings=None, chain=None, transcriber=None, now=None):
    """Process every message in one webhook POST. Returns the per-message statuses (for logs/tests)."""
    return [handle_message(m, client=client, store=store, settings=settings, chain=chain, transcriber=transcriber,
                           now=now) for m, _ in messages_in(payload)]


def handle_message(msg, *, client, store=None, settings=None, chain=None, transcriber=None, now=None):
    d = brain._defaults() if store is None or settings is None else {}
    store, settings = store or d["store"], settings or d["settings"]
    mid, sender_number = msg.get("id"), msg.get("from")
    if not sender_number:
        return "ignored"
    if mid and not store.set_nx(f"wa:msg:{mid}", 1, ttl=MESSAGE_TTL):
        return "duplicate"
    sender, kind = user_id(sender_number), msg.get("type")
    kw = {"store": store, "settings": settings, "now": now}
    try:
        if mid:
            try:
                client.mark_read_typing(mid)
            except Exception:
                pass
        if kind == "text":
            out, status = brain.handle(sender, msg["text"].get("body", ""), chain=chain, **kw), "text"
        elif kind == "interactive" and msg["interactive"].get("type") == "button_reply":
            action = msg["interactive"]["button_reply"]["id"]
            if core.load_profile(store, sender).get("role") != "manager":
                client.send(sender_number, "Ye button manager ke liye hai. Demo: 'manager' likh kar phir dabayein.")
                return "button:not_manager"
            out, status = brain.handle(sender, action, chain=chain, **kw), f"button:{action.split(' ', 1)[0]}"
        elif kind == "location":
            loc = msg["location"]
            out, status = brain.share_location(sender, loc["latitude"], loc["longitude"], **kw), "location"
        elif kind in ("audio", "voice"):
            heard, problem = _transcribe(msg.get("audio") or msg.get("voice") or {}, client, transcriber)
            if problem:
                client.send(sender_number, problem)
                return "voice:failed"
            out = brain.handle(sender, heard, chain=chain, **kw)
            out["reply"], status = f"🎤 \"{heard}\"\n\n{out['reply']}", "voice"
        else:
            client.send(sender_number, "Abhi text, voice note aur location chalti hai.")
            return "unsupported"
        client.send(sender_number, out["reply"], out.get("buttons"))
        channels.deliver(out["events"], whatsapp_client=client)
        return f"{status}:{out['mode']}"
    except Exception:
        log.exception("whatsapp message %s failed", mid)
        try:
            client.send(sender_number, SORRY)
        except Exception:
            pass
        return "error"


def _transcribe(media, client, transcriber):
    if transcriber is None:
        from . import speech
        transcriber = speech.from_env()
    if not transcriber:
        return None, "Voice note abhi set up nahi. Meharbani kar ke likh kar bhejein."
    try:
        audio, mime = client.media_bytes(media["id"])
        return transcriber.transcribe(audio, mime), None
    except WhatsAppError as e:
        if "too large" in str(e):
            return None, "Voice note 2 minute se chhota bhejein."
        log.warning("voice download failed: %s", e)
    except Exception as e:
        log.warning("voice transcription failed: %s", type(e).__name__)
    return None, "Voice samajh nahi aayi. Dobara bolein ya likh kar bhejein."


def from_env(**kw):
    env = os.environ.get
    if not (env("WHATSAPP_TOKEN") and env("WHATSAPP_PHONE_NUMBER_ID")):
        return None
    return Client(env("WHATSAPP_TOKEN"), env("WHATSAPP_PHONE_NUMBER_ID"), env("WHATSAPP_GRAPH_VERSION", "v26.0"),
                  template=env("WHATSAPP_ALERT_TEMPLATE") or None,
                  template_lang=env("WHATSAPP_ALERT_TEMPLATE_LANG", "en"), **kw)
