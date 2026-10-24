"""All FleetLog AI settings come from environment variables (see .env.example), so a client deployment changes
configuration, not code."""
import os
from dataclasses import dataclass, field


def _flag(name, default=False):
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _digits(number):
    return "".join(ch for ch in number if ch.isdigit())  # "+92 300-1234567" -> "923001234567"


def _list(name):
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


@dataclass
class Settings:
    demo_mode: bool = field(default_factory=lambda: _flag("OPS_DEMO_MODE", True))
    restrict_manager: bool = field(default_factory=lambda: _flag("OPS_RESTRICT_MANAGER"))
    max_llm_calls_per_day: int = field(default_factory=lambda: _int("OPS_MAX_LLM_CALLS_PER_DAY", 400))
    max_msgs_per_user_day: int = field(default_factory=lambda: _int("OPS_MAX_MSGS_PER_USER_DAY", 200))
    max_message_chars: int = field(default_factory=lambda: _int("OPS_MAX_MESSAGE_CHARS", 2000))
    history_turns: int = 10
    history_ttl_s: int = 2 * 24 * 3600
    # manager targets: "telegram:<chat_id>" / "whatsapp:<number>" ids that always receive alerts
    manager_ids: list = field(default_factory=lambda: [f"telegram:{x}" for x in _list("TELEGRAM_MANAGER_CHAT_IDS")]
                              + [f"whatsapp:{_digits(x)}" for x in _list("WHATSAPP_MANAGER_NUMBERS")])
    # store: Upstash Redis REST when configured, else SQLite file
    redis_url: str = field(default_factory=lambda: os.environ.get("UPSTASH_REDIS_REST_URL", ""))
    redis_token: str = field(default_factory=lambda: os.environ.get("UPSTASH_REDIS_REST_TOKEN", ""))
    sqlite_path: str = field(default_factory=lambda: os.environ.get("OPS_SQLITE_PATH", ""))


def load():
    return Settings()
