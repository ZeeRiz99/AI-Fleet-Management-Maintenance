"""Driver issue report as a LangGraph state graph:

    understand -> assess_risk -> decide -> record -> notify -> END

Deterministic (no LLM inside), so the offline router and the LLM agent run the very same steps. The LLM may pass
category/severity it understood from the message; otherwise keywords decide.
"""
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from . import core
from . import registry as R


class IssueState(TypedDict, total=False):
    ctx: object
    description: str
    category: Optional[str]
    severity: Optional[str]
    vehicle: dict
    escalate: bool
    service: str
    issue: dict


def understand(state):
    guess_cat, guess_sev = core.classify(state["description"])
    category = state.get("category") if state.get("category") in core.VALID_CATEGORIES else guess_cat
    severity = state.get("severity") if state.get("severity") in core.VALID_SEVERITIES else guess_sev
    # never let a model talk an accident or a keyword-critical complaint down
    if core.SEVERITY_RANK[guess_sev] > core.SEVERITY_RANK[severity]:
        severity = guess_sev
    if category == "other" and guess_cat != "other":
        category = guess_cat
    return {"category": category, "severity": severity}


def assess_risk(state):
    v = R.vehicle(state["ctx"].registration) or {}
    return {"vehicle": v}


def decide(state):
    v = state["vehicle"]
    service = core.SERVICE_FOR.get(state["category"]) or v.get("recommended_service") or "General Inspection"
    return {"escalate": core.should_escalate(state["severity"], state["category"], v.get("risk_tier")),
            "service": service}


def record(state):
    ctx, v = state["ctx"], state["vehicle"]
    issue = {
        "id": core.next_id(ctx.store, "issue"), "reporter": ctx.user_id, "registration": ctx.registration,
        "city": v.get("city"), "description": state["description"][:500], "category": state["category"],
        "severity": state["severity"], "status": "open", "escalated": state["escalate"],
        "suggested_service": state["service"], "model_service": v.get("recommended_service"),
        "risk_prob": v.get("risk_prob"), "risk_tier": v.get("risk_tier"), "top_reasons": v.get("top_reasons"),
        "created_at": ctx.now.isoformat(timespec="seconds"),
    }
    core.save_record(ctx.store, "issue", issue, new=True)
    ctx.profile["last_issue"] = issue["id"]
    return {"issue": issue}


def notify(state):
    ctx, i = state["ctx"], state["issue"]
    risk = f"{i['risk_prob']:.0%} ({i['risk_tier']})" if i.get("risk_prob") is not None else "n/a"
    text = (f"🔔 {'URGENT ' if i['escalated'] else ''}Driver report {i['id']}\n"
            f"Vehicle: {i['registration']} ({i['city']})\n"
            f"Masla: {i['description']}\n"
            f"Category: {i['category']} · severity: {i['severity']}\n"
            f"AI breakdown risk (data as of 1 Jan 2026): {risk}\n"
            f"Wajah: {i['top_reasons']}\n"
            f"Suggested: {i['suggested_service']}")
    if i["escalated"]:
        ctx.notify(ctx.manager_targets(), text, buttons=[
            {"text": "📞 Call driver", "action": f"call {i['id']}"},
            {"text": "✔ Resolved", "action": f"resolve {i['id']}"}])
    ctx.emit("issue.reported", i)
    return {}


def _build():
    g = StateGraph(IssueState)
    for name, fn in [("understand", understand), ("assess_risk", assess_risk), ("decide", decide),
                     ("record", record), ("notify", notify)]:
        g.add_node(name, fn)
    g.add_edge(START, "understand")
    g.add_edge("understand", "assess_risk")
    g.add_edge("assess_risk", "decide")
    g.add_edge("decide", "record")
    g.add_edge("record", "notify")
    g.add_edge("notify", END)
    return g.compile()


GRAPH = _build()


def run(ctx, description, category=None, severity=None):
    out = GRAPH.invoke({"ctx": ctx, "description": description, "category": category, "severity": severity})
    return out["issue"]
