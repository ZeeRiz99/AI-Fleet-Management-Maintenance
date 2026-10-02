"""Score every vehicle today, explain the score with SHAP, and attach a Rs cost impact.

net saving = P(breakdown in 30d) x (typical breakdown cost + downtime x daily cost) x SERVICE_RISK_REDUCTION
             - cost of the most overdue critical service
The risk reduction, downtime cost and tiers are assumptions in config.py, not measured values.
Run:  python src/alerts.py
"""
import joblib
import numpy as np
import pandas as pd
import shap

import config as C
from db import query
from features import CRITICAL, build_features, slug

NICE = {
    "age_years": "vehicle age (yrs)", "service_debt": "overdue-service load",
    "km_since_brake_inspection": "km since brake service", "km_since_transmission_service": "km since transmission service",
    "km_since_engine_tune_up": "km since engine tune-up", "km_since_coolant_flush": "km since coolant flush",
    "km_since_oil_change": "km since oil change", "kmpl_change_vs_prev": "fuel efficiency change",
    "kmpl_ratio_rated_30d": "fuel efficiency vs rated", "days_since_breakdown": "days since last breakdown",
    "odometer_km": "odometer (km)", "km_30d": "km driven (30d)", "harsh_per_100km_30d": "harsh braking /100km",
}


def nice(f):
    return NICE.get(f, f.replace("_", " "))


def load_model():
    art = joblib.load(C.ROOT / "models" / "risk_model.joblib")
    return art["model"], art["features"], art["threshold"]


def design(df, feats):
    x = pd.get_dummies(df, columns=["vehicle_type"], dtype=int)
    for c in feats:
        if c not in x:
            x[c] = 0
    return x[feats]


def breakdown_loss_by_type():
    """Typical breakdown loss per vehicle type from history (cost + downtime), in today's rupees."""
    m = query("""SELECT v.vehicle_type, m.cost_pkr, m.downtime_days, m.maintenance_date FROM maintenance m
                 JOIN vehicles v ON v.id = m.vehicle_id WHERE m.kind = 'Breakdown'""")
    m = m[pd.to_datetime(m.maintenance_date) >= pd.Timestamp(C.AS_OF_DATE) - pd.Timedelta(days=365)]
    g = m.groupby("vehicle_type").agg(cost=("cost_pkr", "mean"), downtime=("downtime_days", "mean"))
    return (g.cost + g.downtime * C.DOWNTIME_COST_PER_DAY_PKR).to_dict()


def score_today():
    model, feats, thr = load_model()
    cur = build_features(as_of=C.AS_OF_DATE)
    x = design(cur, feats)
    cur["risk_prob"] = model.predict_proba(x)[:, 1]
    sv = shap.TreeExplainer(model).shap_values(x)

    veh = query("SELECT v.id vehicle_id, v.registration, v.make_model, v.status, d.city FROM vehicles v JOIN depots d ON d.id = v.depot_id")
    cur = cur.merge(veh, on="vehicle_id")
    loss = breakdown_loss_by_type()
    years = (pd.Timestamp(C.AS_OF_DATE) - pd.Timestamp(C.START_DATE)).days / 365
    infl = (1 + C.COST_INFLATION_PER_YEAR) ** years

    rows = []
    for i, r in cur.reset_index(drop=True).iterrows():
        contrib = pd.Series(sv[i], index=feats)
        top = contrib.nlargest(3)
        reasons = "; ".join(f"{nice(f)} = {x.iloc[i][f]:,.1f}" for f, c in top.items() if c > 0)
        ratios = {s: r[f"ratio_{slug(s)}"] for s in CRITICAL if pd.notna(r[f"ratio_{slug(s)}"])}
        svc = max(ratios, key=ratios.get) if ratios else "Oil Change"
        mult = C.COST_TYPE_MULT[r.vehicle_type]
        svc_cost = C.SERVICES[svc][2] * mult * infl
        exp_loss = r.risk_prob * loss[r.vehicle_type]
        net = exp_loss * C.SERVICE_RISK_REDUCTION - svc_cost
        tier = "High" if r.risk_prob >= C.RISK_HIGH else "Medium" if r.risk_prob >= C.RISK_MEDIUM else "Low"
        rows.append({"vehicle_id": r.vehicle_id, "registration": r.registration, "make_model": r.make_model,
                     "city": r.city, "as_of": C.AS_OF_DATE, "risk_prob": round(r.risk_prob, 3), "risk_tier": tier,
                     "top_reasons": reasons, "recommended_service": svc,
                     "service_overdue_pct": round(max(0, ratios.get(svc, 0) - 1) * 100),
                     "service_cost_pkr": round(svc_cost, -2), "expected_loss_pkr": round(exp_loss, -2),
                     "net_saving_pkr": round(net, -2)})
    return pd.DataFrame(rows).sort_values("risk_prob", ascending=False)


if __name__ == "__main__":
    a = score_today()
    a.to_csv(C.PROCESSED / "alerts.csv", index=False)
    print(a.risk_tier.value_counts().to_dict())
    print(a.head(8)[["registration", "make_model", "risk_prob", "risk_tier", "recommended_service", "net_saving_pkr"]].to_string(index=False))
    print("\nTop alert reasons:", a.iloc[0].top_reasons)
    print(f"Total net saving if High/Medium alerts are serviced now: Rs {a[a.risk_tier != 'Low'].net_saving_pkr.clip(lower=0).sum():,.0f}")
