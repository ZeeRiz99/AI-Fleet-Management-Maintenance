"""Demo workshops and their appointment slots (Asia/Karachi time; Pakistan has no daylight saving: UTC+5)."""
import re
from datetime import datetime, timedelta, timezone

PKT = timezone(timedelta(hours=5), "PKT")
SLOT_HOURS = (9, 11, 14, 16)
DAYS_AHEAD = 4

# Placeholder names: clearly demo workshops, not real businesses.
WORKSHOPS = {
    "Lahore": [("LHR1", "Lahore Workshop 1 (demo)", "Ferozepur Road, Lahore"),
               ("LHR2", "Lahore Workshop 2 (demo)", "Ring Road, Lahore")],
    "Islamabad": [("ISB1", "Islamabad Workshop 1 (demo)", "I-9 Industrial Area, Islamabad"),
                  ("ISB2", "Islamabad Workshop 2 (demo)", "Kahuta Road, Islamabad")],
    "Karachi": [("KHI1", "Karachi Workshop 1 (demo)", "SITE Area, Karachi"),
                ("KHI2", "Karachi Workshop 2 (demo)", "Korangi Industrial Area, Karachi")],
}
_BY_CODE = {code: (city, name, addr) for city, ws in WORKSHOPS.items() for code, name, addr in ws}
SLOT_RE = re.compile(r"\b([A-Z]{3}\d)-(\d{8})-(\d{2})\b", re.IGNORECASE)


def now_pkt():
    return datetime.now(PKT)


def slot_id(code, start):
    return f"{code}-{start:%Y%m%d}-{start:%H}"


def parse_slot(slot):
    """'LHR1-20261021-09' -> dict(code, city, workshop, address, start) or None."""
    m = SLOT_RE.fullmatch((slot or "").strip())
    if not m or m.group(1).upper() not in _BY_CODE:
        return None
    code = m.group(1).upper()
    try:
        start = datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H").replace(tzinfo=PKT)
    except ValueError:
        return None
    if start.hour not in SLOT_HOURS:
        return None
    city, name, addr = _BY_CODE[code]
    return {"slot_id": slot_id(code, start), "code": code, "city": city, "workshop": name, "address": addr,
            "start": start}


def candidate_slots(city, now=None, limit=6):
    """Upcoming slots in a city: Mon-Sat, the 4 slot hours, at least 1 hour from now, both workshops."""
    now = now or now_pkt()
    out = []
    for day in range(DAYS_AHEAD + 1):
        date = (now + timedelta(days=day)).date()
        if date.weekday() == 6:  # Sunday closed
            continue
        for hour in SLOT_HOURS:
            start = datetime(date.year, date.month, date.day, hour, tzinfo=PKT)
            if start < now + timedelta(hours=1):
                continue
            for code, name, addr in WORKSHOPS.get(city, []):
                out.append({"slot_id": slot_id(code, start), "code": code, "city": city, "workshop": name,
                            "address": addr, "start": start})
    return out


def label(slot):
    start = slot["start"]
    return f"{start:%a %d %b, %I:%M %p} · {slot['workshop']}"
