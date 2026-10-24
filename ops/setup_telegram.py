"""Telegram bot setup and local runner. Reads TELEGRAM_BOT_TOKEN / TELEGRAM_WEBHOOK_SECRET from .env; never prints them.

    python -m ops.setup_telegram secret          create TELEGRAM_WEBHOOK_SECRET in .env (if empty)
    python -m ops.setup_telegram info            bot name + current webhook status
    python -m ops.setup_telegram set <base-url>  point the webhook at <base-url>/webhooks/telegram (https only)
    python -m ops.setup_telegram delete          remove the webhook
    python -m ops.setup_telegram poll            local test without any tunnel: long polling (removes the webhook)
"""
import os
import re
import secrets
import sys
import time

from . import ROOT, env, telegram

ALLOWED = ["message", "callback_query"]
COMMANDS = [{"command": "start", "description": "Shuru / madad"},
            {"command": "brief", "description": "Manager: aaj ki report"},
            {"command": "reset", "description": "Naya shuru (profile saaf)"}]


def _bot():
    env.load()
    bot = telegram.from_env()
    if bot is None:
        sys.exit("TELEGRAM_BOT_TOKEN is empty in .env (get it from @BotFather).")
    return bot


def make_secret(path=None):
    """Write a random webhook secret into .env when the line is empty or missing. Returns True if written."""
    path = path or ROOT / ".env"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    m = re.search(r"^TELEGRAM_WEBHOOK_SECRET=(.*)$", text, flags=re.M)
    if m and env.parse_value(m.group(1)):
        return False
    line = f"TELEGRAM_WEBHOOK_SECRET={secrets.token_urlsafe(32)}"  # Telegram allows A-Z a-z 0-9 _ -
    text = (text[:m.start()] + line + text[m.end():]) if m else text.rstrip("\n") + "\n" + line + "\n"
    path.write_text(text, encoding="utf-8")
    return True


def info(bot):
    me = bot.call("getMe")
    hook = bot.call("getWebhookInfo")
    print(f"Bot: @{me['username']} ({me['first_name']})  link: https://t.me/{me['username']}")
    print(f"Webhook: {hook.get('url') or '(none: polling or not set)'}  pending updates: {hook.get('pending_update_count', 0)}")
    if hook.get("last_error_message"):
        print(f"Last webhook error: {hook['last_error_message']}")


def set_webhook(bot, base_url):
    if not base_url.startswith("https://"):
        sys.exit("Telegram webhooks need an https:// URL.")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not secret:
        sys.exit("TELEGRAM_WEBHOOK_SECRET is empty: run  python -m ops.setup_telegram secret  first.")
    bot.call("setWebhook", url=base_url.rstrip("/") + "/webhooks/telegram", secret_token=secret,
             allowed_updates=ALLOWED, drop_pending_updates=True)
    bot.call("setMyCommands", commands=COMMANDS)
    info(bot)


def _retry(fn, attempts=5, wait=3):
    """Startup calls survive a network blip (VPN reconnects, a reset handshake)."""
    for n in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            if n == attempts:
                raise
            print(f"Telegram not reachable ({type(e).__name__}); retry {n}/{attempts - 1}…", flush=True)
            time.sleep(wait)


def poll(bot):
    _retry(lambda: bot.call("deleteWebhook", drop_pending_updates=False))
    _retry(lambda: bot.call("setMyCommands", commands=COMMANDS))
    _retry(lambda: info(bot))
    print("Polling… message the bot on Telegram. Ctrl+C to stop.", flush=True)
    offset = None
    while True:
        try:
            updates = bot.call("getUpdates", timeout=25, allowed_updates=ALLOWED,
                               **({"offset": offset} if offset else {}))
        except Exception as e:  # network blip: wait and retry
            print(f"getUpdates failed: {e}")
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            status = telegram.handle_update(u, bot=bot)
            print(time.strftime("%H:%M:%S"), u["update_id"], status, flush=True)


def main(argv):
    cmd = argv[0] if argv else "info"
    if cmd == "secret":
        print("TELEGRAM_WEBHOOK_SECRET written to .env" if make_secret() else "TELEGRAM_WEBHOOK_SECRET already set")
    elif cmd == "info":
        info(_bot())
    elif cmd == "set" and len(argv) == 2:
        set_webhook(_bot(), argv[1])
    elif cmd == "delete":
        _bot().call("deleteWebhook", drop_pending_updates=False)
        print("Webhook removed.")
    elif cmd == "poll":
        try:
            poll(_bot())
        except KeyboardInterrupt:
            print("Stopped.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
