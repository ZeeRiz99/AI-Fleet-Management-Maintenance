"""Fleet assistant: answers manager questions by calling tools on the database, alerts and models.

Three modes, same tools:
  * Gemini  - if GEMINI_API_KEY is set (free tier: https://aistudio.google.com/apikey), Gemini picks the tools.
  * Claude  - if ANTHROPIC_API_KEY is set, Claude picks the tools (manual tool-use loop).
  * Offline - otherwise (and whenever an LLM call fails, e.g. quota or network) a keyword router calls the same tools.
Run a quick chat:  python src/agent.py "Is hafte kaun si gaariyan risk mein hain?"
"""
import json
import os
import re
import time
import sys

import pandas as pd

import config as C
from db import query

MODEL = os.environ.get("FLEET_AGENT_MODEL", "claude-opus-5-5")
MAX_TOOL_ROUNDS = 6
SYSTEM = f"""You are the assistant of a fleet manager in Pakistan. You answer questions about vehicles, drivers, \
trips, fuel, maintenance and breakdown risk using ONLY the tools provided; never invent numbers. \
Money is in PKR (Rs), distance in km, fuel in litres. 'Today' is {C.AS_OF_DATE}; the data covers {C.START_DATE} to \
{C.END_DATE}. The data is a simulated demo fleet, and cost savings rest on assumptions in config.py \
(downtime cost, service risk reduction) - say so when you quote savings. Reply in the user's language \
(Roman Urdu or English), briefly, with small tables when listing several vehicles."""


def _alerts():
    path = C.PROCESSED / "alerts.csv"
    if not path.exists():
        from alerts import score_today
        score_today().to_csv(path, index=False)
    return pd.read_csv(path)


def _recent(days):
    return (pd.Timestamp(C.END_DATE) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


# ----------------------------------------------------------------------------- tools
def fleet_overview():
    a = _alerts()
    t = query("SELECT COUNT(*) trips, SUM(distance_km) km, SUM(fuel_litres) l, SUM(fuel_cost_pkr) cost FROM trips WHERE trip_date > ?", (_recent(30),))
    v = query("SELECT status, COUNT(*) n FROM vehicles GROUP BY status")
    m = query("SELECT COUNT(*) n, SUM(cost_pkr) cost FROM maintenance WHERE maintenance_date > ?", (_recent(30),))
    return {"vehicles": int(v.n.sum()), "by_status": dict(zip(v.status, v.n.astype(int))),
            "risk_tiers": a.risk_tier.value_counts().to_dict(),
            "last_30d": {"trips": int(t.trips[0]), "km": round(t.km[0]), "fuel_litres": round(t.l[0]),
                         "fuel_cost_pkr": round(t.cost[0]), "fuel_cost_per_km_pkr": round(t.cost[0] / t.km[0], 1),
                         "maintenance_jobs": int(m.n[0]), "maintenance_cost_pkr": round(m.cost[0] or 0)}}


def high_risk_vehicles(min_tier="Medium", limit=10):
    a = _alerts()
    order = {"High": 0, "Medium": 1, "Low": 2}
    a = a[a.risk_tier.map(order) <= order.get(min_tier, 1)].head(int(limit))
    return a[["registration", "make_model", "city", "risk_prob", "risk_tier", "recommended_service",
              "service_overdue_pct", "service_cost_pkr", "net_saving_pkr", "top_reasons"]].to_dict("records")


def vehicle_report(registration):
    a = _alerts()
    row = a[a.registration.str.upper() == registration.strip().upper()]
    if row.empty:
        return {"error": f"Vehicle {registration} not found"}
    r = row.iloc[0].to_dict()
    vid = int(r["vehicle_id"])
    since = _recent(90)
    t = query("SELECT COUNT(*) trips, SUM(distance_km) km, SUM(fuel_cost_pkr) cost, SUM(harsh_braking_events) harsh "
              "FROM trips WHERE vehicle_id = ? AND trip_date > ?", (vid, since))
    m = query("SELECT maintenance_date, maintenance_type, kind, cost_pkr FROM maintenance WHERE vehicle_id = ? "
              "ORDER BY maintenance_date DESC LIMIT 6", (vid,))
    return {"alert": r, "last_90d": {"trips": int(t.trips[0]), "km": round(t.km[0] or 0),
                                     "fuel_cost_pkr": round(t.cost[0] or 0), "harsh_braking": int(t.harsh[0] or 0)},
            "recent_maintenance": m.to_dict("records")}


def fuel_summary(days=30, group_by="vehicle", limit=10):
    col = {"vehicle": "v.registration", "model": "v.make_model", "depot": "d.city", "route": "t.route"}.get(group_by, "v.registration")
    df = query(f"""SELECT {col} AS grp, COUNT(*) trips, SUM(t.distance_km) km, SUM(t.fuel_litres) litres,
                          SUM(t.fuel_cost_pkr) cost FROM trips t JOIN vehicles v ON v.id = t.vehicle_id
                   JOIN depots d ON d.id = v.depot_id WHERE t.trip_date > ? GROUP BY grp""", (_recent(int(days)),))
    df["cost_per_km_pkr"] = (df.cost / df.km).round(1)
    df["km_per_litre"] = (df.km / df.litres).round(2)
    df = df.sort_values("cost_per_km_pkr", ascending=False).head(int(limit))
    return {"period_days": int(days), "group_by": group_by,
            "rows": df.round({"cost": 0, "km": 0, "litres": 0}).to_dict("records")}


def fuel_anomalies(days=90, limit=10):
    a = pd.read_csv(C.PROCESSED / "fuel_anomalies.csv")
    v = query("SELECT id vehicle_id, registration FROM vehicles")
    a = a[(a.flagged == 1) & (a.trip_date > _recent(int(days)))].merge(v, on="vehicle_id")
    by = a.groupby("registration").agg(flagged_trips=("id", "count"), excess_litres=("excess_litres", "sum"),
                                       excess_cost_pkr=("excess_cost_pkr", "sum")).nlargest(int(limit), "excess_cost_pkr")
    return {"period_days": int(days), "flagged_trips": int(len(a)), "total_excess_cost_pkr": round(a.excess_cost_pkr.sum()),
            "top_vehicles": by.round(0).reset_index().to_dict("records")}


def maintenance_costs(days=365, group_by="type"):
    col = {"type": "m.maintenance_type", "vehicle": "v.registration", "kind": "m.kind", "depot": "d.city"}.get(group_by, "m.maintenance_type")
    df = query(f"""SELECT {col} AS grp, COUNT(*) jobs, SUM(m.cost_pkr) cost, SUM(m.downtime_days) downtime_days
                   FROM maintenance m JOIN vehicles v ON v.id = m.vehicle_id JOIN depots d ON d.id = v.depot_id
                   WHERE m.maintenance_date > ? GROUP BY grp ORDER BY cost DESC LIMIT 12""", (_recent(int(days)),))
    return {"period_days": int(days), "group_by": group_by, "rows": df.round(0).to_dict("records")}


def driver_ranking(days=90, limit=8):
    df = query("""SELECT d.name, d.experience_years, COUNT(*) trips, SUM(t.distance_km) km,
                         SUM(t.harsh_braking_events) harsh FROM trips t JOIN drivers d ON d.id = t.driver_id
                  WHERE t.trip_date > ? GROUP BY d.id""", (_recent(int(days)),))
    df["harsh_per_100km"] = (df.harsh / df.km * 100).round(2)
    return {"period_days": int(days), "note": "higher harsh braking per 100 km = riskier driving",
            "rows": df.sort_values("harsh_per_100km", ascending=False).head(int(limit)).to_dict("records")}


FUNCS = {f.__name__: f for f in (fleet_overview, high_risk_vehicles, vehicle_report, fuel_summary,
                                 fuel_anomalies, maintenance_costs, driver_ranking)}


def _schema(name, desc, props=None, required=None):
    return {"name": name, "description": desc, "input_schema": {
        "type": "object", "properties": props or {}, "required": required or [], "additionalProperties": False}}


_INT, _STR = {"type": "integer"}, {"type": "string"}
TOOLS = [
    _schema("fleet_overview", "Fleet KPIs: vehicle counts, risk tiers, last-30-day trips, km, fuel and maintenance spend."),
    _schema("high_risk_vehicles", "Vehicles ranked by 30-day breakdown risk with reasons, recommended service and Rs saving.",
            {"min_tier": {"type": "string", "enum": ["High", "Medium", "Low"]}, "limit": _INT}),
    _schema("vehicle_report", "Full report for one vehicle by registration (risk, reasons, recent trips, maintenance).",
            {"registration": _STR}, ["registration"]),
    _schema("fuel_summary", "Fuel cost per km and km/litre grouped by vehicle, model, depot or route (worst first).",
            {"days": _INT, "group_by": {"type": "string", "enum": ["vehicle", "model", "depot", "route"]}, "limit": _INT}),
    _schema("fuel_anomalies", "Trips flagged as abnormal fuel use (possible leak/theft) with excess litres and Rs.",
            {"days": _INT, "limit": _INT}),
    _schema("maintenance_costs", "Maintenance spend and downtime grouped by type, vehicle, kind (preventive/breakdown) or depot.",
            {"days": _INT, "group_by": {"type": "string", "enum": ["type", "vehicle", "kind", "depot"]}}),
    _schema("driver_ranking", "Drivers ranked by harsh braking per 100 km.", {"days": _INT, "limit": _INT}),
]


def run_tool(name, args):
    try:
        return json.dumps(FUNCS[name](**args), default=str)
    except Exception as e:  # report to the model instead of crashing the chat
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


# ----------------------------------------------------------------------------- LLM mode
def answer_llm(question, history, api_key=None, client=None):
    import anthropic
    client = client or (anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic())
    messages = [*history, {"role": "user", "content": question}]
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(model=MODEL, max_tokens=4096, system=SYSTEM, tools=TOOLS, messages=messages)
        if resp.stop_reason == "refusal":
            return "Maaf kijiye, ye sawal main handle nahi kar sakta.", history
        calls = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not calls:
            text = "".join(b.text for b in resp.content if b.type == "text")
            return text, [*history, {"role": "user", "content": question}, {"role": "assistant", "content": text}]
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": run_tool(c.name, c.input)} for c in calls]})
    return "Jawab tayyar karne mein bohat tools lag gaye; sawal chhota kar ke dobara poochein.", history


# ----------------------------------------------------------------------------- Gemini mode (free tier)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
RETRY_DELAYS = (1.5, 3.0, 6.0)   # seconds between retries on transient server errors
TRANSIENT = (500, 503, 504)
_NOT_CHAT = ("lite", "image", "tts", "live", "audio", "embedding", "thinking", "robotics", "computer", "preview", "exp")


def ranked_gemini_models(models):
    """Chat-capable 'gemini-<version>-flash' / '-flash-lite' models, newest version first, plain flash before lite."""
    found = []
    for m in models:
        name = (getattr(m, "name", "") or "").removeprefix("models/")
        actions = getattr(m, "supported_actions", None) or []
        hit = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash(-lite)?", name)
        if hit and "generateContent" in actions and not any(w in name for w in _NOT_CHAT if w != "lite"):
            version = tuple(int(x) for x in hit.group(1).split("."))
            found.append(((tuple(-v for v in version), bool(hit.group(2))), name))
    return [name for _, name in sorted(found)]


def pick_gemini_model(models):
    """Newest plain flash model (not lite) that supports generateContent."""
    return next((n for n in ranked_gemini_models(models) if not n.endswith("-lite")), None)


def _call(client, model, contents, cfg):
    """One model, retrying transient server errors (500/503/504: Google is busy, usually clears in seconds)."""
    for delay in (*RETRY_DELAYS, None):
        try:
            return client.models.generate_content(model=model, contents=contents, config=cfg)
        except Exception as e:
            if getattr(e, "code", None) in TRANSIENT and delay is not None:
                time.sleep(delay)
                continue
            raise


def _generate(client, contents, cfg):
    """generate_content on GEMINI_MODEL; if it is gone (404) or its free quota is used up (429), move on to the
    next available flash / flash-lite model (each has its own free quota) and remember the one that worked."""
    global GEMINI_MODEL
    model, tried, candidates = GEMINI_MODEL, set(), None
    while True:
        tried.add(model)
        try:
            resp = _call(client, model, contents, cfg)
            GEMINI_MODEL = model
            return resp
        except Exception as e:
            if getattr(e, "code", None) not in (404, 429):
                raise
            if candidates is None:
                candidates = ranked_gemini_models(client.models.list())
            nxt = next((m for m in candidates if m not in tried), None)
            if nxt is None:
                raise
            model = nxt


def answer_gemini(question, history, api_key=None, client=None):
    """Same tools, via the Google Gemini API (google-genai SDK). Free-tier key: https://aistudio.google.com/apikey"""
    from google import genai
    from google.genai import types
    if client is None:
        client = genai.Client(api_key=api_key) if api_key else genai.Client()
    def plain(schema):  # Gemini rejects some JSON-Schema keywords (additionalProperties); keep the basics only
        return {k: v for k, v in schema.items() if k != "additionalProperties"}
    decls = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                       parameters_json_schema=plain(t["input_schema"])) for t in TOOLS]
    cfg = types.GenerateContentConfig(system_instruction=SYSTEM, tools=[types.Tool(function_declarations=decls)],
                                      automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    contents = [types.Content(role="user" if h["role"] == "user" else "model", parts=[types.Part(text=h["content"])])
                for h in history]
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    for _ in range(MAX_TOOL_ROUNDS):
        resp = _generate(client, contents, cfg)
        if not resp.candidates:  # blocked / empty
            return "Maaf kijiye, is sawal ka jawab nahi mil saka.", history
        content = resp.candidates[0].content
        calls = [p.function_call for p in (content.parts or []) if p.function_call]
        if not calls:
            text = "".join(p.text or "" for p in (content.parts or []) if getattr(p, "text", None)).strip()
            text = text or "Maaf kijiye, jawab khali aaya; sawal dobara poochein."
            return text, [*history, {"role": "user", "content": question}, {"role": "assistant", "content": text}]
        contents.append(content)
        contents.append(types.Content(role="user", parts=[
            types.Part.from_function_response(name=c.name, response={"result": json.loads(run_tool(c.name, dict(c.args or {})))})
            for c in calls]))
    return "Jawab tayyar karne mein bohat tools lag gaye; sawal chhota kar ke dobara poochein.", history


# ----------------------------------------------------------------------------- offline mode
HEADERS = {"registration": "Vehicle", "make_model": "Model", "risk_prob": "Risk", "risk_tier": "Tier",
           "recommended_service": "Recommended service", "net_saving_pkr": "Net saving (Rs)", "grp": "Group",
           "km": "km", "litres": "Litres", "cost": "Cost (Rs)", "cost_per_km_pkr": "Rs/km", "km_per_litre": "km/L",
           "flagged_trips": "Flagged trips", "excess_litres": "Excess L", "excess_cost_pkr": "Excess (Rs)",
           "maintenance_date": "Date", "maintenance_type": "Service", "kind": "Type", "cost_pkr": "Cost (Rs)",
           "jobs": "Jobs", "downtime_days": "Downtime (days)", "name": "Driver", "experience_years": "Experience (yrs)",
           "trips": "Trips", "harsh_per_100km": "Harsh braking /100km"}


def _md(rows, cols):
    if not rows:
        return "_(koi record nahi)_"
    head = "| " + " | ".join(HEADERS.get(c, c) for c in cols) + " |\n|" + "---|" * len(cols)
    body = ["| " + " | ".join(f"{r.get(c, ''):,.2f}".rstrip("0").rstrip(".") if isinstance(r.get(c), float) else
                              f"{r.get(c, ''):,}" if isinstance(r.get(c), int) else str(r.get(c, "")) for c in cols) + " |" for r in rows]
    return head + "\n" + "\n".join(body)


def _days(q, default):
    m = re.search(r"(\d+)\s*(din|day|days|d)\b", q)
    if m:
        return int(m.group(1))
    if re.search(r"haft|week", q):       # "is haftay", "this week", "pichle hafte"
        return 7
    if re.search(r"mah?ine|month", q):   # "is mahine", "this month"
        return 30
    return default


def answer_offline(question):
    q = question.lower()
    plate = re.search(r"\b([a-z]{3}-\d{2}-\d{4})\b", q)
    if plate:
        r = vehicle_report(plate.group(1))
        if "error" in r:
            return r["error"]
        a = r["alert"]
        return (f"**{a['registration']}** ({a['make_model']}, {a['city']}): risk {a['risk_prob']:.0%} ({a['risk_tier']}).\n"
                f"- Wajah: {a['top_reasons']}\n- Tajweez: {a['recommended_service']} (Rs {a['service_cost_pkr']:,.0f}), "
                f"mumkina bachat Rs {a['net_saving_pkr']:,.0f}\n- Pichle 90 din: {r['last_90d']['trips']} trips, "
                f"{r['last_90d']['km']:,} km, fuel Rs {r['last_90d']['fuel_cost_pkr']:,}, harsh braking {r['last_90d']['harsh_braking']}\n\n"
                + _md(r["recent_maintenance"], ["maintenance_date", "maintenance_type", "kind", "cost_pkr"]))
    if any(k in q for k in ("anomal", "chori", "leak", "theft", "ghalat fuel", "suspicious")):
        r = fuel_anomalies(_days(q, 90))
        return (f"Pichle {r['period_days']} din mein {r['flagged_trips']} trips mein ghair-mamooli fuel use mila "
                f"(Rs {r['total_excess_cost_pkr']:,} ka ziyada fuel).\n\n"
                + _md(r["top_vehicles"], ["registration", "flagged_trips", "excess_litres", "excess_cost_pkr"]))
    if any(k in q for k in ("risk", "khatr", "breakdown", "kharab", "service", "gaari", "gari", "vehicle")) and "fuel" not in q:
        r = high_risk_vehicles("Medium", 10)
        return ("Agle 30 din mein breakdown ke sab se zyada risk wali gaariyan:\n\n"
                + _md(r, ["registration", "make_model", "risk_prob", "risk_tier", "recommended_service", "net_saving_pkr"]))
    if "fuel" in q or "petrol" in q or "diesel" in q:
        total_q = any(k in q for k in ("kharcha", "kharch", "kitna", "total", "spend", "expense"))
        g = ("model" if "model" in q else "depot" if ("depot" in q or "city" in q or "sheher" in q) else
             "route" if "route" in q else "depot" if total_q else "vehicle")
        days = _days(q, 30)
        r = fuel_summary(days, g, limit=50)
        tot = query("SELECT SUM(fuel_cost_pkr) c, SUM(fuel_litres) l, SUM(distance_km) k FROM trips WHERE trip_date > ?",
                    (_recent(days),)).iloc[0]
        head = (f"Pichle {days} din (data {C.END_DATE} tak) ka total fuel kharcha: **Rs {tot.c:,.0f}** "
                f"({tot.l:,.0f} litre, {tot.k:,.0f} km, Rs {tot.c / tot.k:,.1f}/km).\n\n")
        return (head + f"{g} ke hisaab se (mehnga pehle):\n\n"
                + _md(r["rows"][:10], ["grp", "km", "litres", "cost", "cost_per_km_pkr", "km_per_litre"]))
    if any(k in q for k in ("maintenance", "repair", "marammat", "kharcha", "cost")):
        g = "vehicle" if "vehicle" in q or "gaari" in q else "kind" if "breakdown" in q else "type"
        r = maintenance_costs(_days(q, 365), g)
        return f"Maintenance kharcha ({g} ke hisaab se, pichle {r['period_days']} din):\n\n" + _md(r["rows"], ["grp", "jobs", "cost", "downtime_days"])
    if "driver" in q or "dryver" in q:
        r = driver_ranking(_days(q, 90))
        return r["note"] + ":\n\n" + _md(r["rows"], ["name", "experience_years", "trips", "km", "harsh_per_100km"])
    o = fleet_overview()
    l = o["last_30d"]
    return (f"Fleet: {o['vehicles']} vehicles, risk tiers {o['risk_tiers']}. Pichle 30 din: {l['trips']:,} trips, {l['km']:,} km, "
            f"fuel Rs {l['fuel_cost_pkr']:,} (Rs {l['fuel_cost_per_km_pkr']}/km), maintenance Rs {l['maintenance_cost_pkr']:,}.\n\n"
            "Aap poochh sakte hain: *risk wali gaariyan*, *fuel cost per km depot ke hisaab se*, *fuel chori/anomaly*, "
            "*maintenance kharcha*, *driver ranking*, ya kisi gaari ka number (jaise BAB-21-6978).")


# ----------------------------------------------------------------------------- entry point
def resolve_provider(api_key=None):
    """-> (provider, key). provider is 'gemini', 'anthropic' or 'offline'.

    An explicit key (pasted in the dashboard) wins; 'sk-ant...' means Anthropic, anything else Gemini.
    Otherwise env vars: GEMINI_API_KEY / GOOGLE_API_KEY (free tier, preferred) then ANTHROPIC_API_KEY.
    FLEET_LLM_PROVIDER=offline|gemini|anthropic forces a choice.
    """
    forced = os.environ.get("FLEET_LLM_PROVIDER", "auto").lower()
    if forced == "offline":
        return "offline", None
    if api_key:
        return ("anthropic" if api_key.startswith("sk-ant") else "gemini"), api_key
    gem = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    ant = os.environ.get("ANTHROPIC_API_KEY")
    if forced == "anthropic" and ant:
        return "anthropic", ant
    if forced == "gemini" and gem:
        return "gemini", gem
    if forced == "auto":
        if gem:
            return "gemini", gem
        if ant:
            return "anthropic", ant
    return "offline", None


def mode_label(api_key=None):
    provider, _ = resolve_provider(api_key)
    return {"gemini": f"Gemini ({GEMINI_MODEL}) with tools", "anthropic": f"Claude ({MODEL}) with tools",
            "offline": "Offline keyword assistant (add a free Gemini key for open-ended questions)"}[provider]


def _why(e, key=None):
    """Short, human-readable reason for an LLM failure. Keys are redacted from anything shown."""
    code = getattr(e, "code", None)
    status = getattr(e, "status", None)
    msg = str(getattr(e, "message", None) or e)
    if key:
        msg = msg.replace(key, "***")
    msg = re.sub(r"AIza[0-9A-Za-z_\-]{20,}|sk-ant-[0-9A-Za-z_\-]{10,}", "***", msg)
    first = (msg.strip().splitlines() or [""])[0][:240]
    low = (msg + str(status)).lower()
    if code == 429 or "resource_exhausted" in low or "quota" in low:
        hint = "free-tier limit poori ho gayi (1-2 minute baad ya kal try karein, ya doosri key use karein)"
    elif code in (401, 403) or "api key" in low or "api_key" in low or "permission" in low:
        hint = "API key sahi nahi lagti"
    elif code in (500, 503, 504) or "unavailable" in low or "high demand" in low:
        hint = "Gemini par abhi load zyada hai (kuch der baad dobara try karein)"
    elif code == 404 or "not found" in low:
        hint = "model ka naam sahi nahi/hata diya gaya (GEMINI_MODEL set karein)"
    elif code == 400:
        hint = "request qabool nahi hui"
    else:
        hint = type(e).__name__
    detail = f" [{code or ''} {status or ''}: {first}]" if first else ""
    return hint + detail


def answer(question, history=None, api_key=None):
    """Returns (reply_text, new_history). Gemini / Claude when a key is available, else (or on any failure) offline."""
    history = history or []
    provider, key = resolve_provider(api_key)
    if provider != "offline":
        try:
            fn = answer_gemini if provider == "gemini" else answer_llm
            return fn(question, history, api_key=key)
        except Exception as e:  # network / auth / rate-limit: degrade gracefully, never crash the chat
            note = f"\n\n_({provider} se jawab nahi mila: {_why(e, key)}; offline mode se jawab diya)_"
            return answer_offline(question) + note, history
    return answer_offline(question), history


if __name__ == "__main__":
    print(answer(" ".join(sys.argv[1:]) or "fleet overview")[0])
