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
import logging
import re
from datetime import datetime
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from . import core, env, llm as LLM, registry as R, router
from . import settings as S
from . import store as ST
from . import tools_driver, tools_manager  # noqa: F401  (registers the tools)
from . import workshops as W

log = logging.getLogger("fleetlog.brain")
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
    buttons: list


def _system_prompt(ctx):
    who = (f"The user is a DRIVER of vehicle {ctx.registration}." if ctx.role == "driver"
           else "The user is the fleet MANAGER.")
    return (
        "You are FleetLog AI, the AI Fleet Log Assistant of a Pakistani fleet (km, litres, PKR). "
        f"Current time: {ctx.now:%A %d %B %Y, %H:%M} PKT. {who} "
        "Reply in the user's language and script (Roman Urdu, Urdu or English), short and friendly. "
        "Use ONLY tool results for facts and numbers; never invent data. Never say something was booked, reported, "
        "logged or approved unless you called that tool in this turn and it returned ok. "
        "Vehicle risk data is a simulated demo fleet "
        "scored as of 1 Jan 2026; say so when quoting risk or savings. "
        "Driver workflow: (1) understand the problem, (2) call report_issue (safety advice comes first in its "
        "message), (3) offer find_service_slots (use its date/part filters for 'kal subah' etc. and show its list "
        "as is), (4) book_service with the exact slot code of the slot the driver picked, (5) say it is booked and "
        "waiting for the manager's approval (not 'confirmed' until the manager approves). "
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
    done = []  # messages of tools already run this turn: never run them twice through the offline router
    ran, safety = set(), []
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            msg = chain.chat(messages, tools)
            calls = msg.get("tool_calls") or []
            if not calls:
                text = plain(msg.get("content") or "")
                problem = ungrounded(text, ran, json.dumps(messages, ensure_ascii=False, default=str))
                if problem:  # the model claimed an action it did not take, or a number no tool gave
                    log.warning("LLM reply rejected (%s): %s", chain.last_used, problem)
                    break
                if text:  # safety advice always leads (spec), whatever the model wrote
                    # live: the model re-worded the advice ("Gaari ... aur brake ..."), so any safety line counts
                    lead = [] if "hifazatpehle" in _letters(text) else safety
                    return {"reply": "\n".join([*lead, text]), "mode": f"llm:{chain.last_used}"}
                break
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                fn = c.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = core.run_tool(ctx, fn.get("name"), args)
                if result.get("ok"):
                    ran.add(fn.get("name"))
                    if result.get("safety") and result["safety"] not in safety:
                        safety.append(result["safety"])
                    if result.get("message"):
                        done.append(result["message"])
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": json.dumps(result, default=str)})
    except LLM.LLMUnavailable as e:
        log.warning("LLM unavailable, %s: %s", "using tool results" if done else "offline router", e)
    if done:
        return {"reply": "\n\n".join(done), "mode": "tools"}
    return {"mode": "offline"}


# Live finding (Groq/qwen): a model said "book kar diya" without calling book_service, and invented a driving score.
# Prompts are not a guarantee, so replies are checked: claimed actions need the tool, numbers need a source.
CLAIMS = [
    (r"book kar (diya|di|liya|li)|booking (ho gayi|kar di)|\bbooked\b", {"book_service", "my_bookings",
                                                                         "upcoming_bookings"}),
    (r"report (ban|bana|darj)|report kar (diya|di)|\breported\b", {"report_issue", "report_emergency",
                                                                   "pretrip_check", "open_issues"}),
    (r"approve kar (diya|di)|approve ho (gayi|gaya)", {"approve_booking"}),
    (r"resolve kar (diya|di)|resolve ho (gaya|gayi)", {"resolve_issue"}),
    (r"fuel log|log kar (diya|di)|darj kar (diya|di)", {"log_fuel", "start_shift", "report_issue"}),
]
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")


def _numbers(text):
    return {part.lstrip("0") or "0" for tok in _NUMBER.findall(text) for part in re.split(r"[.,:]", tok)}


def ungrounded(reply, ran, sources):
    """Why the reply cannot be trusted, or None. `sources` = everything the model was given this turn (system
    prompt, history, user text, tool results)."""
    low = reply.lower()
    for pattern, tools in CLAIMS:
        if re.search(pattern, low) and not ran & tools:
            return f"claims '{re.search(pattern, low).group(0)}' without {sorted(tools)[0]}"
    invented = _numbers(reply) - _numbers(sources)
    return f"numbers not from any tool: {sorted(invented)[:5]}" if invented else None


def _letters(text):
    """Comparable form: models re-type emoji (with/without variation selectors), spaces and punctuation."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def plain(text):
    """Chat apps show text as is: drop markdown emphasis/headings the model may still produce."""
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"(?m)^#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^(\s*)[*-]\s+", r"\1• ", text)
    return text.strip()


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
    reply, buttons = _demo_copy(ctx, reply)
    ctx.save_profile()
    return {"reply": reply, "buttons": buttons}


def _demo_copy(ctx, reply):
    """Demo mode: the reporter also sees what the manager received (with its buttons), unless they got it directly."""
    if not ctx.settings.demo_mode:
        return reply, []
    alerts = [e for e in ctx.events if e["type"] == "notify" and e["kind"] in ("manager_alert", "emergency")
              and ctx.user_id not in e["to"]]
    if alerts:
        reply += "\n\n" + "\n\n".join(f"{DEMO_HEADER}\n{e['text']}" for e in alerts)
    return reply, [b for e in alerts for b in e["buttons"]]


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
        env.load()
        settings = S.load()
        _DEFAULT.update(settings=settings, store=ST.from_settings(settings), chain=LLM.from_env())
    return _DEFAULT


def _ctx(user_id, store, settings, now):
    d = _defaults() if (store is None or settings is None) else {}
    store, settings = store or d["store"], settings or d["settings"]
    return core.Ctx(store=store, settings=settings, user_id=user_id, profile=core.load_profile(store, user_id),
                    now=now or W.now_pkt())


def _out(ctx, reply, mode, buttons=()):
    return {"reply": reply, "mode": mode, "events": ctx.events, "buttons": list(buttons),
            "profile": {k: v for k, v in ctx.profile.items() if k in ("role", "registration")}}


def handle(user_id, text, *, store=None, settings=None, chain=None, now: Optional[datetime] = None):
    ctx = _ctx(user_id, store, settings, now)
    chain = _defaults()["chain"] if chain is None else chain
    out = GRAPH.invoke({"ctx": ctx, "text": text or "", "chain": chain})
    return _out(ctx, out["reply"], out.get("mode", "offline"), out.get("buttons", []))


def share_location(user_id, latitude, longitude, *, store=None, settings=None, now: Optional[datetime] = None):
    """A shared location pin (Telegram/WhatsApp). Kept on the profile for a later emergency report; within an hour
    after an emergency it goes straight to the manager."""
    ctx = _ctx(user_id, store, settings, now)
    ctx.profile["location"] = {"lat": latitude, "lon": longitude, "at": ctx.now.isoformat(timespec="seconds")}
    emergency = core.recent(ctx, ctx.profile.get("last_emergency"), minutes=60)
    if ctx.role == "driver" and emergency:
        ctx.notify(ctx.manager_targets(),
                   f"📍 Live location {emergency['id']} ({ctx.registration}): {core.maps_link(latitude, longitude)}",
                   buttons=[{"text": "📞 Call driver", "action": f"call {emergency['id']}"}], kind="emergency")
        reply = f"📍 Location manager ko bhej di ({emergency['id']}). Mehfooz jagah rahein."
    else:
        reply = "📍 Location mil gayi. Emergency ho to 'emergency' ya 'accident' likhein: location saath jayegi."
    core.log(ctx.store, "location", {"user": user_id, "registration": ctx.registration, **ctx.profile["location"]})
    reply, buttons = _demo_copy(ctx, reply)
    ctx.save_profile()
    return _out(ctx, reply, "command", buttons)
