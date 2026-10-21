"""FleetLog AI — AI Fleet Log Assistant (driver + manager agent). Spec: docs/fleetlog-ai/SPEC.md"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:  # reuse src/config.py, src/db.py, src/agent.py
    sys.path.insert(0, str(ROOT / "src"))
