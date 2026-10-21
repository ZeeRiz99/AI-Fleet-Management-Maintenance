"""Driver tools. A driver only ever sees their own vehicle: no other vehicles, no costs, no fleet-wide data."""
from datetime import timedelta

import pandas as pd

import config as C
from db import query

from . import core, issue_flow
from . import registry as R
from . import workshops as W
from .core import tool

DRIVER = ("driver",)
_STR, _NUM, _INT, _BOOL = {"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"}


def _need_vehicle(ctx):
    if not ctx.registration:
        raise ValueError("Pehle apni gaari ka number batayein, jaise: driver LEA-22-2030")
    return R.vehicle(ctx.registration)


@tool("set_my_vehicle", "Set the vehicle this driver is driving (registration like LEA-22-2030).", DRIVER,
      {"registration": _STR}, ["registration"])
def set_my_vehicle(ctx, registration):
    reg = R.normalize(registration)
    v = R.vehicle(reg)
    if not v:
        raise ValueError(f"'{registration}' fleet mein nahi mili. Number dobara check karein (jaise LEA-22-2030).")
    ctx.profile["registration"] = reg
    ctx.save_profile()
    return {"ok": True, "registration": reg, "city": v["city"],
            "message": f"✅ Theek hai, aap {reg} ({v['make_model']}, {v['city']}) chala rahe hain."}


@tool("start_shift", "Start the driver's shift; optionally record the odometer reading in km.", DRIVER,
      {"odometer_km": _NUM})
def start_shift(ctx, odometer_km=None):
    v = _need_vehicle(ctx)
    rec = {"user": ctx.user_id, "registration": ctx.registration, "odometer_km": odometer_km,
           "at": ctx.now.isoformat(timespec="seconds")}
    core.log(ctx.store, "shift", rec)
    ctx.profile["shift"] = {"date": ctx.now.date().isoformat(), "odometer_km": odometer_km}
    if odometer_km:
        ctx.store.set(f"odo:{ctx.registration}", float(odometer_km))
    ctx.save_profile()
    meter = f", meter {odometer_km:,.0f} km" if odometer_km else ""
    return {"ok": True, "message": f"✅ Shift shuru: {ctx.registration}{meter}. Safar mehfooz ho! "
                                   f"Koi masla ho to voice note bhej dein. ({v['city']})"}


@tool("pretrip_check", "Record the pre-trip check (true = OK). Anything not OK becomes an issue report.", DRIVER,
      {"tyres": _BOOL, "brakes": _BOOL, "oil": _BOOL, "lights": _BOOL, "notes": _STR})
def pretrip_check(ctx, tyres=True, brakes=True, oil=True, lights=True, notes=""):
    _need_vehicle(ctx)
    items = {"tyres": tyres, "brakes": brakes, "oil": oil, "lights": lights}
    core.log(ctx.store, "pretrip", {"user": ctx.user_id, "registration": ctx.registration, **items,
                                     "notes": notes, "at": ctx.now.isoformat(timespec="seconds")})
    failed = [k for k, ok in items.items() if not ok]
    if not failed:
        return {"ok": True, "failed": [], "message": "✅ Pre-trip check: sab theek. Shukriya!"}
    cat = {"tyres": "tyres", "brakes": "brakes", "oil": "engine", "lights": "electrical"}
    issues = [issue_flow.run(ctx, f"Pre-trip check: {k} theek nahi. {notes}".strip(), category=cat[k], severity="medium")
              for k in failed]
    ctx.save_profile()
    return {"ok": True, "failed": failed, "issues": [i["id"] for i in issues],
            "message": "⚠️ Pre-trip check mein masla: " + ", ".join(failed) + ". Report ban gayi: "
                       + ", ".join(i["id"] for i in issues) + ". Workshop slot ke liye 'slot' likhein."}


@tool("log_fuel", "Log a fuel fill-up: litres, and km driven since the last fill (or the odometer reading). "
      "Checks it against the vehicle's normal km/l and alerts the manager if abnormal.", DRIVER,
      {"litres": _NUM, "km": _NUM, "odometer_km": _NUM, "amount_pkr": _NUM}, ["litres"])
def log_fuel(ctx, litres, km=None, odometer_km=None, amount_pkr=None):
    _need_vehicle(ctx)
    litres = float(litres)
    if litres <= 0 or litres > 400:
        raise ValueError("Litres ka number sahi nahi lagta.")
    last_odo = ctx.store.get(f"odo:{ctx.registration}")
    if km is None and odometer_km is not None and last_odo is not None:
        km = float(odometer_km) - float(last_odo)
    if odometer_km is not None:
        ctx.store.set(f"odo:{ctx.registration}", float(odometer_km))
    rec = {"user": ctx.user_id, "registration": ctx.registration, "litres": litres, "km": km,
           "amount_pkr": amount_pkr, "at": ctx.now.isoformat(timespec="seconds")}
    if not km or km <= 0:
        core.log(ctx.store, "fuel", rec)
        return {"ok": True, "checked": False,
                "message": f"✅ Fuel log: {litres:g} litre. Check ke liye pichli fill se kitne km chale ye bhi batayein "
                           f"(ya meter reading)."}
    threshold, baselines = R.fuel_baselines()
    b = baselines[ctx.registration]
    actual = km / litres
    ratio = actual / b["baseline_km_per_l"]
    abnormal = ratio < threshold
    excess = max(0.0, litres - km / b["baseline_km_per_l"])
    rec.update({"km_per_l": round(actual, 2), "baseline_km_per_l": round(b["baseline_km_per_l"], 2),
                "abnormal": abnormal, "excess_litres": round(excess, 1)})
    core.log(ctx.store, "fuel", rec)
    if abnormal:
        cost = excess * b["fuel_price"]
        ctx.notify(ctx.manager_targets(),
                   f"⛽ Fuel alert: {ctx.registration} ne {km:,.0f} km ke liye {litres:g} L liya = {actual:.2f} km/l "
                   f"(normal {b['baseline_km_per_l']:.2f}). Taqreeban {excess:.1f} L ({core.pkr(cost)}) zyada. "
                   f"Leak, chori ya ghalat reading check karein.")
        ctx.emit("fuel.abnormal", rec)
        return {"ok": True, "checked": True, "abnormal": True, "km_per_l": round(actual, 2),
                "message": f"⚠️ Ye fill normal se zyada hai ({actual:.2f} km/l, aam taur par {b['baseline_km_per_l']:.2f}). "
                           f"Manager ko bata diya gaya hai. Tanki ya pipe se leak to nahi? Check kar lein."}
    return {"ok": True, "checked": True, "abnormal": False, "km_per_l": round(actual, 2),
            "message": f"✅ Fuel log: {litres:g} L, {km:,.0f} km = {actual:.2f} km/l. Normal hai, shukriya!"}


@tool("report_issue", "Report a vehicle problem. Give the driver's words as description; category and severity "
      "if clear (category: brakes/engine/tyres/electrical/fuel/overheating/accident/other; severity: "
      "low/medium/high/critical).", DRIVER,
      {"description": _STR, "category": {"type": "string", "enum": list(core.VALID_CATEGORIES)},
       "severity": {"type": "string", "enum": list(core.VALID_SEVERITIES)}}, ["description"])
def report_issue(ctx, description, category=None, severity=None):
    _need_vehicle(ctx)
    i = issue_flow.run(ctx, description, category, severity)
    ctx.save_profile()
    advice = core.safety_advice(i["category"], i["severity"])
    risk = f"{i['risk_prob']:.0%} ({i['risk_tier']})" if i.get("risk_prob") is not None else "n/a"
    model_note = (f" AI model ke mutabiq {i['model_service']} bhi due hai."
                  if i.get("model_service") and i["model_service"] != i["suggested_service"] else "")
    msg = "\n".join(x for x in [
        advice,
        f"📝 Report {i['id']} ban gayi ({i['category']}, {i['severity']}).",
        f"Is gaari ka AI breakdown risk: {risk} (demo data, 1 Jan 2026 tak).",
        f"Tajweez: {i['suggested_service']}.{model_note}",
        "Manager ko foran alert bhej diya gaya hai." if i["escalated"] else "Report log ho gayi; subah ki report mein jayegi.",
        "Workshop ka waqt lene ke liye 'slot' likhein."] if x)
    return {"ok": True, "issue_id": i["id"], "escalated": i["escalated"], "category": i["category"],
            "severity": i["severity"], "message": msg}


@tool("report_emergency", "Emergency or accident: alerts the manager immediately, with location if shared.", DRIVER,
      {"description": _STR, "latitude": _NUM, "longitude": _NUM}, ["description"])
def report_emergency(ctx, description, latitude=None, longitude=None):
    _need_vehicle(ctx)
    shared = core.recent(ctx, ctx.profile.get("location"), minutes=30)
    if (latitude is None or longitude is None) and shared:  # pin shared shortly before the report
        latitude, longitude = shared["lat"], shared["lon"]
    i = issue_flow.run(ctx, description, category="accident", severity="critical")
    ctx.profile["last_emergency"] = {"id": i["id"], "at": ctx.now.isoformat(timespec="seconds")}
    loc = (core.maps_link(latitude, longitude) if latitude is not None and longitude is not None
           else "location share nahi hui")
    core.log(ctx.store, "emergency", {"user": ctx.user_id, "registration": ctx.registration, "issue": i["id"],
                                       "lat": latitude, "lon": longitude, "at": ctx.now.isoformat(timespec="seconds")})
    ctx.notify(ctx.manager_targets(), f"🚨 EMERGENCY {i['id']}: {ctx.registration}: {description}\n📍 {loc}",
               buttons=[{"text": "📞 Call driver", "action": f"call {i['id']}"}], kind="emergency")
    ctx.save_profile()
    tip = "" if latitude is not None else " Mumkin ho to apni location share karein (📎 → Location)."
    return {"ok": True, "issue_id": i["id"],
            "message": f"{core.SAFETY_ADVICE['accident']}\n🚨 Manager ko emergency alert bhej diya ({i['id']}).{tip}"}


@tool("find_service_slots", "Free workshop slots in the driver's city (next days, Mon-Sat). Optional filters: date "
      "(YYYY-MM-DD, e.g. tomorrow for 'kal') and part ('morning' before 12:00 / 'afternoon'). Show the driver exactly "
      "this list: their 'pehla'/'2' refers to its numbering.", DRIVER,
      {"limit": _INT, "date": _STR, "part": {"type": "string", "enum": ["morning", "afternoon"]}})
def find_service_slots(ctx, limit=6, date=None, part=None):
    v = _need_vehicle(ctx)
    free = [s for s in W.candidate_slots(v["city"], ctx.now) if not ctx.store.get(f"slot:{s['slot_id']}")
            and (not date or s["start"].date().isoformat() == str(date)[:10])
            and (part not in ("morning", "afternoon") or (s["start"].hour < 12) == (part == "morning"))]
    free = free[:max(1, min(int(limit), 10))]
    if not free:
        when = "Us waqt" if date or part else "Agle dino mein"
        return {"ok": True, "slots": [], "message": f"{when} koi slot khali nahi. Doosra din/waqt try karein ya "
                                                    f"manager se baat karein."}
    ctx.profile["last_offer"] = [s["slot_id"] for s in free]
    ctx.save_profile()
    lines = [f"{n}. {W.label(s)} ({s['slot_id']})" for n, s in enumerate(free, 1)]
    return {"ok": True, "slots": [{"slot_id": s["slot_id"], "label": W.label(s)} for s in free],
            "message": f"🔧 {v['city']} mein khali slots:\n" + "\n".join(lines)
                       + "\nNumber bhejein (jaise '1' ya 'pehla wala') ya slot code."}


_ORDINALS = {"pehla": 1, "pehle": 1, "pehli": 1, "first": 1, "doosra": 2, "dusra": 2, "doosre": 2, "second": 2,
             "teesra": 3, "tisra": 3, "third": 3, "chautha": 4, "fourth": 4}


def resolve_choice(ctx, choice):
    """'LHR1-20261021-09' / '2' / 'pehla wala' -> slot id from the last offer (or the code itself)."""
    text = str(choice).strip()
    m = W.SLOT_RE.search(text)
    if m:
        return m.group(0).upper()
    offer = ctx.profile.get("last_offer") or []
    num = next((n for w, n in _ORDINALS.items() if w in text.lower()), None)
    if num is None and text.isdigit():
        num = int(text)
    if num and 1 <= num <= len(offer):
        return offer[num - 1]
    return None


@tool("book_service", "Book a workshop slot. Pass the slot code exactly as listed (e.g. LHR1-20261022-09) for the "
      "slot the driver picked; a bare number/'pehla wala' means that position in the last find_service_slots list.",
      DRIVER, {"choice": _STR}, ["choice"])
def book_service(ctx, choice):
    v = _need_vehicle(ctx)
    slot_id = resolve_choice(ctx, choice)
    slot = W.parse_slot(slot_id) if slot_id else None
    if not slot:
        raise ValueError("Ye slot samajh nahi aaya. Pehle 'slot' likh kar list lein, phir number bhejein.")
    if slot["city"] != v["city"]:
        raise ValueError(f"Ye slot {slot['city']} ka hai; aap ki gaari {v['city']} ki hai.")
    if slot["start"] < ctx.now + timedelta(hours=1):
        raise ValueError("Ye waqt guzar chuka hai ya bohat qareeb hai. Naya slot chunein ('slot').")
    if slot["start"].weekday() == 6:
        raise ValueError("Itwar (Sunday) ko workshop band hai.")
    booking_id = core.next_id(ctx.store, "booking")
    if not ctx.store.set_nx(f"slot:{slot['slot_id']}", booking_id, ttl=14 * 24 * 3600):
        raise ValueError("Ye slot abhi kisi aur ne le liya. 'slot' likh kar naya chunein.")
    issue_id = ctx.profile.get("last_issue")
    issue = core.get_record(ctx.store, "issue", issue_id) if issue_id else None
    if issue and issue["status"] in ("open", "service_booked"):
        issue["status"] = "service_booked"
        core.save_record(ctx.store, "issue", issue)
    else:
        issue = None
    service = (issue or {}).get("suggested_service") or v.get("recommended_service")
    b = {"id": booking_id, "slot_id": slot["slot_id"], "registration": ctx.registration, "city": slot["city"],
         "workshop": slot["workshop"], "address": slot["address"], "start": slot["start"].isoformat(),
         "service": service, "issue_id": issue["id"] if issue else None, "driver": ctx.user_id,
         "status": "pending_approval", "created_at": ctx.now.isoformat(timespec="seconds")}
    core.save_record(ctx.store, "booking", b, new=True)
    ctx.notify(ctx.manager_targets(),
               f"🔧 Booking {booking_id}: {ctx.registration} · {service}\n{W.label(slot)}\n{slot['address']}"
               + (f"\nIssue: {issue['id']}" if issue else ""),
               buttons=[{"text": "✅ Approve", "action": f"approve {booking_id}"},
                        {"text": "🔁 Reschedule", "action": f"reschedule {booking_id}"}])
    ctx.emit("booking.created", b)
    return {"ok": True, "booking_id": booking_id,
            "message": f"✅ Booking {booking_id}: {W.label(slot)}\n📍 {slot['address']}\nService: {service}. "
                       f"Manager ki approval ka intezar hai; confirm hote hi aap ko bata dein ge."}


@tool("my_bookings", "The driver's own upcoming workshop bookings.", DRIVER)
def my_bookings(ctx):
    mine = [b for b in core.list_records(ctx.store, "booking")
            if b["registration"] == ctx.registration and b["status"] in ("pending_approval", "confirmed")
            and b["start"] >= ctx.now.isoformat()]
    if not mine:
        return {"ok": True, "bookings": [], "message": "Aap ki koi aane wali booking nahi. Slot ke liye 'slot' likhein."}
    lines = [f"• {b['id']}: {W.label(W.parse_slot(b['slot_id']))} ({'confirmed' if b['status'] == 'confirmed' else 'approval baqi'})"
             for b in mine]
    return {"ok": True, "bookings": [b["id"] for b in mine], "message": "📅 Aap ki bookings:\n" + "\n".join(lines)}


SAFETY_FORMULA = "Safety = 100 - 35 x harsh-braking events per 100 km (0-100)"


@tool("my_score", "Safety score of driving on the driver's own vehicle over the last 90 days, with tips.", DRIVER)
def my_score(ctx):
    v = _need_vehicle(ctx)
    since = (pd.Timestamp(C.END_DATE) - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    t = query("SELECT SUM(distance_km) km, SUM(harsh_braking_events) h FROM trips WHERE vehicle_id = ? AND trip_date > ?",
              (int(v["vehicle_id"]), since)).iloc[0]
    f = query("SELECT SUM(distance_km) km, SUM(harsh_braking_events) h FROM trips WHERE trip_date > ?", (since,)).iloc[0]
    h100, fleet = t.h / t.km * 100, f.h / f.km * 100
    score = max(0, min(100, round(100 - 35 * h100)))
    fleet_score = max(0, min(100, round(100 - 35 * fleet)))
    tip = ("Behtareen! Isi tarah aaram se brake lagate rahein." if score >= fleet_score
           else "Tip: aage wali gaari se fasla rakhein aur pehle se raftaar kam karein; achanak brake kam lagayein.")
    return {"ok": True, "score": score, "fleet_average": fleet_score,
            "message": f"🏅 {ctx.registration} par driving score: {score}/100 (fleet average {fleet_score}). "
                       f"Harsh braking {h100:.2f} har 100 km. {tip} (Pichle 90 din, demo data.)"}


@tool("my_vehicle", "The driver's own vehicle: AI breakdown risk, reasons and recommended service.", DRIVER)
def my_vehicle(ctx):
    v = _need_vehicle(ctx)
    return {"ok": True, "registration": ctx.registration, "risk_prob": v["risk_prob"], "risk_tier": v["risk_tier"],
            "message": f"🚐 {ctx.registration} ({v['make_model']}): AI breakdown risk {v['risk_prob']:.0%} "
                       f"({v['risk_tier']}). Wajah: {v['top_reasons']}. Tajweez: {v['recommended_service']}. "
                       f"(Demo data, 1 Jan 2026 tak.)"}
