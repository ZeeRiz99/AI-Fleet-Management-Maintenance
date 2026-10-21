"""Provider-agnostic LLM access through the OpenAI-compatible chat-completions API.

Gemini, Groq and Ollama (and LM Studio, OpenRouter, Mistral) all speak this format, so a provider is just
base_url + key + model. The chain tries them in order; if all fail the caller falls back to the offline router.
Model names are defaults only: set OPS_*_MODEL in the environment (and verify they still exist) when deploying.
"""
import json
import os
import time
import urllib.request


class LLMUnavailable(Exception):
    pass


class Provider:
    def __init__(self, name, base_url, api_key, model, transport=None, timeout=40):
        self.name, self.base_url, self.api_key, self.model = name, base_url.rstrip("/"), api_key, model
        self.timeout = timeout
        self.transport = transport or self._http

    def _http(self, url, headers, payload):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def chat(self, messages, tools=None):
        payload = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = self.transport(f"{self.base_url}/chat/completions", headers, payload)
        try:
            return body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMUnavailable(f"{self.name}: unexpected response") from None


class Chain:
    """Try each provider in order; remember nothing between calls (serverless-friendly)."""

    COOLDOWN_S = 120  # a provider that just failed (busy/quota/timeout) is skipped for a while, not waited on again

    def __init__(self, providers, clock=time.monotonic):
        self.providers = list(providers)
        self.last_used = None
        self.clock = clock
        self.resting = {}  # provider index -> time it may be tried again

    def __bool__(self):
        return bool(self.providers)

    @property
    def label(self):
        return " → ".join(f"{p.name}({p.model})" for p in self.providers) or "offline"

    def chat(self, messages, tools=None):
        errors = []
        now = self.clock()
        ready = [i for i in range(len(self.providers)) if self.resting.get(i, 0) <= now]
        for i in ready or range(len(self.providers)):  # all resting: try them all anyway
            p = self.providers[i]
            try:
                msg = p.chat(messages, tools)
                self.last_used = p.name
                self.resting.pop(i, None)
                return msg
            except Exception as e:  # quota, network, bad key: rest it and try the next provider
                self.resting[i] = self.clock() + self.COOLDOWN_S
                errors.append(f"{p.name}({p.model}): {type(e).__name__}")
        raise LLMUnavailable("; ".join(errors) or "no provider configured")


def models(value):
    """'a, b' -> ['a', 'b']: several models per provider, tried in order (free tiers often answer 503 'busy')."""
    return [m.strip() for m in (value or "").split(",") if m.strip()]


def from_env():
    env = os.environ.get
    providers = []
    if env("GEMINI_API_KEY") or env("GOOGLE_API_KEY"):
        for m in models(env("OPS_GEMINI_MODEL", "gemini-3.8-flash,gemini-3.5-flash")):
            providers.append(Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                                      env("GEMINI_API_KEY") or env("GOOGLE_API_KEY"), m, timeout=25))
    if env("GROQ_API_KEY"):
        for m in models(env("OPS_GROQ_MODEL", "openai/gpt-oss-120b")):
            providers.append(Provider("groq", "https://api.groq.com/openai/v1", env("GROQ_API_KEY"), m, timeout=25))
    if env("OLLAMA_BASE_URL"):  # e.g. http://localhost:11434/v1 (only reachable when the laptop runs it)
        providers.append(Provider("ollama", env("OLLAMA_BASE_URL"), None, env("OPS_OLLAMA_MODEL", "qwen2.5:3b"),
                                  timeout=120))
    if env("OPS_LLM_PROVIDER", "").lower() == "offline":
        providers = []
    return Chain(providers)
