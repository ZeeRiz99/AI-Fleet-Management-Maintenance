"""Offline keyword router: no API key, LLM budget used up, or an LLM error -> the SAME tools, chosen by keywords.
Understands Roman Urdu and English driver/manager messages."""
import re

import agent as legacy

from . import core
from . import registry as R
from . import workshops as W

_NUM = r"(\d[\d,]*(?:\.\d+)?)"


def _num(s):
    return float(s.replace(",", ""))


def parse_money(text):
    """'1 lakh' -> 100000, '50k' -> 50000, 'Rs 75,000' -> 75000."""
    t = text.lower()
    m = re.search(_NUM + r"\s*(lakh|lac|k\b|hazar|hazaar|thousand)?", t)
    if not m:
        return None
    value = _num(m.group(1))
    unit = m.group(2) or ""
    return value * (100_000 if unit in ("lakh", "lac") else 1000 if unit in ("k", "hazar", "hazaar", "thousand") else 1)


def parse_fuel(text):
    t = text.lower()
    litres = re.search(_NUM + r"\s*(?:l\b|ltr|litre|liter|lit\b)", t)
    km = re.search(_NUM + r"\s*km", t)
    odo = re.search(r"(?:meter|odometer|reading)\D{0,12}" + _NUM, t)
    amount = re.search(r"(?:rs\.?|rupay|rupees|pkr)\s*" + _NUM, t) or re.search(_NUM + r"\s*(?:rs|rupay|rupees|pkr)\b", t)
    return {"litres": _num(litres.group(1)) if litres else None, "km": _num(km.group(1)) if km else None,
            "odometer_km": _num(odo.group(1)) if odo else None, "amount_pkr": _num(amount.group(1)) if amount else None}


def _say(result):
    return result.get("message") or result.get("error") or "Maaf kijiye, ye samajh nahi aaya."


def driver(ctx, text):
    t = text.lower().strip()
    run = lambda name, **kw: _say(core.run_tool(ctx, name, kw))
    if W.SLOT_RE.search(text) or re.fullmatch(r"\d{1,2}", t) or re.search(r"\b(pehla|pehle|pehli|doosra|dusra|teesra|first|second|third)\b", t):
        if ctx.profile.get("last_offer") or W.SLOT_RE.search(text):
            return run("book_service", choice=text)
    if re.search(r"accident|takkar|hadsa|emergency|madad|help me", t):
        return run("report_emergency", description=text)
    if re.search(r"\bslot|booking kar|book kar|workshop|appointment|waqt chahiye|time chahiye", t):
        return run("find_service_slots")
    if re.search(r"meri booking|my booking|bookings", t):
        return run("my_bookings")
    if re.search(r"score|driving kaisi|meri driving|rating", t):
        return run("my_score")
    fuel = parse_fuel(text)
    if fuel["litres"] and re.search(r"fuel|petrol|diesel|tanki|bhar|fill|litre|liter|ltr", t):
        return run("log_fuel", **{k: v for k, v in fuel.items() if v is not None})
    if re.search(r"shift|chala raha|chalaunga|duty shuru|start kar|meter", t):
        return run("start_shift", odometer_km=fuel["odometer_km"] or (_num(m.group(1)) if (m := re.search(_NUM, t)) else None))
    if re.search(r"risk|meri gaari|my vehicle|gaari ki halat", t):
        return run("my_vehicle")
    category, _ = core.classify(text)
    if category != "other" or re.search(r"masla|problem|kharab|kharabi|issue|nahi chal|awaaz|awaz", t):
        return run("report_issue", description=text)
    return ("Main FleetLog AI hoon. Aap ye kar sakte hain:\n• masla batayein (voice note bhi): 'brake se awaaz aa rahi hai'\n"
            "• 'slot': workshop ka waqt\n• fuel: '45 litre, 300 km'\n• 'shift meter 45200'\n• 'mera score'\n"
            "• emergency: 'accident ho gaya'")


def manager(ctx, text):
    t = text.lower().strip()
    run = lambda name, **kw: _say(core.run_tool(ctx, name, kw))
    act = re.match(r"(approve|reschedule|resolve|call)\s+((?:bk|iss)-\d+)", t)
    if act:
        verb, rid = act.group(1), act.group(2).upper()
        name, key = {"approve": ("approve_booking", "booking_id"), "reschedule": ("reschedule_booking", "booking_id"),
                     "resolve": ("resolve_issue", "issue_id"), "call": ("call_driver", "issue_id")}[verb]
        return run(name, **{key: rid})
    if re.search(r"budget|plan", t) and parse_money(t):
        return run("plan_services", budget_pkr=parse_money(t))
    if re.search(r"what if|agar .*service|kya hoga", t):
        regs = [R.normalize(m.group(0)) for m in re.finditer(r"[a-z]{3}[\s\-]*\d{2}[\s\-]*\d{4}", t)]
        if regs:
            return run("what_if", registrations=regs)
    if re.search(r"brief|report de|subah|summary|aaj ka", t):
        return run("morning_brief")
    if re.search(r"issue|masle|masla|complain|reports?\b", t):
        return run("open_issues")
    if re.search(r"booking|slot|workshop", t):
        return run("upcoming_bookings")
    return legacy.answer_offline(text)  # existing data questions (risk, fuel, maintenance, drivers, a vehicle)


def route(ctx, text):
    return driver(ctx, text) if ctx.role == "driver" else manager(ctx, text)
