"""Shared pieces: per-message context, records (issues, bookings, logs), complaint classification, escalation rule
and the tool registry used by both the LLM agent and the offline router."""
import re
from dataclasses import dataclass, field
from datetime import datetime

from . import workshops as W


# ----------------------------------------------------------------------------- context
@dataclass
class Ctx:
    store: object
    settings: object
    user_id: str                      # "telegram:123", "whatsapp:9230...", "app:<session>", "test:..."
    profile: dict = field(default_factory=dict)
    now: datetime = field(default_factory=W.now_pkt)
    events: list = field(default_factory=list)

    @property
    def role(self):
        return self.profile.get("role")

    @property
    def registration(self):
        return self.profile.get("registration")

    def save_profile(self):
        self.store.set(f"profile:{self.user_id}", self.profile)

    def notify(self, to, text, buttons=None, kind="manager_alert"):
        """Queue an outgoing message; channels deliver it (Phase 2+). `to` = list of user ids."""
        # kept even with no targets yet: demo mode shows the reporter what the manager would receive
        targets = [t for t in dict.fromkeys(to) if t]
        self.events.append({"type": "notify", "kind": kind, "to": targets, "text": text, "buttons": buttons or []})

    def emit(self, name, data):
        """Queue a webhook event (n8n / Apps Script: Sheets, email)."""
        self.events.append({"type": "event", "name": name, "data": data})

    def manager_targets(self):
        return list(dict.fromkeys([*self.settings.manager_ids, *sorted(self.store.smembers("subscribers"))]))


def load_profile(store, user_id):
    return store.get(f"profile:{user_id}", {}) or {}


# ----------------------------------------------------------------------------- records
def next_id(store, kind):
    base = {"issue": ("ISS", 1000), "booking": ("BK", 2000)}[kind]
    return f"{base[0]}-{base[1] + store.incr(f'seq:{kind}')}"


def save_record(store, kind, record, new=False):
    store.set(f"{kind}:{record['id']}", record)
    if new:
        store.rpush(f"{kind}s:all", record["id"])


def get_record(store, kind, record_id):
    return store.get(f"{kind}:{(record_id or '').upper()}")


def list_records(store, kind, last=200):
    ids = store.lrange(f"{kind}s:all", -last, -1)
    return [r for r in (store.get(f"{kind}:{i}") for i in ids) if r]


def log(store, kind, record):
    """Append-only driver logs (shift, fuel, pretrip, emergency): the 'Fleet Log' that real data would come from."""
    store.rpush(f"log:{kind}", record)


# ----------------------------------------------------------------------------- complaint understanding
CATEGORY_WORDS = [
    ("accident", r"accident|takkar|tak+ar|hadsa|hadisa|collision|crash|ulat"),
    ("overheating", r"overheat|garam|garmi|heat|temperature|temp\b|ubal|boil|coolant|radiator"),
    ("brakes", r"brake|break|bre?k|brk"),
    ("tyres", r"tyre|tire|puncture|pankchar|panchar|wheel|pahiya|pahia"),
    ("electrical", r"battery|light|bijli|wiring|electric|start nahi|self|horn|indicator"),
    ("fuel", r"fuel|petrol|diesel|tanki|leak|mileage|average kam"),
    ("engine", r"engine|injan|smoke|dhuan|dhuaan|dhoan|knock|awaaz|awaz|noise|vibration|jhatk|oil"),
]
SEVERITY_WORDS = [
    ("critical", r"fail|nahi ruk|nahin ruk|rukti nahi|band ho gay|aag|fire|dhuan|dhuaan|smoke|accident|takkar|hadsa|"
                 r"bilkul kaam nahi|khatarnak|dangerous|critical"),
    ("high", r"bohat|bahut|buhat|zyada|ziyada|tez|serious|severe|loud|kafi|high"),
    ("low", r"thora|thoda|thori|thodi|halki|halka|kabhi kabhi|minor|low|chota"),
]
SERVICE_FOR = {"brakes": "Brake Inspection", "overheating": "Coolant Flush", "engine": "Engine Tune-Up",
               "tyres": "Tire Rotation", "electrical": "Battery Replacement", "fuel": "Engine Tune-Up"}
SAFETY_ADVICE = {
    "brakes": "⚠️ Hifazat pehle: gaari aahista chalayein, mehfooz jagah rok dein, brake ki halat check hone tak lambi trip na karein.",
    "overheating": "⚠️ Hifazat pehle: gaari foran mehfooz jagah rok kar engine band karein. Radiator ka dhakkan garam halat mein mat kholiye.",
    "accident": "🚨 Hifazat pehle: sab theek hain to gaari side par lagayein, hazard lights on karein. Zakhmi hon to 1122 / 115 par call karein.",
    "critical": "⚠️ Hifazat pehle: gaari mehfooz jagah rok dein aur manager ki hidayat ka intezar karein.",
}
VALID_CATEGORIES = ("brakes", "engine", "tyres", "electrical", "fuel", "overheating", "accident", "other")
VALID_SEVERITIES = ("low", "medium", "high", "critical")
SEVERITY_RANK = {s: i for i, s in enumerate(VALID_SEVERITIES)}


def classify(text):
    """Keyword guess of (category, severity) for Roman Urdu / English complaints; LLMs may override both."""
    t = (text or "").lower()
    category = next((c for c, rx in CATEGORY_WORDS if re.search(rx, t)), "other")
    severity = next((s for s, rx in SEVERITY_WORDS if re.search(rx, t)), "medium")
    if category == "accident" and SEVERITY_RANK[severity] < SEVERITY_RANK["high"]:
        severity = "high"
    return category, severity


def should_escalate(severity, category, risk_tier):
    """Spec rule: high/critical severity, OR a High-risk vehicle, OR brakes/accident/overheating at >= medium."""
    rank = SEVERITY_RANK.get(severity, 1)
    return (rank >= SEVERITY_RANK["high"] or risk_tier == "High"
            or (category in ("brakes", "accident", "overheating") and rank >= SEVERITY_RANK["medium"]))


def safety_advice(category, severity):
    if category in SAFETY_ADVICE:
        return SAFETY_ADVICE[category]
    return SAFETY_ADVICE["critical"] if severity == "critical" else ""


# ----------------------------------------------------------------------------- tool registry
TOOLS = {}


def tool(name, description, roles, params=None, required=None):
    """Register a tool for the LLM agent (OpenAI function schema) and the offline router. Tools take (ctx, **args)
    and return a dict with a ready-to-send Roman Urdu 'message' (used as-is by the offline router)."""
    def wrap(fn):
        TOOLS[name] = {"name": name, "description": description, "roles": set(roles), "fn": fn,
                       "parameters": {"type": "object", "properties": params or {}, "required": required or []}}
        return fn
    return wrap


def tools_for(role):
    return [t for t in TOOLS.values() if role in t["roles"]]


def run_tool(ctx, name, args):
    """Execute a tool for this user; role checks live here so neither the LLM nor the router can bypass them."""
    spec = TOOLS.get(name)
    if spec is None:
        return {"ok": False, "error": f"Unknown tool {name}"}
    if ctx.role not in spec["roles"]:
        return {"ok": False, "error": "Ye kaam aap ke role ke liye nahi hai.", "message": "Ye kaam aap ke role ke liye nahi hai."}
    try:
        return spec["fn"](ctx, **(args or {}))
    except TypeError as e:
        return {"ok": False, "error": f"Bad arguments: {e}"}
    except ValueError as e:
        return {"ok": False, "error": str(e), "message": str(e)}


def pkr(x):
    return f"Rs {float(x):,.0f}"


def maps_link(lat, lon):
    return f"https://maps.google.com/?q={lat},{lon}"


def recent(ctx, stamped, minutes):
    """`stamped` ({..., "at": iso time}) if it is at most `minutes` old, else None."""
    try:
        age = ctx.now - datetime.fromisoformat(stamped["at"])
    except (TypeError, KeyError, ValueError):
        return None
    return stamped if age.total_seconds() <= minutes * 60 else None
