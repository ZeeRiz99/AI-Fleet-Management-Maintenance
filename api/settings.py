"""API configuration from environment variables (nothing secret is hard-coded)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DB = ROOT / "data" / "fleet.db"
RUNTIME_DIR = Path(os.environ.get("FLEET_RUNTIME_DIR", ROOT / "data" / "runtime"))
RUNTIME_DB = RUNTIME_DIR / "fleet_api.db"   # working copy the API reads and writes
STATE_DB = RUNTIME_DIR / "app_state.db"     # users, alert read-state, JWT secret

API_VERSION = "1.0.0"
TOKEN_MINUTES = int(os.environ.get("FLEET_TOKEN_MINUTES", "720"))
JWT_SECRET = os.environ.get("FLEET_API_SECRET")          # unset -> random secret generated once, stored in STATE_DB

ADMIN_USER = os.environ.get("FLEET_ADMIN_USER", "admin")
ADMIN_NAME = os.environ.get("FLEET_ADMIN_NAME", "Fleet Manager")
ADMIN_PASSWORD = os.environ.get("FLEET_ADMIN_PASSWORD")  # unset -> local demo password below (logged as a warning)
DEMO_PASSWORD = "fleet123"
