"""FleetLog AI web entry point (webhooks).  Run locally:  uvicorn ops.web:app --port 8100

POST /webhooks/telegram  Telegram updates; only requests carrying our secret token are accepted
GET  /health             liveness + which pieces are configured (never any secret values)
"""
import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from . import brain, env, telegram

env.load()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("fleetlog.web")
MAX_BODY = 1_000_000

app = FastAPI(title="FleetLog AI", description="AI Fleet Log Assistant: Telegram webhook (WhatsApp in phase 6).",
              docs_url=None, redoc_url=None)
_BOT = {}


def _bot():
    if "bot" not in _BOT:
        _BOT["bot"] = telegram.from_env()
    return _BOT["bot"]


@app.get("/health")
def health():
    d = brain._defaults()
    return {"ok": True, "service": "FleetLog AI", "llm": d["chain"].label, "store": d["store"].kind,
            "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
            "webhook_secret": bool(os.environ.get("TELEGRAM_WEBHOOK_SECRET"))}


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    # fail closed: without a configured secret nobody can post fake updates
    if not secret or not hmac.compare_digest(x_telegram_bot_api_secret_token.encode(), secret.encode()):
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
