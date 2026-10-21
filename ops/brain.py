"""FleetLog AI brain: one entry point for every channel.

    handle(user_id, text) -> {"reply", "mode", "events", "profile"}

LangGraph flow:  guard -> identify -> (command | agent | offline) -> finalize
* guard     message length + per-user daily cap
* identify  short commands (/start, driver <REG>, manager, subscribe, brief, reset, approve BK-.., ...)
* agent     LLM with role-scoped tools (provider chain), daily LLM budget; any failure -> offline
* offline   keyword router running the same tools
* finalize  demo copy of manager alerts, chat history (without the demo copy)
"""
import json
import re
from datetime import datetime
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from . import core, llm as LLM, registry as R, router
from . import settings as S
from . import store as ST
from . import tools_driver, tools_manager  # noqa: F401  (registers the tools)
from . import workshops as W

MAX_TOOL_ROUNDS = 6
DEMO_HEADER = "— Demo: manager ko ye alert gaya —"
HELP = ("👋 FleetLog AI — AI Fleet Log Assistant\n"
        "Driver: 'driver LEA-22-2030' likhein, phir masla, fuel, shift ya 'slot'. Voice note bhi chalega.\n"
        "Manager: 'manager' likhein; alerts ke liye 'subscribe'; subah ki report: 'brief'.\n"
        "Naya shuru: 'reset'.")


class State(TypedDict, total=False):
    ctx: object
    text: str
    reply: str
    mode: str
    chain: object


def _system_prompt(ctx):
    who = (f"The user is a DRIVER of vehicle {ctx.registration}." if ctx.role == "driver"
           else "The user is the fleet MANAGER.")
    return (
        "You are FleetLog AI, the AI Fleet Log Assistant of a Pakistani fleet (km, litres, PKR). "
        f"Current time: {ctx.now:%A %d %B %Y, %H:%M} PKT. {who} "
        "Reply in the user's language and script (Roman Urdu, Urdu or English), short and friendly. "
        "Use ONLY tool results for facts and numbers; never invent data. Vehicle risk data is a simulated demo fleet "
        "scored as of 1 Jan 2026; say so when quoting risk or savings. "
        "Driver workflow: (1) understand the problem, (2) call report_issue (safety advice comes first in its "
        "message), (3) offer find_service_slots, (4) book_service when the driver picks one, (5) confirm. "
        "Fuel fill-ups -> log_fuel; shift start -> start_shift; accidents/emergencies -> report_emergency. "
        "A driver may only see their own vehicle; refuse other vehicles, costs and fleet-wide data. "
        "Chat formatting: plain text and • bullet lines; no markdown tables or headings. "
        "When a tool returns a 'message', you may pass it on as is.")


def _history_key(ctx):
    return f"hist:{ctx.user_id}"


def _history(ctx):
    return ctx.store.lrange(_history_key(ctx), -2 * ctx.settings.history_turns, -1)


# ----------------------------------------------------------------------------- nodes
def guard(state):
    ctx, text = state["ctx"], state["text"]
    if not text.strip():
        return {"reply": "Kuch likhein ya voice note bhejein.", "mode": "command"}
    if len(text) > ctx.settings.max_message_chars:
        return {"reply": f"Paigham bohat lamba hai (zyada se zyada {ctx.settings.max_message_chars} huroof).",
                "mode": "command"}
    n = ctx.store.incr(f"rate:{ctx.user_id}:{ctx.now:%Y%m%d}", ttl=26 * 3600)
    if n > ctx.settings.max_msgs_per_user_day:
        return {"reply": "Aaj ki had poori ho gayi. Kal dobara koshish karein.", "mode": "command"}
    return {}


def identify(state):
    ctx, text = state["ctx"], state["text"].strip()
    low = text.lower()
    words = low.split()
    reg = R.find_registration(text)
    if low.startswith("driver") and reg:
        ctx.profile["role"] = "driver"
        r = core.run_tool(ctx, "set_my_vehicle", {"registration": reg})
        if not r.get("ok"):
            ctx.profile.pop("role", None)
            return {"reply": r.get("message") or r.get("error"), "mode": "command"}
        return {"reply": r["message"] + "\nAb masla, fuel, shift ya 'slot' likhein (voice note bhi chalega).",
                "mode": "command"}
    if not (len(words) <= 3 or low.startswith("/")):
        return {}
    cmd = words[0].lstrip("/") if words else ""
    if cmd in ("start", "help", "madad") and len(words) == 1:
        return {"reply": HELP, "mode": "command"}
    if cmd == "reset":
        ctx.store.delete(_history_key(ctx))
        ctx.profile.clear()
        ctx.save_profile()
        return {"reply": "Sab saaf. " + HELP, "mode": "command"}
    if cmd == "manager":
        if ctx.settings.restrict_manager and ctx.user_id not in ctx.settings.manager_ids:
            return {"reply": "Manager mode sirf registered managers ke liye hai.", "mode": "command"}
        ctx.profile.update(role="manager")
        ctx.profile.pop("registration", None)
        ctx.save_profile()
        return {"reply": "✅ Manager mode. Poochein: 'brief', 'issues', 'bookings', 'budget 1 lakh', ya koi bhi sawal. "
                         "Alerts ke liye 'subscribe'.", "mode": "command"}
    if cmd in ("subscribe", "unsubscribe"):
        if ctx.role != "manager":
            return {"reply": "Pehle 'manager' likhein.", "mode": "command"}
        (ctx.store.sadd if cmd == "subscribe" else ctx.store.srem)("subscribers", ctx.user_id)
        return {"reply": "🔔 Alerts on." if cmd == "subscribe" else "🔕 Alerts off.", "mode": "command"}
    if not ctx.role:
        if reg:  # a bare registration starts driver mode too
            return identify({**state, "text": f"driver {reg}"})
        return {"reply": "Pehle batayein aap kaun hain:\n• driver ho to: 'driver LEA-22-2030'\n• manager ho to: 'manager'",
                "mode": "command"}
    if cmd == "brief" and ctx.role == "manager":
        return {"reply": core.run_tool(ctx, "morning_brief", {})["message"], "mode": "command"}
    if ctx.role == "manager" and re.match(r"(approve|reschedule|resolve|call)\s+(bk|iss)-\d+$", low):
        return {"reply": router.manager(ctx, text), "mode": "command"}
    return {}


def agent(state):
    ctx, chain = state["ctx"], state["chain"]
    used = ctx.store.incr(f"llm:{ctx.now:%Y%m%d}", ttl=26 * 3600)
    if used > ctx.settings.max_llm_calls_per_day:
        return {"mode": "offline"}
    tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                               "parameters": t["parameters"]}} for t in core.tools_for(ctx.role)]
    messages = [{"role": "system", "content": _system_prompt(ctx)}, *_history(ctx),
                {"role": "user", "content": state["text"]}]
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            msg = chain.chat(messages, tools)
            calls = msg.get("tool_calls") or []
            if not calls:
                text = (msg.get("content") or "").strip()
                return {"reply": text, "mode": f"llm:{chain.last_used}"} if text else {"mode": "offline"}
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                fn = c.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = core.run_tool(ctx, fn.get("name"), args)
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": json.dumps(result, default=str)})
    except LLM.LLMUnavailable:
        return {"mode": "offline"}
    return {"mode": "offline"}


def offline(state):
    ctx = state["ctx"]
    if ctx.role == "driver" and not ctx.registration:
        return {"reply": "Pehle gaari ka number batayein: 'driver LEA-22-2030'", "mode": "offline"}
    reg = R.find_registration(state["text"])
    if ctx.role == "driver" and reg and reg != ctx.registration and R.vehicle(reg):
        core.run_tool(ctx, "set_my_vehicle", {"registration": reg})  # "aaj LEA-22-2030 chala raha hoon"
    return {"reply": router.route(ctx, state["text"]), "mode": "offline"}


def finalize(state):
    ctx, reply = state["ctx"], state.get("reply") or "…"
    if state.get("mode") != "command":
        ctx.store.rpush(_history_key(ctx), {"role": "user", "content": state["text"]}, ttl=ctx.settings.history_ttl_s)
        ctx.store.rpush(_history_key(ctx), {"role": "assistant", "content": reply}, ttl=ctx.settings.history_ttl_s)
        ctx.store.ltrim(_history_key(ctx), -2 * ctx.settings.history_turns, -1)
    if ctx.settings.demo_mode:
        alerts = [e for e in ctx.events if e["type"] == "notify" and e["kind"] in ("manager_alert", "emergency")
                  and ctx.user_id not in e["to"]]
        if alerts:
            reply += "\n\n" + "\n\n".join(f"{DEMO_HEADER}\n{e['text']}" for e in alerts)
    ctx.save_profile()
    return {"reply": reply}


# ----------------------------------------------------------------------------- graph
def _after_guard(state):
    return "finalize" if state.get("reply") else "identify"


def _after_identify(state):
    if state.get("reply"):
        return "finalize"
    chain = state.get("chain")
    return "agent" if chain else "offline"


def _after_agent(state):
    return "finalize" if state.get("reply") else "offline"


def _build():
    g = StateGraph(State)
    for name, fn in [("guard", guard), ("identify", identify), ("agent", agent), ("offline", offline),
                     ("finalize", finalize)]:
        g.add_node(name, fn)
    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", _after_guard, ["identify", "finalize"])
    g.add_conditional_edges("identify", _after_identify, ["agent", "offline", "finalize"])
    g.add_conditional_edges("agent", _after_agent, ["offline", "finalize"])
    g.add_edge("offline", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


GRAPH = _build()
_DEFAULT = {}


def _defaults():
    if not _DEFAULT:
        settings = S.load()
        _DEFAULT.update(settings=settings, store=ST.from_settings(settings), chain=LLM.from_env())
    return _DEFAULT


def handle(user_id, text, *, store=None, settings=None, chain=None, now: Optional[datetime] = None):
    d = _defaults() if (store is None or settings is None or chain is None) else {}
    store = store or d["store"]
    settings = settings or d["settings"]
    chain = d["chain"] if chain is None else chain
    ctx = core.Ctx(store=store, settings=settings, user_id=user_id, profile=core.load_profile(store, user_id),
                   now=now or W.now_pkt())
    out = GRAPH.invoke({"ctx": ctx, "text": text or "", "chain": chain})
    return {"reply": out["reply"], "mode": out.get("mode", "offline"), "events": ctx.events,
            "profile": {k: v for k, v in ctx.profile.items() if k in ("role", "registration")}}
