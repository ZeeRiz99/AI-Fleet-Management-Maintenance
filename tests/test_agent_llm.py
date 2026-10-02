"""Tool-calling loops for Gemini and Claude, tested with fake clients (no network, no keys).
These prove the loop logic, tool execution and fallback; they do NOT prove the live APIs accept the requests."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import agent  # noqa: E402
import config as C  # noqa: E402

pytestmark = pytest.mark.skipif(not C.DB_PATH.exists(), reason="run src/run_pipeline.py first")
ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "FLEET_LLM_PROVIDER")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)


def test_provider_resolution(monkeypatch):
    assert agent.resolve_provider() == ("offline", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert agent.resolve_provider()[0] == "anthropic"
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    assert agent.resolve_provider()[0] == "gemini"          # free tier preferred
    assert agent.resolve_provider("sk-ant-pasted") == ("anthropic", "sk-ant-pasted")
    assert agent.resolve_provider("AIzaPasted") == ("gemini", "AIzaPasted")
    monkeypatch.setenv("FLEET_LLM_PROVIDER", "offline")
    assert agent.resolve_provider("AIzaPasted") == ("offline", None)


def test_gemini_loop_executes_tools_and_returns_text():
    from google.genai import types
    first = NS(candidates=[NS(content=types.Content(role="model", parts=[types.Part(
        function_call=types.FunctionCall(name="high_risk_vehicles", args={"min_tier": "High", "limit": 2}))]))])
    final = NS(candidates=[NS(content=types.Content(role="model", parts=[types.Part(text="Do gaariyan risk mein hain.")]))])
    seen = []

    class Models:
        script = [first, final]

        def generate_content(self, model, contents, config):
            seen.append((model, list(contents), config))
            return self.script.pop(0)

    text, hist = agent.answer_gemini("risk wali gaariyan?", [], client=NS(models=Models()))
    assert text == "Do gaariyan risk mein hain."
    assert hist[-2:] == [{"role": "user", "content": "risk wali gaariyan?"}, {"role": "assistant", "content": text}]
    # the 2nd request carried the tool result (real vehicle data), and tools were declared on the config
    result_part = seen[1][1][-1].parts[0].function_response
    assert result_part.name == "high_risk_vehicles" and "registration" in str(result_part.response)
    assert [d.name for d in seen[0][2].tools[0].function_declarations] == [t["name"] for t in agent.TOOLS]


def test_gemini_empty_response_is_handled():
    class Models:
        def generate_content(self, **kw):
            return NS(candidates=[])
    text, _ = agent.answer_gemini("hi", [], client=NS(models=Models()))
    assert "Maaf" in text


def test_claude_loop_executes_tools_and_returns_text():
    use = NS(type="tool_use", id="t1", name="fleet_overview", input={})
    first = NS(stop_reason="tool_use", content=[use])
    final = NS(stop_reason="end_turn", content=[NS(type="text", text="Fleet theek hai.")])
    sent = []

    class Messages:
        script = [first, final]

        def create(self, **kw):
            sent.append([dict(m) for m in kw["messages"]])
            return self.script.pop(0)

    text, _ = agent.answer_llm("overview", [], client=NS(messages=Messages()))
    assert text == "Fleet theek hai."
    tool_result = sent[1][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "t1" and "vehicles" in tool_result["content"]


def test_llm_failure_falls_back_to_offline(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")

    def boom(*a, **k):
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
    monkeypatch.setattr(agent, "answer_gemini", boom)
    text, _ = agent.answer("risk wali gaariyan")
    assert "registration" in text.lower() or "Vehicle" in text      # offline table still delivered
    assert "free-tier" in text


def test_bad_key_message_never_leaks_the_key(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("API key not valid. key=AIzaSECRET123456789012345")
    monkeypatch.setattr(agent, "answer_gemini", boom)
    text, _ = agent.answer("fleet overview", api_key="AIzaSECRET123456789012345")
    assert "SECRET123" not in text and "key sahi nahi" in text


def _m(name, actions=("generateContent",)):
    return NS(name=f"models/{name}", supported_actions=list(actions))


def test_pick_gemini_model_chooses_newest_plain_flash():
    models = [_m("gemini-2.5-flash"), _m("gemini-3.8-flash"), _m("gemini-3.8-flash-lite"), _m("gemini-4.0-flash-preview"),
              _m("gemini-3.10-flash"), _m("gemini-9-flash-image"), _m("gemini-9-flash", actions=["embedContent"]),
              _m("gemini-3.8-pro")]
    assert agent.pick_gemini_model(models) == "gemini-3.10-flash"   # 3.10 > 3.8 numerically, not as a string
    assert agent.pick_gemini_model([_m("gemini-3.8-pro")]) is None


def test_generate_retries_with_discovered_model_on_404(monkeypatch):
    monkeypatch.setattr(agent, "GEMINI_MODEL", "gemini-old-flash")
    calls = []

    class NotFound(Exception):
        code = 404

    class Models:
        def generate_content(self, model, contents, config):
            calls.append(model)
            if model == "gemini-old-flash":
                raise NotFound("model retired")
            return "ok"

        def list(self):
            return [_m("gemini-7.1-flash")]

    assert agent._generate(NS(models=Models()), [], None) == "ok"
    assert calls == ["gemini-old-flash", "gemini-7.1-flash"] and agent.GEMINI_MODEL == "gemini-7.1-flash"


def test_generate_does_not_swallow_other_errors(monkeypatch):
    class BadKey(Exception):
        code = 401

    class Models:
        def generate_content(self, **kw):
            raise BadKey("API key not valid")

    with pytest.raises(BadKey):          # auth errors are not retried and do not trigger model fallback
        agent._generate(NS(models=Models()), [], None)


def test_generate_retries_transient_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(agent, "RETRY_DELAYS", (0, 0, 0))
    attempts = []

    class Busy(Exception):
        code = 503

    class Models:
        def generate_content(self, model, contents, config):
            attempts.append(1)
            if len(attempts) < 3:
                raise Busy("high demand")
            return "ok"

    assert agent._generate(NS(models=Models()), [], None) == "ok" and len(attempts) == 3


def test_generate_gives_up_after_retries_and_message_is_friendly(monkeypatch):
    monkeypatch.setattr(agent, "RETRY_DELAYS", (0, 0))

    class Busy(Exception):
        code = 503

    class Models:
        n = 0

        def generate_content(self, **kw):
            Models.n += 1
            raise Busy("This model is currently experiencing high demand.")

    with pytest.raises(Busy):
        agent._generate(NS(models=Models()), [], None)
    assert Models.n == 3                                       # 1 try + 2 retries
    assert "load zyada" in agent._why(Busy("high demand"))


def test_ranked_models_order_newest_first_and_lite_last():
    models = [_m("gemini-3.8-flash-lite"), _m("gemini-3.8-flash"), _m("gemini-3.10-flash"), _m("gemini-2.5-flash"),
              _m("gemini-3.8-pro"), _m("gemini-3.9-flash-live")]
    assert agent.ranked_gemini_models(models) == ["gemini-3.10-flash", "gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-2.5-flash"]


def test_quota_429_falls_through_to_next_model_and_remembers_it(monkeypatch):
    monkeypatch.setattr(agent, "GEMINI_MODEL", "gemini-3.8-flash")
    calls = []

    class Quota(Exception):
        code = 429

    class Models:
        def generate_content(self, model, contents, config):
            calls.append(model)
            if model != "gemini-3.8-flash-lite":
                raise Quota("exceeded")
            return "ok"

        def list(self):
            return [_m("gemini-3.8-flash"), _m("gemini-3.8-flash-lite"), _m("gemini-2.5-flash")]

    assert agent._generate(NS(models=Models()), [], None) == "ok"
    assert calls == ["gemini-3.8-flash", "gemini-3.8-flash-lite"] and agent.GEMINI_MODEL == "gemini-3.8-flash-lite"


def test_all_models_out_of_quota_raises_so_chat_falls_back_to_offline(monkeypatch):
    monkeypatch.setattr(agent, "GEMINI_MODEL", "gemini-3.8-flash")

    class Quota(Exception):
        code = 429

    class Models:
        def generate_content(self, **kw):
            raise Quota("exceeded")

        def list(self):
            return [_m("gemini-3.8-flash"), _m("gemini-3.8-flash-lite")]

    with pytest.raises(Quota):
        agent._generate(NS(models=Models()), [], None)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setattr(agent, "answer_gemini", lambda *a, **k: (_ for _ in ()).throw(Quota("exceeded")))
    text, _ = agent.answer("fleet overview")
    assert "free-tier" in text and "Fleet:" in text
