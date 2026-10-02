"""Fuel anomaly detection (leaks / theft / meter fraud).

Each trip is compared with the vehicle's own recent efficiency (median km/l of its previous
WINDOW trips, so only past data is used). Two detectors are evaluated against the injected
ground truth `is_fuel_anomaly` on a time-based test set (2025):
  * rule: flag when km/l falls below THRESHOLD x the vehicle baseline (threshold tuned on 2023-24)
  * IsolationForest on [efficiency ratio, litres-per-100km z-score vs baseline]
The better F1 detector writes data/processed/fuel_anomalies.csv with excess litres and Rs.
Run:  python src/anomaly.py
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_recall_fscore_support

import config as C
from db import query

WINDOW = 15
TEST_START = "2025-01-01"
REPORT_DIR = C.ROOT / "reports"


def prepare():
    t = query("""SELECT t.*, v.make_model, v.fuel_type, v.depot_id FROM trips t
                 JOIN vehicles v ON v.id = t.vehicle_id ORDER BY t.vehicle_id, t.trip_date, t.id""")
    t["kmpl"] = t.distance_km / t.fuel_litres
    g = t.groupby("vehicle_id").kmpl
    t["baseline_kmpl"] = g.transform(lambda s: s.shift(1).rolling(WINDOW, min_periods=5).median())
    t["ratio"] = t.kmpl / t.baseline_kmpl
    spread = t.groupby("vehicle_id").ratio.transform(lambda s: s.rolling(60, min_periods=20).std().shift(1))
    t["ratio_z"] = (t.ratio - 1) / spread
    return t.dropna(subset=["ratio", "ratio_z"]).reset_index(drop=True)


def prf(y, pred):
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    return round(p, 3), round(r, 3), round(f, 3)


def main():
    t = prepare()
    train, test = t[t.trip_date < TEST_START], t[t.trip_date >= TEST_START]
    y_tr, y_te = train.is_fuel_anomaly, test.is_fuel_anomaly
    print(f"trips: train {len(train)} test {len(test)} | anomaly rate test {y_te.mean():.4f}")

    # rule detector, threshold tuned on train
    grid = np.arange(0.55, 0.95, 0.01)
    thr = max(grid, key=lambda x: prf(y_tr, train.ratio < x)[2])
    rule_pred = test.ratio < thr

    # IsolationForest (unsupervised); contamination set from the expected rate (config-level assumption)
    feats = ["ratio", "ratio_z"]
    iso = IsolationForest(n_estimators=200, contamination=C.FUEL_ANOMALY_RATE, random_state=C.SEED).fit(train[feats])
    iso_pred = iso.predict(test[feats]) == -1

    rows = []
    for name, pred in (("Rule (ratio < %.2f)" % thr, rule_pred), ("IsolationForest", iso_pred)):
        p, r, f = prf(y_te, pred)
        rows.append({"detector": name, "precision": p, "recall": r, "f1": f, "flagged": int(pred.sum())})
    res = pd.DataFrame(rows)
    print(res.to_string(index=False))
    REPORT_DIR.mkdir(exist_ok=True)
    res.to_csv(REPORT_DIR / "anomaly_metrics.csv", index=False)

    # score all trips with the rule (more explainable); excess = litres above the vehicle's own baseline
    t["flagged"] = (t.ratio < thr).astype(int)
    t["expected_litres"] = t.distance_km / t.baseline_kmpl
    t["excess_litres"] = (t.fuel_litres - t.expected_litres).clip(lower=0).where(t.flagged == 1, 0).round(1)
    t["excess_cost_pkr"] = (t.excess_litres * t.fuel_price_per_litre).round(0)
    out = t[["id", "vehicle_id", "driver_id", "trip_date", "route", "distance_km", "fuel_litres", "baseline_kmpl",
             "ratio", "flagged", "excess_litres", "excess_cost_pkr", "is_fuel_anomaly"]]
    out.to_csv(C.PROCESSED / "fuel_anomalies.csv", index=False)
    f = t[t.flagged == 1]
    print(f"\nflagged {len(f)} trips; excess fuel {f.excess_litres.sum():,.0f} L = Rs {f.excess_cost_pkr.sum():,.0f}")
    print("top vehicles by excess cost:\n" + f.groupby("vehicle_id").excess_cost_pkr.sum().nlargest(5).to_string())


if __name__ == "__main__":
    main()
