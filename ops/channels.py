"""Outgoing delivery shared by every entry point (Telegram, WhatsApp, the Android app, the morning cron).

The brain only queues events; this module sends them:
* notify -> each target on its own channel ("telegram:<chat>" / "whatsapp:<number>"); "app:" users have no push
* event  -> forwarded to OPS_EVENTS_WEBHOOK_URL (n8n / Google Apps Script) when configured
One failed target never stops the others.
"""
import json
import logging
import os
import urllib.request

log = logging.getLogger("fleetlog.channels")


def _telegram(bot):
    if bot is not None:
        return bot
    from . import telegram
    return telegram.from_env()


def _whatsapp(client):
    if client is not None:
        return client
    from . import whatsapp
    return whatsapp.from_env()


def forward_event(event, transport=None):
    """POST a business event (issue.reported, booking.created, ...) to the automation webhook, if configured."""
    url = os.environ.get("OPS_EVENTS_WEBHOOK_URL", "")
    if not url:
        return False
    body = json.dumps({"event": event["name"], "data": event["data"]}, default=str).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "fleetlog-ai/1.0",
               "X-FleetLog-Secret": os.environ.get("OPS_EVENTS_WEBHOOK_SECRET", "")}
    if transport:
        return transport(url, body, headers)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return 200 <= resp.status < 300


def deliver(events, *, telegram_bot=None, whatsapp_client=None, forward=forward_event):
    """Send notify events to their targets and forward business events. Returns the number of messages sent."""
    clients = {}

    def client(channel):  # built on first use, so a Telegram-only deployment never touches WhatsApp settings
        if channel not in clients:
            clients[channel] = (_telegram(telegram_bot) if channel == "telegram"
                                else _whatsapp(whatsapp_client) if channel == "whatsapp" else None)
        return clients[channel]

    sent = 0
    for e in events:
        if e.get("type") == "event":
            try:
                forward(e)
            except Exception as ex:
                log.warning("event %s not forwarded: %s", e.get("name"), type(ex).__name__)
            continue
        if e.get("type") != "notify":
            continue
        for target in e["to"]:
            channel, _, address = target.partition(":")
            try:
                c = client(channel)
                if c:
                    c.send(address, e["text"], e.get("buttons"))
                    sent += 1
            except Exception as ex:
                log.warning("notify %s failed: %s", target, ex)
    return sent
