"""Minimal .env loader (python-dotenv style, no dependency): KEY=value lines, optional quotes, inline # comments.
Existing environment variables win, so a host's settings (Vercel, Render) are never overridden by a stray file."""
import os
import re

from . import ROOT

_LINE = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_value(raw):
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end > 0 else raw[1:]
    return re.split(r"\s+#|^#", raw, maxsplit=1)[0].strip()


def load(path=None, override=False):
    """Load ROOT/.env (or `path`) into os.environ; returns the names that were set (never the values)."""
    path = path or ROOT / ".env"
    if not os.path.isfile(path):
        return []
    loaded = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            m = _LINE.match(line)
            if not m or line.lstrip().startswith("#"):
                continue
            name, value = m.group(1), parse_value(m.group(2))
            if value and (override or not os.environ.get(name)):
                os.environ[name] = value
                loaded.append(name)
    return loaded
