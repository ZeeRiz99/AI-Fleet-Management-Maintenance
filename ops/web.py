"""FleetLog AI web entry point.  Run locally:  uvicorn ops.web:app --port 8100   (Vercel: build/vercel/index.py)

GET  /                   what this service is (no data)
GET  /health             liveness + which pieces are configured (never any secret values)
POST /webhooks/telegram  Telegram updates; only requests carrying our secret token are accepted
POST /api/chat           the Android app's "Ask FleetLog AI" screen (X-App-Key header)
"""
import hmac
import logging
import os
import re

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import brain, channels, env, telegram

env.load()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("fleetlog.web")
MAX_BODY = 1_000_000
SESSION_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")

app = FastAPI(title="FleetLog AI", description="AI Fleet Log Assistant: Telegram webhook and the app's chat API.",
              docs_url=None, redoc_url=None)
_BOT = {}


def _bot():
    if "bot" not in _BOT:
        _BOT["bot"] = telegram.from_env()
    return _BOT["bot"]


def _same(given, expected):
    """Constant-time secret comparison that fails closed when no secret is configured."""
    return bool(expected) and hmac.compare_digest((given or "").encode(), expected.encode())


@app.get("/")
def root():
    return {"service": "FleetLog AI — AI Fleet Log Assistant",
            "about": "Drivers report problems (text or voice) on Telegram; the manager gets alerts and approves "
                     "workshop bookings. Simulated demo fleet; risk data as of 1 Jan 2026.",
            "repo": "https://github.com/ZeeRiz99/AI-Fleet-Management-Maintenance"}


@app.get("/health")
def health():
    d = brain._defaults()
    persistent = d["store"].kind == "redis" or not os.environ.get("VERCEL")
    return {"ok": True, "service": "FleetLog AI", "llm": d["chain"].label, "store": d["store"].kind,
            "store_persistent": persistent,
            "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
            "webhook_secret": bool(os.environ.get("TELEGRAM_WEBHOOK_SECRET")),
            "app_chat": bool(os.environ.get("OPS_APP_KEY"))}


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    if not _same(x_telegram_bot_api_secret_token, os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")):
        raise HTTPException(403, "forbidden")
    bot = _bot()
    if bot is None:
        raise HTTPException(503, "telegram not configured")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "too large")
    try:
        update = await request.json()
    except ValueError:
        raise HTTPException(400, "bad json") from None
    # processed before answering: serverless functions stop once the response is sent
    status = await run_in_threadpool(telegram.handle_update, update, bot=bot)
    log.info("telegram update %s -> %s", update.get("update_id"), status)
    return {"ok": True}


class ChatIn(BaseModel):
    session: str = Field(..., description="random id the app keeps per install")
    text: str = Field(..., max_length=4000)


@app.post("/api/chat")
def app_chat(body: ChatIn, x_app_key: str = Header(default="")):
    """The app's chat. The key is a soft gate (it ships inside the APK): it keeps out casual traffic, while the
    per-user and daily LLM limits in the brain protect the free quotas."""
    if not _same(x_app_key, os.environ.get("OPS_APP_KEY", "")):
        raise HTTPException(403, "forbidden")
    if not SESSION_RE.match(body.session):
        raise HTTPException(422, "bad session id")
    out = brain.handle(f"app:{body.session}", body.text)
    channels.deliver(out["events"], telegram_bot=_bot())
    return {"reply": out["reply"], "mode": out["mode"], "buttons": out.get("buttons", []), "profile": out["profile"]}
