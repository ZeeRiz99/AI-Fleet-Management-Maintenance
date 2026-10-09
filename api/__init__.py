"""FastAPI backend for the FleetAI Android app (and any other client).

Reuses the existing src/ modules (database access, features, XGBoost risk model, SHAP, fuel-anomaly output).
It works on its own copy of the database (data/runtime/), so the committed data/fleet.db and the Streamlit
dashboard are never modified by API writes.
Run:  uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
