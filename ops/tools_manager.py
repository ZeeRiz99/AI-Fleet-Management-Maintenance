"""Manager tools: the 7 existing data tools from src/agent.py, the ops records (issues, bookings, brief), money
planning (plan_services, what_if) and actions on driver reports (approve, reschedule, resolve, call)."""
from datetime import timedelta

import agent as legacy  # src/agent.py: fleet_overview, high_risk_vehicles, ... (reused, not duplicated)
import config as C

from . import core
from . import registry as R
from . import workshops as W
from .core import tool

MANAGER = ("manager",)
_STR, _NUM, _INT = {"type": "string"}, {"type": "number"}, {"type": "integer"}

# --- existing data tools, unchanged (schemas converted from the Anthropic format in src/agent.py)
for spec in legacy.TOOLS:
    fn = legacy.FUNCS[spec["name"]]
    props = spec["input_schema"].get("properties", {})
    core.tool(spec["name"], spec["description"], MANAGER, props, spec["input_schema"].get("required", []))(
        (lambda f: lambda ctx, **kw: {"ok": True, "data": f(**kw)})(fn))


def _issue_line(i):
    return f"• {i['id']} {i['registration']}: {i['description'][:60]} ({i['category']}/{i['severity']}, {i['status']})"


@tool("open_issues", "Driver-reported issues that are not resolved yet (newest first).", MANAGER, {"limit": _INT})
def open_issues(ctx, limit=10):
    items = [i for i in core.list_records(ctx.store, "issue") if i["status"] != "resolved"][::-1][:int(limit)]
    return {"ok": True, "issues": items,
            "message": ("🧾 Khule masle:\n" + "\n".join(_issue_line(i) for i in items)) if items else "Koi khula masla nahi. ✅"}


@tool("upcoming_bookings", "Workshop bookings in the next N hours (default 48).", MANAGER, {"hours": _INT})
def upcoming_bookings(ctx, hours=48):
    end = (ctx.now + timedelta(hours=int(hours))).isoformat()
    items = sorted([b for b in core.list_records(ctx.store, "booking")
                    if b["status"] in ("pending_approval", "confirmed") and ctx.now.isoformat() <= b["start"] <= end],
                   key=lambda b: b["start"])
    lines = [f"• {b['id']} {b['registration']}: {W.label(W.parse_slot(b['slot_id']))} · {b['service']} ({b['status']})"
             for b in items]
    return {"ok": True, "bookings": items,
            "message": ("📅 Aane wali bookings:\n" + "\n".join(lines)) if items else f"Agle {hours} ghante mein koi booking nahi."}


def build_brief(ctx):
    """Morning brief data + chat text. Risk and fuel come from the scored snapshot (simulated, as of 1 Jan 2026);
    issues and bookings are live."""
    high = [v for v in R.all_vehicles() if v["risk_tier"] == "High"]
    high.sort(key=lambda v: v["risk_prob"], reverse=True)
    fuel = legacy.fuel_anomalies(30, 5)
    day_ago = (ctx.now - timedelta(hours=24)).isoformat()
    issues = [i for i in core.list_records(ctx.store, "issue") if i["created_at"] >= day_ago]
    soon = upcoming_bookings(ctx, 48)["bookings"]
    saving = sum(max(0, v["net_saving_pkr"]) for v in high)
    lines = [f"☀️ FleetLog AI subah ki report ({ctx.now:%d %b %Y})",
             f"🔴 High risk: {len(high)} gaariyan; waqt par service se taqreeban {core.pkr(saving)} bach sakte hain."]
    lines += [f"   • {v['registration']} {v['risk_prob']:.0%} → {v['recommended_service']}" for v in high[:5]]
    lines.append(f"⛽ Fuel shak (30 din): {fuel['flagged_trips']} trips, {core.pkr(fuel['total_excess_cost_pkr'])} zyada fuel.")
    lines += [f"   • {r['registration']}: {core.pkr(r['excess_cost_pkr'])}" for r in fuel["top_vehicles"][:3]]
    lines.append(f"🧾 Driver reports (24 ghante): {len(issues)}" + (f" ({sum(i['escalated'] for i in issues)} urgent)" if issues else ""))
    lines.append(f"🔧 Bookings (48 ghante): {len(soon)}")
    pending = [b for b in core.list_records(ctx.store, "booking") if b["status"] == "pending_approval"]
    if pending:
        lines.append(f"⏳ Approval ka intezar: {len(pending)} ({', '.join(b['id'] for b in pending[:5])}); "
                     f"'approve BK-…' likhein.")
    lines.append("ℹ️ Risk aur fuel data simulated demo fleet ka hai (1 Jan 2026 tak); reports aur bookings live hain.")
    return {"date": ctx.now.date().isoformat(), "high_risk": [
                {k: v[k] for k in ("registration", "risk_prob", "recommended_service", "net_saving_pkr")} for v in high],
            "fuel": fuel, "issues_24h": issues, "bookings_48h": soon, "saving_pkr": round(saving),
            "text": "\n".join(lines)}


@tool("morning_brief", "Today's brief: high-risk vehicles + Rs saving, fuel-theft suspects, driver reports, bookings.",
      MANAGER)
def morning_brief(ctx):
    b = build_brief(ctx)
    return {"ok": True, "brief": {k: v for k, v in b.items() if k != "text"}, "message": b["text"]}


ASSUMPTION = (f"Andaza: service se breakdown risk {C.SERVICE_RISK_REDUCTION:.0%} kam hota hai, aur downtime "
              f"{core.pkr(C.DOWNTIME_COST_PER_DAY_PKR)}/din (config.py ke assumptions).")


@tool("plan_services", "Best vehicles to service within a budget (Rs): picks the highest saving per rupee.", MANAGER,
      {"budget_pkr": _NUM, "max_vehicles": _INT}, ["budget_pkr"])
def plan_services(ctx, budget_pkr, max_vehicles=10):
    budget = float(budget_pkr)
    if budget <= 0:
        raise ValueError("Budget Rs mein musbat number hona chahiye.")
    pool = sorted([v for v in R.all_vehicles() if v["net_saving_pkr"] > 0],
                  key=lambda v: v["net_saving_pkr"] / v["service_cost_pkr"], reverse=True)
    chosen, spent = [], 0.0
    for v in pool:
        if len(chosen) >= int(max_vehicles):
            break
        if spent + v["service_cost_pkr"] <= budget:
            chosen.append(v)
            spent += v["service_cost_pkr"]
    saving = sum(v["net_saving_pkr"] for v in chosen)
    lines = [f"• {v['registration']}: {v['recommended_service']} {core.pkr(v['service_cost_pkr'])} → bachat "
             f"{core.pkr(v['net_saving_pkr'])} (risk {v['risk_prob']:.0%})" for v in chosen]
    msg = (f"💰 {core.pkr(budget)} budget mein behtareen plan ({len(chosen)} gaariyan, kharcha {core.pkr(spent)}, "
           f"andazan bachat {core.pkr(saving)}):\n" + "\n".join(lines) + f"\n{ASSUMPTION}") if chosen else \
          "Is budget mein koi faida-mand service nahi aati."
    return {"ok": True, "budget_pkr": budget, "spent_pkr": round(spent), "saving_pkr": round(saving),
            "vehicles": [{k: v[k] for k in ("registration", "recommended_service", "service_cost_pkr", "net_saving_pkr",
                                            "risk_prob")} for v in chosen], "message": msg}


@tool("what_if", "Expected breakdown loss before vs after servicing the given vehicles now.", MANAGER,
      {"registrations": {"type": "array", "items": _STR}}, ["registrations"])
def what_if(ctx, registrations):
    rows, missing = [], []
    for raw in registrations:
        v = R.vehicle(R.normalize(str(raw)) or "")
        (rows.append(v) if v else missing.append(str(raw)))
    if not rows:
        raise ValueError("In mein se koi gaari fleet mein nahi mili.")
    before = sum(v["expected_loss_pkr"] for v in rows)
    after = sum(v["expected_loss_pkr"] * (1 - C.SERVICE_RISK_REDUCTION) for v in rows)
    cost = sum(v["service_cost_pkr"] for v in rows)
    net = before - after - cost
    msg = (f"🔮 Agar {len(rows)} gaariyon ki service abhi ho: mutawaqqa nuqsan {core.pkr(before)} → {core.pkr(after)}, "
           f"service kharcha {core.pkr(cost)}, khalis {'bachat' if net >= 0 else 'nuqsan'} {core.pkr(abs(net))}.\n{ASSUMPTION}"
           + (f"\n(Nahi mili: {', '.join(missing)})" if missing else ""))
    return {"ok": True, "expected_loss_before_pkr": round(before), "expected_loss_after_pkr": round(after),
            "service_cost_pkr": round(cost), "net_pkr": round(net), "not_found": missing, "message": msg}


def _booking(ctx, booking_id):
    b = core.get_record(ctx.store, "booking", booking_id)
    if not b:
        raise ValueError(f"Booking {booking_id} nahi mili.")
    return b


@tool("approve_booking", "Approve a pending workshop booking; the driver is told it is confirmed.", MANAGER,
      {"booking_id": _STR}, ["booking_id"])
def approve_booking(ctx, booking_id):
    b = _booking(ctx, booking_id)
    if b["status"] != "pending_approval":
        raise ValueError(f"Booking {b['id']} ka status '{b['status']}' hai; approve nahi ho sakti.")
    b.update(status="confirmed", approved_by=ctx.user_id, approved_at=ctx.now.isoformat(timespec="seconds"))
    core.save_record(ctx.store, "booking", b)
    ctx.notify([b["driver"]], f"✅ Aap ki booking {b['id']} confirm ho gayi: {W.label(W.parse_slot(b['slot_id']))}, "
                              f"{b['address']}.", kind="driver_update")
    ctx.emit("booking.approved", b)
    return {"ok": True, "message": f"✅ {b['id']} approve; driver ko bata diya."}


@tool("reschedule_booking", "Cancel a booking's slot and ask the driver to pick a new one.", MANAGER,
      {"booking_id": _STR}, ["booking_id"])
def reschedule_booking(ctx, booking_id):
    b = _booking(ctx, booking_id)
    if b["status"] not in ("pending_approval", "confirmed"):
        raise ValueError(f"Booking {b['id']} ({b['status']}) badli nahi ja sakti.")
    ctx.store.delete(f"slot:{b['slot_id']}")
    b.update(status="rescheduled", changed_by=ctx.user_id)
    core.save_record(ctx.store, "booking", b)
    ctx.notify([b["driver"]], f"🔁 Manager ne booking {b['id']} ka waqt badalne ko kaha hai. "
                              f"Naya waqt chunne ke liye 'slot' likhein.", kind="driver_update")
    ctx.emit("booking.rescheduled", b)
    return {"ok": True, "message": f"🔁 {b['id']} ka slot khali kar diya; driver ko naya slot chunne ka kaha."}


@tool("resolve_issue", "Mark a driver-reported issue as resolved (optional note).", MANAGER,
      {"issue_id": _STR, "note": _STR}, ["issue_id"])
def resolve_issue(ctx, issue_id, note=""):
    i = core.get_record(ctx.store, "issue", issue_id)
    if not i:
        raise ValueError(f"Issue {issue_id} nahi mila.")
    i.update(status="resolved", resolved_by=ctx.user_id, note=note, resolved_at=ctx.now.isoformat(timespec="seconds"))
    core.save_record(ctx.store, "issue", i)
    ctx.notify([i["reporter"]], f"✔ Aap ki report {i['id']} hal kar di gayi." + (f" Note: {note}" if note else ""),
               kind="driver_update")
    ctx.emit("issue.resolved", i)
    return {"ok": True, "message": f"✔ {i['id']} resolved."}


@tool("call_driver", "Who reported an issue and how to reach them; the driver is told the manager will call.", MANAGER,
      {"issue_id": _STR}, ["issue_id"])
def call_driver(ctx, issue_id):
    i = core.get_record(ctx.store, "issue", issue_id)
    if not i:
        raise ValueError(f"Issue {issue_id} nahi mila.")
    channel, _, ident = i["reporter"].partition(":")
    contact = f"+{ident.lstrip('+')}" if channel == "whatsapp" else f"{channel} user {ident}"
    ctx.notify([i["reporter"]], "📞 Manager aap ko jald call karein ge. Phone qareeb rakhein.", kind="driver_update")
    return {"ok": True, "contact": contact, "message": f"📞 {i['id']} ({i['registration']}) ka driver: {contact}. "
                                                        f"Driver ko bata diya ke aap call karein ge."}
