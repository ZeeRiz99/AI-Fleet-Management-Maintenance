"""Sanity tests for data, features (no leakage), models, alerts and the assistant.
Run:  python -m pytest -q      (needs the pipeline outputs: python src/run_pipeline.py)
"""
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import agent  # noqa: E402
import config as C  # noqa: E402
from db import query  # noqa: E402

pytestmark = pytest.mark.skipif(not C.DB_PATH.exists(), reason="run src/run_pipeline.py first")


def test_unit_conversions():
    assert C.MPG_TO_KM_PER_L == pytest.approx(0.4251, abs=1e-3)
    assert C.FUEL_PRICE_NOW == {"Petrol": 387.40, "Diesel": 400.35}


def test_tables_have_expected_shape_and_integrity():
    v, d, t, m = (query(f"SELECT * FROM {n}") for n in ("vehicles", "drivers", "trips", "maintenance"))
    assert len(v) == 58 and len(d) == C.N_DRIVERS
    assert t.vehicle_id.isin(v.id).all() and t.driver_id.isin(d.id).all() and m.vehicle_id.isin(v.id).all()
    assert t.isna().sum().sum() == 0 and m.isna().sum().sum() == 0
    assert t.distance_km.between(C.TRIP_KM_MIN - 1, C.TRIP_KM_MAX + 1).all()
    assert (t.fuel_litres > 0).all()
    assert (t.fuel_cost_pkr - t.fuel_litres * t.fuel_price_per_litre).abs().max() < 1.0  # rounding only
    assert t.trip_date.min() >= C.START_DATE and t.trip_date.max() <= C.END_DATE
    assert (m[m.kind == "Breakdown"].downtime_days > 0).all() and (m[m.kind == "Preventive"].downtime_days == 0).all()


def test_odometer_never_decreases_per_vehicle():
    t = query("SELECT vehicle_id, odometer_end_km FROM trips ORDER BY vehicle_id, trip_date, id")
    assert (t.groupby("vehicle_id").odometer_end_km.diff().dropna() > 0).all()


def test_fuel_prices_follow_current_rates_at_the_end():
    t = query("SELECT v.fuel_type, t.fuel_price_per_litre p FROM trips t JOIN vehicles v ON v.id = t.vehicle_id "
              "WHERE t.trip_date >= '2025-12-01'")
    for fuel, price in C.FUEL_PRICE_NOW.items():
        assert t[t.fuel_type == fuel].p.mean() == pytest.approx(price, rel=0.05)


@pytest.fixture(scope="module")
def feats():
    return pd.read_csv(C.PROCESSED / "features.csv", parse_dates=["snapshot_date"])


def test_features_use_only_past_data_and_labels_match(feats):
    rng = np.random.default_rng(0)
    trips = query("SELECT vehicle_id, trip_date, odometer_end_km FROM trips ORDER BY trip_date, id")
    bd = query("SELECT vehicle_id, maintenance_date FROM maintenance WHERE kind = 'Breakdown'")
    for _, r in feats.iloc[rng.choice(len(feats), 40, replace=False)].iterrows():
        d = r.snapshot_date
        past = trips[(trips.vehicle_id == r.vehicle_id) & (pd.to_datetime(trips.trip_date) < d)]
        assert r.odometer_km == past.odometer_end_km.iloc[-1], "odometer must come from trips before the snapshot"
        b = pd.to_datetime(bd[bd.vehicle_id == r.vehicle_id].maintenance_date)
        assert r.breakdown_next_30d == int(((b >= d) & (b < d + pd.Timedelta(days=30))).any())


def test_features_reasonable(feats):
    assert 0.05 < feats.breakdown_next_30d.mean() < 0.40
    assert feats.snapshot_date.min() >= pd.Timestamp(C.START_DATE) + pd.Timedelta(days=150)
    assert feats.snapshot_date.max() <= pd.Timestamp(C.END_DATE) - pd.Timedelta(days=29)


def test_model_artifact_and_no_leaky_features():
    art = joblib.load(ROOT / "models" / "risk_model.joblib")
    assert not {"breakdown_next_30d", "depot_id", "vehicle_id", "snapshot_date"} & set(art["features"])
    x = pd.read_csv(C.PROCESSED / "features.csv").head(50)
    from alerts import design
    p = art["model"].predict_proba(design(x, art["features"]))[:, 1]
    assert ((p >= 0) & (p <= 1)).all()


def test_model_beats_random_on_time_split():
    res = pd.read_csv(ROOT / "reports" / "risk_model_metrics.csv").set_index("model")
    assert res.loc["XGBoost", "roc_auc"] > 0.65
    assert res.loc["XGBoost", "pr_auc"] > res.loc["Random (prevalence)", "pr_auc"] * 1.5


def test_anomaly_detector_quality():
    res = pd.read_csv(ROOT / "reports" / "anomaly_metrics.csv")
    assert res.f1.max() > 0.8


def test_alerts():
    a = pd.read_csv(C.PROCESSED / "alerts.csv")
    assert len(a) == 58 and a.vehicle_id.is_unique
    assert a.risk_prob.between(0, 1).all() and set(a.risk_tier) <= {"High", "Medium", "Low"}
    assert a.recommended_service.isin(C.SERVICES).all()
    assert (a.risk_prob.is_monotonic_decreasing)
    assert a.top_reasons.str.len().gt(0).all()


@pytest.mark.parametrize("q", ["Is hafte kaun si gaariyan risk mein hain?", "fuel cost per km depot ke hisaab se",
                               "fuel chori anomaly", "maintenance kharcha", "driver ranking", "hello"])
def test_assistant_offline_answers(q, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text, _ = agent.answer(q)
    assert isinstance(text, str) and len(text) > 20 and "Traceback" not in text


def test_assistant_vehicle_lookup_and_unknown(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reg = pd.read_csv(C.PROCESSED / "alerts.csv").registration.iloc[0]
    assert reg in agent.answer(f"{reg} ka haal")[0]
    assert "not found" in agent.answer("ZZZ-99-0000")[0]


def test_every_tool_runs_and_returns_json():
    import json
    for name, args in [("fleet_overview", {}), ("high_risk_vehicles", {"min_tier": "High", "limit": 3}),
                       ("fuel_summary", {"group_by": "model"}), ("fuel_anomalies", {}), ("maintenance_costs", {"group_by": "kind"}),
                       ("driver_ranking", {"limit": 3}), ("vehicle_report", {"registration": "nope"})]:
        assert isinstance(json.loads(agent.run_tool(name, args)), (dict, list))
    assert "error" in json.loads(agent.run_tool("fuel_summary", {"bogus": 1}))  # bad args are reported, not raised


def test_weekly_fuel_question_is_understood(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    text, _ = agent.answer("is haftay ka transportation fuel ka kharcha kia hoga")
    assert "Pichle 7 din" in text and "total fuel kharcha" in text
    expected = query("SELECT SUM(fuel_cost_pkr) c FROM trips WHERE trip_date > ?", (agent._recent(7),)).c[0]
    assert f"{expected:,.0f}" in text
