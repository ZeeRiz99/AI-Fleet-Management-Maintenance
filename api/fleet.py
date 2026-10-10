"""Read models and AI computations served by the API.

Nothing is re-invented here: breakdown risk, SHAP contributions and the Rs impact come from
src/alerts.score(); fuel anomalies from src/anomaly.py's output and saved rule; service intervals
and costs from src/config.py. This module only shapes those results for clients and adds the
transparent, documented derived scores (vehicle health, driver safety/performance).
"""
import logging
import math
import re
import shutil
import sqlite3
import threading
from datetime import datetime

import numpy as np
import pandas as pd

import alerts as risk_model
import config as C
from db import query

from . import settings as S

log = logging.getLogger("fleet.api")

SIM_TODAY = pd.Timestamp(C.END_DATE)        # last simulated day; services recorded via the API are dated here
AS_OF = pd.Timestamp(C.AS_OF_DATE)          # scoring date (day after the data ends)
BREAKDOWN_RESETS = {name: svc for name, (_, svc) in C.BREAKDOWNS.items()}
INT_FIELDS = ("interval_km", "interval_days", "last_done_odometer_km", "since_last_km", "since_last_days",
              "due_in_km", "due_in_days", "overdue_pct")
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
HEALTH_FORMULA = "Health = 100 x (1 - 30-day breakdown risk) - 5 per overdue critical service, limited to 0-100."
SAFETY_FORMULA = "Safety = 100 - 35 x harsh-braking events per 100 km, limited to 0-100."
PERFORMANCE_FORMULA = ("Performance = 50 x distance vs the median driver (capped at 1) + "
                       "50 x fuel efficiency vs the vehicle's rated km/l (0 at 70%, full at 100%).")


# ----------------------------------------------------------------------------- small helpers
def py(x):
    """numpy/pandas scalar -> plain Python; NaN/inf -> None."""
    if x is None or x is pd.NaT:
        return None
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def rnd(x, digits=0):
    x = py(x)
    if x is None:
        return None
    return int(round(x)) if digits == 0 else round(float(x), digits)


def pct(p):
    return f"{p * 100:.0f}%"


def health_band(h):
    return "Good" if h >= 70 else "Watch" if h >= 40 else "Critical"


def describe(feature, value):
    """Human-readable value for a model feature (used in AI explanations)."""
    v = py(value)
    if v is None:
        return "no record yet"
    if feature.startswith("km_since_") or feature in ("odometer_km", "km_7d", "km_30d"):
        return f"{v:,.0f} km"
    if feature == "age_years":
        return f"{v:.0f} years"
    if feature.startswith("ratio_"):
        return f"{v * 100:.0f}% of its service interval"
    if feature == "service_debt":
        return f"{v:.2f} (0 = nothing overdue)"
    if feature == "kmpl_ratio_rated_30d":
        return f"{v * 100:.0f}% of rated efficiency"
    if feature == "kmpl_change_vs_prev":
        return f"{v * 100:+.0f}% vs the previous 90 days"
    if feature.startswith("days_since"):
        return f"{v:,.0f} days"
    if feature == "harsh_per_100km_30d":
        return f"{v:.2f} per 100 km"
    if feature.startswith("vehicle_type_"):
        return "yes" if v else "no"
    if feature == "is_petrol":
        return "petrol" if v else "diesel"
    if feature in ("trips_30d", "breakdowns_180d", "preventive_90d"):
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def prepare_runtime(fresh=False):
    """Create/refresh the API's working copy of the database and point every src/ module at it."""
    S.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if fresh or not S.RUNTIME_DB.exists():
        shutil.copy2(S.SOURCE_DB, S.RUNTIME_DB)
    C.DB_PATH = S.RUNTIME_DB  # src/db.query reads C.DB_PATH on every call


# ----------------------------------------------------------------------------- service
class FleetService:
    """In-memory view of the runtime database plus model outputs; rebuilt after every write."""

    def __init__(self):
        self.lock = threading.RLock()
        self.reload()

    # ---------------------------------------------------------------- loading & scoring
    def reload(self):
        with self.lock:
            v = query("SELECT v.*, d.city AS depot FROM vehicles v JOIN depots d ON d.id = v.depot_id")
            self.vehicles = v.set_index("id", drop=False).rename_axis(None)
            dr = query("SELECT dr.*, d.city AS depot FROM drivers dr JOIN depots d ON d.id = dr.depot_id")
            self.drivers = dr.set_index("id", drop=False).rename_axis(None)

            t = query("SELECT * FROM trips")
            t["date"] = pd.to_datetime(t.trip_date)
            t["month"] = t.trip_date.str[:7]
            t["kmpl"] = t.distance_km / t.fuel_litres
            for col in ("registration", "depot", "make_model", "fuel_type", "km_per_l"):
                t[col] = t.vehicle_id.map(self.vehicles[col])
            t["driver"] = t.driver_id.map(self.drivers["name"])
            self.trips = t.sort_values(["date", "id"])

            an = pd.read_csv(C.PROCESSED / "fuel_anomalies.csv")
            self.anomalies = an[an.flagged == 1].set_index("id", drop=False).rename_axis(None)
            rule = pd.read_json(C.ROOT / "reports" / "anomaly_rule.json", typ="series")
            self.anomaly_threshold, self.anomaly_window = float(rule["threshold"]), int(rule["window"])

            self.odometer = self.trips.groupby("vehicle_id").odometer_end_km.max()
            recent = self.trips[self.trips.date > SIM_TODAY - pd.Timedelta(days=90)]
            self.km_per_day = (recent.groupby("vehicle_id").distance_km.sum() / 90).reindex(self.vehicles.index).fillna(0.0)
            self._load_reports()
            self._load_maintenance()
            self.rescore()

    def _load_maintenance(self):
        m = query("SELECT * FROM maintenance ORDER BY maintenance_date, id")
        m["date"] = pd.to_datetime(m.maintenance_date)
        m["registration"] = m.vehicle_id.map(self.vehicles["registration"])
        self.maintenance = m

    def _load_reports(self):
        rep = C.ROOT / "reports"
        self.risk_metrics = pd.read_csv(rep / "risk_model_metrics.csv")
        self.anomaly_metrics = pd.read_csv(rep / "anomaly_metrics.csv")
        self.shap_importance = pd.read_csv(rep / "shap_importance.csv", index_col=0).mean_abs_shap

    def rescore(self):
        """Run the real XGBoost model + SHAP for every vehicle and derive schedule/health from the results."""
        with self.lock:
            scoring = risk_model.score(as_of=C.AS_OF_DATE)
            self.scores = scoring.alerts.set_index("vehicle_id", drop=False).rename_axis(None)
            self.factors = {}
            for i, row in scoring.features.iterrows():
                contrib = pd.Series(scoring.shap_values[i], index=scoring.feature_names)
                values = scoring.x.iloc[i]
                top = contrib.reindex(contrib.abs().sort_values(ascending=False).index).head(6)
                self.factors[int(row.vehicle_id)] = [
                    {"feature": f, "label": re.sub(r"\s*\(.*?\)", "", risk_model.nice(f)), "value": py(values[f]), "display": describe(f, values[f]),
                     "impact": round(float(c), 3), "direction": "raises risk" if c > 0 else "lowers risk"}
                    for f, c in top.items()]
            self.schedule = self._compute_schedule()
            self.health = self._compute_health()
            self.scored_at = datetime.now().isoformat(timespec="seconds")

    def _compute_schedule(self):
        """Every service type for every vehicle: km/days since it was last done, due point and status."""
        m = self.maintenance
        done = m[["vehicle_id", "maintenance_type", "maintenance_date", "odometer_km"]].rename(columns={"maintenance_type": "service"})
        resets = m[m.kind == "Breakdown"].assign(service=lambda d: d.maintenance_type.map(BREAKDOWN_RESETS)).dropna(subset=["service"])
        events = pd.concat([done, resets[["vehicle_id", "service", "maintenance_date", "odometer_km"]]], ignore_index=True)
        last = events.groupby(["vehicle_id", "service"]).agg(last_date=("maintenance_date", "max"), last_odo=("odometer_km", "max"))
        inflation = (1 + C.COST_INFLATION_PER_YEAR) ** ((AS_OF - pd.Timestamp(C.START_DATE)).days / 365)

        rows = []
        for v in self.vehicles.itertuples():
            odo = float(self.odometer.get(v.id, v.odometer_start_km))
            km_day = float(self.km_per_day.get(v.id, 0.0))
            for service, (interval_km, interval_days, base_cost, critical) in C.SERVICES.items():
                rec = last.loc[(v.id, service)] if (v.id, service) in last.index else None
                ratio = due_km = due_days = since_km = since_days = None
                if rec is not None and interval_km:
                    since_km = odo - float(rec.last_odo)
                    ratio, due_km = since_km / interval_km, interval_km - since_km
                    due_days = due_km / km_day if km_day > 0 else None
                elif rec is not None:
                    since_days = (SIM_TODAY - pd.Timestamp(rec.last_date)).days
                    ratio, due_days = since_days / interval_days, interval_days - since_days
                status = "unknown" if ratio is None else "overdue" if ratio >= 1 else "due_soon" if ratio >= 0.9 else "ok"
                rows.append({
                    "vehicle_id": int(v.id), "registration": v.registration, "depot": v.depot, "service": service,
                    "critical": bool(critical), "interval_km": interval_km, "interval_days": interval_days,
                    "last_done_date": None if rec is None else rec.last_date,
                    "last_done_odometer_km": None if rec is None else rnd(rec.last_odo),
                    "since_last_km": rnd(since_km), "since_last_days": rnd(since_days),
                    "ratio": None if ratio is None else round(ratio, 3), "status": status,
                    "due_in_km": rnd(due_km), "due_in_days": rnd(due_days),
                    "due_date": None if due_days is None else (SIM_TODAY + pd.Timedelta(days=round(due_days))).strftime("%Y-%m-%d"),
                    "overdue_pct": None if ratio is None else rnd(max(0.0, ratio - 1) * 100),
                    "estimated_cost": float(round(base_cost * C.COST_TYPE_MULT[v.vehicle_type] * inflation, -2)),
                })
        return pd.DataFrame(rows)

    def _compute_health(self):
        s = self.schedule
        overdue_critical = s[s.critical & (s.status == "overdue")].groupby("vehicle_id").size()
        risk = self.scores.risk_prob
        health = (100 * (1 - risk) - 5 * overdue_critical.reindex(risk.index).fillna(0)).clip(0, 100).round()
        return health.astype(int)

    # ---------------------------------------------------------------- vehicles
    def vehicle_ids(self):
        return set(int(i) for i in self.vehicles.index)

    def next_service(self, vid):
        s = self.schedule[(self.schedule.vehicle_id == vid) & (self.schedule.status != "unknown")]
        if s.empty:
            return None
        r = s.sort_values("ratio", ascending=False).iloc[0]
        return {"service": r.service, "status": r.status, "due_in_km": rnd(r.due_in_km), "due_in_days": rnd(r.due_in_days),
                "overdue_pct": rnd(r.overdue_pct)}

    def vehicle_summary(self, vid):
        v, s = self.vehicles.loc[vid], self.scores.loc[vid]
        h = int(self.health[vid])
        return {
            "id": int(vid), "registration": v.registration, "make_model": v.make_model, "vehicle_type": v.vehicle_type,
            "fuel_type": v.fuel_type, "year": int(v.year), "depot": v.depot, "status": v.status,
            "odometer_km": rnd(self.odometer.get(vid)), "health_score": h, "health_band": health_band(h),
            "risk_probability": round(float(s.risk_prob), 3), "risk_tier": s.risk_tier,
            "next_service": self.next_service(vid),
        }

    def list_vehicles(self, search=None, status=None, vehicle_type=None, depot=None, risk_tier=None, sort="risk"):
        rows = [self.vehicle_summary(int(vid)) for vid in self.vehicles.index]
        if search:
            q = search.strip().lower()
            rows = [r for r in rows if q in r["registration"].lower() or q in r["make_model"].lower()]
        for key, wanted in (("status", status), ("vehicle_type", vehicle_type), ("depot", depot), ("risk_tier", risk_tier)):
            if wanted:
                rows = [r for r in rows if r[key].lower() == wanted.lower()]
        keys = {"risk": lambda r: -r["risk_probability"], "health": lambda r: r["health_score"],
                "registration": lambda r: r["registration"], "odometer": lambda r: -(r["odometer_km"] or 0)}
        return sorted(rows, key=keys.get(sort, keys["risk"]))

    def prediction(self, vid):
        v, s = self.vehicles.loc[vid], self.scores.loc[vid]
        h, factors = int(self.health[vid]), self.factors[vid]
        tier_word = {"High": "high", "Medium": "elevated", "Low": "low"}[s.risk_tier]
        raising = [f for f in factors if f["impact"] > 0][:3]
        lowering = [f for f in factors if f["impact"] < 0][:2]
        text = (f"The model estimates a {pct(s.risk_prob)} chance that {v.registration} breaks down within the next "
                f"30 days ({tier_word} risk). ")
        text += ("Main factors raising the risk: " + "; ".join(f"{f['label']} is {f['display']}" for f in raising) + "."
                 if raising else "No single factor stands out as raising the risk.")
        if lowering:
            text += " Keeping it lower: " + "; ".join(f"{f['label']} is {f['display']}" for f in lowering) + "."
        service, overdue = s.recommended_service, int(s.service_overdue_pct)
        net = float(s.net_saving_pkr)
        if net > 0:
            rec_text = (f"Do the {service} now" + (f" ({overdue}% past its interval)" if overdue else "") +
                        f": expected saving about Rs {net:,.0f} after the service cost.")
        else:
            rec_text = (f"Servicing early costs more than the expected loss at this risk level; keep the normal schedule "
                        f"(most urgent critical service: {service}).")
        return {
            "vehicle_id": int(vid), "registration": v.registration, "risk_probability": round(float(s.risk_prob), 3),
            "risk_tier": s.risk_tier, "health_score": h, "health_band": health_band(h), "health_formula": HEALTH_FORMULA,
            "explanation": text, "factors": factors,
            "recommendation": {"service": service, "overdue_pct": overdue, "service_cost": float(s.service_cost_pkr),
                               "expected_loss": float(s.expected_loss_pkr), "net_saving": net, "text": rec_text},
            "model": "XGBoost breakdown-risk model with SHAP explanations", "as_of": C.AS_OF_DATE, "scored_at": self.scored_at,
        }

    def vehicle_detail(self, vid):
        v = self.vehicles.loc[vid]
        t = self.trips[self.trips.vehicle_id == vid]
        t90 = t[t.date > SIM_TODAY - pd.Timedelta(days=90)]
        km90, l90, c90 = float(t90.distance_km.sum()), float(t90.fuel_litres.sum()), float(t90.fuel_cost_pkr.sum())
        months = sorted(t.month.unique())[-12:]
        eff = t[t.month.isin(months)].groupby("month").agg(km=("distance_km", "sum"), litres=("fuel_litres", "sum"))
        m = self.maintenance[self.maintenance.vehicle_id == vid]
        sched = self.schedule[self.schedule.vehicle_id == vid].sort_values("ratio", ascending=False, na_position="last")
        return {
            **self.vehicle_summary(vid),
            "rated_km_per_l": round(float(v.km_per_l), 2),
            "prediction": self.prediction(vid),
            "fuel": {"trips_90d": len(t90), "km_90d": rnd(km90), "litres_90d": rnd(l90), "cost_90d": rnd(c90),
                     "km_per_l_90d": rnd(km90 / l90, 2) if l90 else None, "cost_per_km_90d": rnd(c90 / km90, 1) if km90 else None,
                     "monthly_km_per_l": [{"month": mo, "km_per_l": round(r.km / r.litres, 2)} for mo, r in eff.iterrows()]},
            "maintenance": {"total_cost": rnd(m.cost_pkr.sum()), "preventive_cost": rnd(m[m.kind == "Preventive"].cost_pkr.sum()),
                            "breakdown_cost": rnd(m[m.kind == "Breakdown"].cost_pkr.sum()),
                            "breakdowns": int((m.kind == "Breakdown").sum()), "services": int((m.kind == "Preventive").sum()),
                            "history": [self._maintenance_record(r) for r in m.sort_values(["date", "id"], ascending=False).head(15).itertuples()]},
            "upcoming_services": [self._schedule_item(r) for r in sched.itertuples()],
            "recent_trips": [self._trip(r) for r in t.sort_values(["date", "id"], ascending=False).head(8).itertuples()],
        }

    # ---------------------------------------------------------------- maintenance
    @staticmethod
    def _maintenance_record(r):
        return {"id": int(r.id), "vehicle_id": int(r.vehicle_id), "registration": r.registration, "date": r.maintenance_date,
                "service": r.maintenance_type, "kind": r.kind, "odometer_km": rnd(r.odometer_km), "cost": rnd(r.cost_pkr),
                "downtime_days": int(r.downtime_days), "notes": r.notes if isinstance(r.notes, str) else None,
                "status": "Completed"}

    @staticmethod
    def _schedule_item(r):
        item = {k: py(getattr(r, k)) for k in (
            "vehicle_id", "registration", "depot", "service", "critical", "interval_km", "interval_days", "last_done_date",
            "last_done_odometer_km", "since_last_km", "since_last_days", "status", "due_in_km", "due_in_days", "due_date",
            "overdue_pct", "estimated_cost")}
        for k in INT_FIELDS:  # pandas stores these as float when some rows are empty
            item[k] = rnd(item[k])
        return item

    def maintenance_schedule(self, status=None, vehicle_id=None, critical_only=False, limit=200):
        s = self.schedule
        if status:
            s = s[s.status == status]
        if vehicle_id is not None:
            s = s[s.vehicle_id == vehicle_id]
        if critical_only:
            s = s[s.critical]
        s = s.sort_values(["ratio"], ascending=False, na_position="last") if status != "due_soon" else s.sort_values("due_in_days")
        return [self._schedule_item(r) for r in s.head(limit).itertuples()]

    def maintenance_history(self, vehicle_id=None, kind=None, limit=50, offset=0):
        m = self.maintenance
        if vehicle_id is not None:
            m = m[m.vehicle_id == vehicle_id]
        if kind:
            m = m[m.kind.str.lower() == kind.lower()]
        m = m.sort_values(["date", "id"], ascending=False)
        return {"total": len(m), "items": [self._maintenance_record(r) for r in m.iloc[offset:offset + limit].itertuples()]}

    def maintenance_summary(self):
        s, m = self.schedule, self.maintenance
        m30 = m[m.date > SIM_TODAY - pd.Timedelta(days=30)]
        m365 = m[m.date > SIM_TODAY - pd.Timedelta(days=365)]
        return {
            "overdue": int((s.status == "overdue").sum()), "due_soon": int((s.status == "due_soon").sum()),
            "vehicles_with_overdue": int(s[s.status == "overdue"].vehicle_id.nunique()),
            "completed_30d": len(m30), "spend_30d": rnd(m30.cost_pkr.sum()), "spend_365d": rnd(m365.cost_pkr.sum()),
            "breakdowns_365d": int((m365.kind == "Breakdown").sum()),
            "breakdown_share": round(float(m[m.kind == "Breakdown"].cost_pkr.sum() / m.cost_pkr.sum()), 3),
        }

    def record_service(self, vid, service, cost=None, notes=None, username="api"):
        """Record a completed preventive service, then re-run the model so the risk reflects it."""
        with self.lock:
            before = self.prediction(vid)
            row = self.schedule[(self.schedule.vehicle_id == vid) & (self.schedule.service == service)].iloc[0]
            cost = float(row.estimated_cost if cost is None else cost)
            odo = float(self.odometer[vid])
            note = (notes or f"Recorded from the mobile app by {username}").strip()[:200]
            with sqlite3.connect(C.DB_PATH) as con:
                new_id = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM maintenance").fetchone()[0]
                con.execute("INSERT INTO maintenance (id, vehicle_id, maintenance_date, maintenance_type, kind, odometer_km, "
                            "cost_pkr, downtime_days, notes) VALUES (?, ?, ?, ?, 'Preventive', ?, ?, 0, ?)",
                            (new_id, vid, C.END_DATE, service, round(odo), round(cost, -1), note))
            self._load_maintenance()
            self.rescore()
            record = self.maintenance[self.maintenance.id == new_id].iloc[0]
            return {"record": self._maintenance_record(record), "before": before, "after": self.prediction(vid)}

    # ---------------------------------------------------------------- trips
    @staticmethod
    def _trip(r):
        start, end = r.start_time, r.end_time
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        duration = (eh * 60 + em) - (sh * 60 + sm)
        if duration < 0:
            duration += 24 * 60
        return {"id": int(r.id), "date": r.trip_date, "start_time": start, "end_time": end, "duration_min": duration,
                "status": "Completed", "vehicle_id": int(r.vehicle_id), "registration": r.registration,
                "driver_id": int(r.driver_id), "driver": r.driver, "route": r.route, "distance_km": rnd(r.distance_km),
                "fuel_litres": rnd(r.fuel_litres, 1), "fuel_cost": rnd(r.fuel_cost_pkr),
                "harsh_braking_events": int(r.harsh_braking_events)}

    def list_trips(self, vehicle_id=None, driver_id=None, limit=30, offset=0):
        t = self.trips
        if vehicle_id is not None:
            t = t[t.vehicle_id == vehicle_id]
        if driver_id is not None:
            t = t[t.driver_id == driver_id]
        t = t.sort_values(["date", "id"], ascending=False)
        items = [self._trip(r) for r in t.iloc[offset:offset + limit].itertuples()]
        for item in items:
            item["fuel_anomaly"] = item["id"] in self.anomalies.index
        return {"total": len(t), "active": 0,
                "note": "Trips are historical (2023-2025); live trip tracking/GPS is a future feature.", "items": items}

    # ---------------------------------------------------------------- fuel
    def _fuel_groups(self, w, col, name_col=None):
        g = w.groupby(col).agg(km=("distance_km", "sum"), litres=("fuel_litres", "sum"),
                               cost=("fuel_cost_pkr", "sum"), trips=("id", "count")).reset_index()
        out = []
        for r in g.sort_values("cost", ascending=False).itertuples():
            item = {"name": str(getattr(r, col)), "km": rnd(r.km), "litres": rnd(r.litres), "cost": rnd(r.cost), "trips": int(r.trips),
                    "cost_per_km": rnd(r.cost / r.km, 1), "km_per_litre": rnd(r.km / r.litres, 2)}
            if name_col:
                item["vehicle_id"] = int(self.vehicles.index[self.vehicles[name_col] == getattr(r, col)][0])
            out.append(item)
        return out

    def fuel_summary(self, days=30):
        w = self.trips[self.trips.date > SIM_TODAY - pd.Timedelta(days=days)]
        km, litres, cost = float(w.distance_km.sum()), float(w.fuel_litres.sum()), float(w.fuel_cost_pkr.sum())
        a = self.anomalies[pd.to_datetime(self.anomalies.trip_date) > SIM_TODAY - pd.Timedelta(days=days)]
        months = sorted(self.trips.month.unique())[-24:]
        mon = self.trips[self.trips.month.isin(months)].groupby("month").agg(
            km=("distance_km", "sum"), litres=("fuel_litres", "sum"), cost=("fuel_cost_pkr", "sum"))
        price = self.trips[self.trips.month.isin(months)].pivot_table(
            index="month", columns="fuel_type", values="fuel_price_per_litre", aggfunc="mean")
        return {
            "days": days, "period_end": C.END_DATE,
            "totals": {"trips": len(w), "km": rnd(km), "litres": rnd(litres), "cost": rnd(cost),
                       "cost_per_km": rnd(cost / km, 1) if km else None, "km_per_litre": rnd(km / litres, 2) if litres else None,
                       "litres_per_100km": rnd(litres / km * 100, 1) if km else None,
                       "anomalies": len(a), "anomaly_excess_cost": rnd(a.excess_cost_pkr.sum())},
            "by_vehicle": self._fuel_groups(w, "registration", name_col="registration"),
            "by_depot": self._fuel_groups(w, "depot"), "by_model": self._fuel_groups(w, "make_model"),
            "monthly": [{"month": mo, "km": rnd(r.km), "litres": rnd(r.litres), "cost": rnd(r.cost),
                         "cost_per_km": rnd(r.cost / r.km, 2), "km_per_litre": rnd(r.km / r.litres, 2)} for mo, r in mon.iterrows()],
            "price_monthly": [{"month": mo, "petrol": rnd(r.get("Petrol"), 1), "diesel": rnd(r.get("Diesel"), 1)}
                              for mo, r in price.iterrows()],
        }

    def _anomaly_item(self, r):
        actual = r.distance_km / r.fuel_litres
        extra_pct = (1 / r.ratio - 1) * 100 if r.ratio else 0
        return {
            "trip_id": int(r.id), "date": r.trip_date, "vehicle_id": int(r.vehicle_id),
            "registration": self.vehicles.registration.get(r.vehicle_id), "driver": self.drivers.name.get(r.driver_id),
            "route": r.route, "distance_km": rnd(r.distance_km), "fuel_litres": rnd(r.fuel_litres, 1),
            "expected_litres": rnd(r.distance_km / r.baseline_kmpl, 1), "baseline_km_per_l": rnd(r.baseline_kmpl, 2),
            "actual_km_per_l": rnd(actual, 2), "ratio": rnd(r.ratio, 2), "excess_litres": rnd(r.excess_litres, 1),
            "excess_cost": rnd(r.excess_cost_pkr),
            "explanation": (f"Used {r.fuel_litres:.1f} L for {r.distance_km:.0f} km ({actual:.2f} km/l). This vehicle "
                            f"normally does {r.baseline_kmpl:.2f} km/l (median of its previous {self.anomaly_window} trips), "
                            f"so it burned about {extra_pct:.0f}% more fuel than expected. Trips below "
                            f"{self.anomaly_threshold * 100:.0f}% of the vehicle's normal efficiency are flagged as a "
                            f"possible leak, theft or meter error."),
        }

    def fuel_anomalies(self, days=90, vehicle_id=None, limit=50):
        a = self.anomalies[pd.to_datetime(self.anomalies.trip_date) > SIM_TODAY - pd.Timedelta(days=days)]
        if vehicle_id is not None:
            a = a[a.vehicle_id == vehicle_id]
        a = a.sort_values(["trip_date", "id"], ascending=False)
        return {"days": days, "count": len(a), "excess_litres": rnd(a.excess_litres.sum()), "excess_cost": rnd(a.excess_cost_pkr.sum()),
                "vehicles_affected": int(a.vehicle_id.nunique()), "threshold": self.anomaly_threshold,
                "method": f"Trip km/l compared with the vehicle's median km/l over its previous {self.anomaly_window} trips; "
                          f"flagged below {self.anomaly_threshold:.2f} x baseline (F1 0.99 on the 2025 test set).",
                "items": [self._anomaly_item(r) for r in a.head(limit).itertuples()]}

    def fuel_check(self, vid, distance_km, fuel_litres):
        """Live anomaly test for a new fuel entry, using the same rule as the batch detector."""
        hist = self.trips[self.trips.vehicle_id == vid].tail(self.anomaly_window)
        baseline = float(hist.kmpl.median())
        actual = distance_km / fuel_litres
        ratio = actual / baseline
        abnormal = ratio < self.anomaly_threshold
        expected = distance_km / baseline
        excess = max(0.0, fuel_litres - expected)
        price = C.FUEL_PRICE_NOW[self.vehicles.loc[vid].fuel_type]
        if abnormal:
            text = (f"{actual:.2f} km/l is only {ratio * 100:.0f}% of this vehicle's normal {baseline:.2f} km/l. "
                    f"About {excess:.1f} L (Rs {excess * price:,.0f}) more than expected - check for a leak, theft or a wrong meter reading.")
        else:
            text = (f"{actual:.2f} km/l is {ratio * 100:.0f}% of this vehicle's usual {baseline:.2f} km/l "
                    f"(flagged only below {self.anomaly_threshold * 100:.0f}%).")
        return {"vehicle_id": int(vid), "registration": self.vehicles.loc[vid].registration, "abnormal": bool(abnormal),
                "verdict": "Abnormal" if abnormal else "Normal", "ratio": round(ratio, 3), "threshold": self.anomaly_threshold,
                "baseline_km_per_l": round(baseline, 2), "actual_km_per_l": round(actual, 2),
                "expected_litres": round(expected, 1), "excess_litres": round(excess, 1), "excess_cost": round(excess * price),
                "explanation": text}

    # ---------------------------------------------------------------- drivers
    def driver_table(self, days=180):
        w = self.trips[self.trips.date > SIM_TODAY - pd.Timedelta(days=days)].copy()
        w["eff"] = w.kmpl / w.km_per_l
        g = w.groupby("driver_id").agg(trips=("id", "count"), km=("distance_km", "sum"), harsh=("harsh_braking_events", "sum"),
                                       litres=("fuel_litres", "sum"), eff=("eff", "median"))
        top_vehicle = w.groupby(["driver_id", "vehicle_id"]).distance_km.sum().reset_index().sort_values(
            "distance_km", ascending=False).drop_duplicates("driver_id").set_index("driver_id").vehicle_id
        d = self.drivers.join(g, how="left").fillna({"trips": 0, "km": 0, "harsh": 0, "litres": 0})
        d["h100"] = (d.harsh / d.km.where(d.km > 0) * 100).fillna(0)
        median_km = float(d.km[d.km > 0].median()) if (d.km > 0).any() else 1.0
        d["safety"] = (100 - 35 * d.h100).clip(0, 100).round()
        d["performance"] = (50 * (d.km / median_km).clip(upper=1) + 50 * ((d.eff.fillna(0.7) - 0.7) / 0.3).clip(0, 1)).round()
        d["top_vehicle"] = top_vehicle.reindex(d.index)
        return d

    def _driver_summary(self, r):
        vid = py(r.top_vehicle)
        return {"id": int(r.id), "name": r.name, "license_number": r.license_number, "depot": r.depot,
                "experience_years": int(r.experience_years), "trips": int(r.trips), "distance_km": rnd(r.km),
                "harsh_per_100km": rnd(r.h100, 2), "safety_score": int(r.safety), "performance_score": int(r.performance),
                "most_used_vehicle": None if vid is None else self.vehicles.loc[int(vid)].registration,
                "most_used_vehicle_id": None if vid is None else int(vid)}

    def list_drivers(self, days=180, sort="safety"):
        d = self.driver_table(days)
        d = d.sort_values({"safety": "safety", "performance": "performance", "name": "name"}.get(sort, "safety"),
                          ascending=(sort == "name"))
        return {"days": days, "safety_formula": SAFETY_FORMULA, "performance_formula": PERFORMANCE_FORMULA,
                "items": [self._driver_summary(r) for r in d.itertuples()]}

    def driver_detail(self, did, days=180):
        d = self.driver_table(days)
        summary = self._driver_summary(next(d.loc[[did]].itertuples()))
        trips = self.list_trips(driver_id=did, limit=10)["items"]
        return {**summary, "days": days, "safety_formula": SAFETY_FORMULA, "performance_formula": PERFORMANCE_FORMULA,
                "recent_trips": trips}

    # ---------------------------------------------------------------- alerts
    def alerts(self, read_ids=frozenset()):
        out = []

        def add(aid, category, severity, title, message, vid=None, date=None):
            out.append({"id": aid, "category": category, "severity": severity, "title": title, "message": message,
                        "vehicle_id": None if vid is None else int(vid),
                        "registration": None if vid is None else self.vehicles.registration.get(vid),
                        "date": date or C.AS_OF_DATE, "read": aid in read_ids})

        for vid, s in self.scores.iterrows():
            h = int(self.health[vid])
            reg = self.vehicles.loc[vid].registration
            if s.risk_tier == "High":
                add(f"high_risk:{vid}", "high_risk", "critical", f"High breakdown risk - {reg}",
                    f"{pct(s.risk_prob)} chance of a breakdown in the next 30 days. Recommended: {s.recommended_service}.", vid)
            elif h < 40 or s.risk_tier == "Medium":
                add(f"health:{vid}", "health_warning", "warning", f"Vehicle health warning - {reg}",
                    f"Health score {h}/100 ({pct(s.risk_prob)} breakdown risk). Plan a check-up.", vid)

        sched = self.schedule
        overdue = sched[sched.status == "overdue"]
        counts = overdue.groupby("vehicle_id").size()
        for r in overdue.sort_values("ratio", ascending=False).drop_duplicates("vehicle_id").itertuples():
            more = int(counts[r.vehicle_id]) - 1
            add(f"overdue:{r.vehicle_id}:{r.service}", "maintenance_overdue",
                "critical" if r.critical and r.overdue_pct >= 50 else "warning", f"Maintenance overdue - {r.registration}",
                f"{r.service} is {r.overdue_pct}% past its interval" + (f" (+{more} more overdue)" if more else "") + ".", r.vehicle_id)
        for r in sched[sched.status == "due_soon"].sort_values("due_in_days").itertuples():
            when = f"in about {r.due_in_km:,.0f} km" if pd.notna(r.due_in_km) else f"in {r.due_in_days:.0f} days"
            add(f"due:{r.vehicle_id}:{r.service}", "maintenance_due", "info", f"Maintenance due - {r.registration}",
                f"{r.service} is due {when}.", r.vehicle_id)

        recent = self.anomalies[pd.to_datetime(self.anomalies.trip_date) > SIM_TODAY - pd.Timedelta(days=30)]
        for r in recent.itertuples():
            add(f"fuel:{r.id}", "fuel_anomaly", "warning", f"Abnormal fuel use - {self.vehicles.registration.get(r.vehicle_id)}",
                f"{r.excess_litres:.0f} L more than expected on {r.route} (about Rs {r.excess_cost_pkr:,.0f}).", r.vehicle_id, r.trip_date)

        for v in self.vehicles[self.vehicles.status == "maintenance"].itertuples():
            add(f"workshop:{v.id}", "operational", "info", f"In workshop - {v.registration}",
                "Vehicle is under breakdown repair and unavailable for trips.", v.id)
        for r in self.driver_table(90).itertuples():
            if r.trips and r.safety < 50:
                add(f"driver:{r.id}", "operational", "warning", f"Driver safety - {r.name}",
                    f"{r.h100:.2f} harsh-braking events per 100 km in the last 90 days (safety score {int(r.safety)}).")

        out.sort(key=lambda a: a["date"], reverse=True)                               # newest first ...
        out.sort(key=lambda a: (a["read"], SEVERITY_ORDER[a["severity"]]))            # ... within unread/severity groups
        return out

    # ---------------------------------------------------------------- dashboard
    def dashboard(self, read_ids=frozenset()):
        v, s = self.vehicles, self.scores
        alerts = self.alerts(read_ids)
        fuel = self.fuel_summary(30)
        health = self.health
        upcoming = self.maintenance_schedule(status="due_soon", limit=5)
        top = [self.vehicle_summary(int(vid)) for vid in s.sort_values("risk_prob", ascending=False).index[:5]]
        return {
            "as_of": C.AS_OF_DATE, "data_start": C.START_DATE, "data_end": C.END_DATE,
            "fleet": {"total_vehicles": len(v), "active": int((v.status == "active").sum()),
                      "in_maintenance": int((v.status == "maintenance").sum()), "critical": int((s.risk_tier == "High").sum()),
                      "drivers": len(self.drivers), "depots": int(v.depot.nunique())},
            "risk": {"high": int((s.risk_tier == "High").sum()), "medium": int((s.risk_tier == "Medium").sum()),
                     "low": int((s.risk_tier == "Low").sum()), "average_probability": round(float(s.risk_prob.mean()), 3),
                     "potential_saving": rnd(s[s.risk_tier != "Low"].net_saving_pkr.clip(lower=0).sum()), "top": top},
            "fuel": {**fuel["totals"], "monthly": fuel["monthly"][-12:]},
            "maintenance": {**self.maintenance_summary(), "upcoming": upcoming},
            "health": {"average": round(float(health.mean()), 1), "good": int((health >= 70).sum()),
                       "watch": int(((health >= 40) & (health < 70)).sum()), "critical": int((health < 40).sum()),
                       "formula": HEALTH_FORMULA},
            "recent_alerts": alerts[:5], "unread_alerts": sum(1 for a in alerts if not a["read"]),
        }

    # ---------------------------------------------------------------- model info
    def model_info(self):
        m = self.risk_metrics.replace({np.nan: None})
        return {
            "risk_model": {"name": "XGBoost breakdown-risk classifier", "target": "breakdown within 30 days",
                           "validation": "time-based split: train before 2024-12-01, test on 2025",
                           "metrics": [{k: py(val) for k, val in row.items()} for row in m.to_dict("records")]},
            "explainability": [{"feature": risk_model.nice(f), "mean_abs_shap": round(float(val), 3)}
                               for f, val in self.shap_importance.head(10).items()],
            "fuel_anomaly": {"rule": f"km/l below {self.anomaly_threshold:.2f} x the vehicle's median of its previous "
                                     f"{self.anomaly_window} trips",
                             "metrics": self.anomaly_metrics.to_dict("records")},
            "health_formula": HEALTH_FORMULA, "safety_formula": SAFETY_FORMULA, "performance_formula": PERFORMANCE_FORMULA,
            "data_note": "The fleet data is simulated (2023-2025); results show the method, not real-fleet accuracy.",
            "scored_at": self.scored_at,
        }
