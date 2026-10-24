"""Scheduled jobs. One daily run (Vercel Hobby allows one cron per day, fired anywhere within the hour, and may fire
twice), so every job here is idempotent: a per-day lock makes the second run a no-op.

    morning  08:00 PKT: manager brief + driver reminders (today's workshop visits, service due on high-risk vehicles)

Local run:  python -m ops.jobs morning      (sends through the configured channels)
"""
import sys

from . import core, registry as R
from . import workshops as W

SERVICE_REMINDER_DAYS = 7


def _driver_ctx(ctx, user_id):
    return core.Ctx(store=ctx.store, settings=ctx.settings, user_id=user_id,
                    profile=core.load_profile(ctx.store, user_id), now=ctx.now, events=ctx.events)


def visit_reminders(ctx):
    """Drivers with a workshop booking later today get the time and the address."""
    today = ctx.now.date().isoformat()
    sent = 0
    for b in core.list_records(ctx.store, "booking"):
        if b["status"] in ("confirmed", "pending_approval") and b["start"][:10] == today and b["start"] >= ctx.now.isoformat():
            state = "confirm hai" if b["status"] == "confirmed" else "abhi manager ki approval ka intezar hai"
            ctx.notify([b["driver"]], f"⏰ Yaad dihani: aaj {W.label(W.parse_slot(b['slot_id']))}\n📍 {b['address']}\n"
                                      f"Service: {b['service']} ({b['id']}; {state}).", kind="reminder")
            sent += 1
    return sent


def service_reminders(ctx):
    """Drivers of High-risk vehicles without an open booking: a nudge to book, at most once a week per vehicle."""
    booked = {b["registration"] for b in core.list_records(ctx.store, "booking")
              if b["status"] in ("confirmed", "pending_approval") and b["start"] >= ctx.now.isoformat()}
    sent = 0
    for user_id in sorted(ctx.store.smembers("drivers")):
        reg = core.load_profile(ctx.store, user_id).get("registration")
        v = R.vehicle(reg) if reg else None
        if not v or v["risk_tier"] != "High" or reg in booked:
            continue
        key = f"remind:service:{user_id}:{reg}"
        if core.recent(ctx, {"at": ctx.store.get(key)}, minutes=SERVICE_REMINDER_DAYS * 24 * 60 - 60):
            continue  # judged on the job's clock; the TTL only cleans up
        ctx.store.set(key, ctx.now.isoformat(), ttl=SERVICE_REMINDER_DAYS * 86400)
        ctx.notify([user_id], f"🔧 {reg} ka {v['recommended_service']} due hai (AI breakdown risk {v['risk_prob']:.0%}, "
                              f"demo data 1 Jan 2026 tak). 'slot' likh kar workshop ka waqt lein.", kind="reminder")
        sent += 1
    return sent


def morning(store, settings, now=None):
    """Run once per day. Returns (summary, events); the caller delivers the events."""
    from .tools_manager import build_brief
    now = now or W.now_pkt()
    ctx = core.Ctx(store=store, settings=settings, user_id="system:morning", profile={"role": "manager"}, now=now)
    if not store.set_nx(f"job:morning:{now:%Y%m%d}", now.isoformat(), ttl=3 * 86400):
        return {"status": "already_ran", "date": now.date().isoformat()}, []
    brief = build_brief(ctx)
    managers = ctx.manager_targets()
    if managers:
        ctx.notify(managers, brief["text"], kind="brief")
    summary = {"status": "ok", "date": brief["date"], "brief_to": len(managers),
               "visit_reminders": visit_reminders(ctx), "service_reminders": service_reminders(ctx)}
    ctx.emit("brief.sent", {k: v for k, v in brief.items() if k != "text"} | {"summary": summary})
    return summary, ctx.events


def main(argv):
    if argv[:1] != ["morning"]:
        sys.exit(__doc__)
    from . import brain, channels
    d = brain._defaults()
    summary, events = morning(d["store"], d["settings"])
    summary["sent"] = channels.deliver(events)
    print(summary)


if __name__ == "__main__":
    main(sys.argv[1:])
