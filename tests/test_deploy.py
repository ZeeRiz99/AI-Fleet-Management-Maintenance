"""FleetLog AI phase 3: the Vercel bundle is self-contained and serves /health without the repo around it."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.skipif(not (ROOT / "data" / "fleet.db").exists(), reason="run the pipeline first")

from ops import vercel_bundle as VB  # noqa: E402

PROBE = """
import json, sys
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
import index
c = TestClient(index.app)
h = c.get("/health").json()
bad = c.post("/webhooks/telegram", json={"update_id": 1}).status_code
mods = sorted({m.__file__ for m in sys.modules.values() if getattr(m, "__file__", None) and "Fleet Management AI" in m.__file__ and ".venv" not in m.__file__
               and "build" not in m.__file__})
print(json.dumps({"health": h, "unauthorised": bad, "outside": mods}))
"""


def test_bundle_is_self_contained_and_serves(tmp_path):
    out = tmp_path / "vercel"
    VB.build(out)
    assert json.loads((out / "vercel.json").read_text())["crons"][0]["path"] == "/cron/morning"
    assert "uvicorn" not in (out / "requirements.txt").read_text()
    assert not (out / ".env").exists() and not list(out.rglob("__pycache__"))
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("OPS_", "GEMINI", "GROQ", "TELEGRAM",
                                                                       "UPSTASH", "WHATSAPP", "FLEET_"))}
    clean.update(OPS_SQLITE_PATH=str(tmp_path / "ops.db"), FLEET_DB_PATH=str(out / "data" / "fleet.db"),
                 OPS_LLM_PROVIDER="offline")
    # -I: isolated mode (no PYTHONPATH, no script dir), run from the bundle like the Vercel runtime
    r = subprocess.run([sys.executable, "-I", "-c", PROBE], cwd=out, env=clean, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["health"]["ok"] and got["health"]["llm"] == "offline"
    assert got["unauthorised"] == 403                       # no secret configured: webhook stays closed
    assert got["outside"] == []                              # nothing imported from the repo outside the bundle


def test_env_names_cover_the_settings_used_on_vercel():
    code = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "ops").glob("*.py") if p.name != "vercel_bundle.py")
    for name in VB.REQUIRED + VB.OPTIONAL:
        assert name in code or name.startswith(("WHATSAPP", "OPS_EVENTS", "OPS_APP", "CRON", "OPS_BRIEF")), name
    assert not set(VB.LOCAL_ONLY) & set(VB.REQUIRED + VB.OPTIONAL)
