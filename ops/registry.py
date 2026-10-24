"""Vehicles known to the agent (from the scored snapshot data/processed/alerts.csv) and registration parsing."""
import json
import re
from functools import lru_cache

import pandas as pd

import config as C

from . import ROOT

# "lea 22 2030", "LEA222030", "lea-22-2030", "LEA 22-2030" -> "LEA-22-2030"
_REG = re.compile(r"\b([a-z]{3})[\s\-_.]*(\d{2})[\s\-_.]*(\d{4})\b", re.IGNORECASE)
CITY_CODE = {"Lahore": "LHR", "Islamabad": "ISB", "Karachi": "KHI"}


def find_registration(text):
    """First registration-looking token in free text, normalised (not validated)."""
    m = _REG.search(text or "")
    return f"{m.group(1).upper()}-{m.group(2)}-{m.group(3)}" if m else None


def normalize(text):
    return find_registration(text)


@lru_cache(maxsize=1)
def _alerts():
    a = pd.read_csv(C.PROCESSED / "alerts.csv")
    return {r["registration"]: r for r in a.to_dict("records")}


def vehicle(registration):
    """Scored snapshot row for a registration, or None if the fleet has no such vehicle."""
    return _alerts().get((registration or "").upper())


def all_vehicles():
    return list(_alerts().values())


@lru_cache(maxsize=1)
def fuel_baselines():
    """Per-vehicle median km/l over the previous trips + the anomaly threshold (exported with the API snapshot)."""
    path = ROOT / "static-api" / "v1" / "fuel" / "baselines.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    by_reg = {v["registration"]: v for v in data["vehicles"].values()}
    return data["threshold"], by_reg
