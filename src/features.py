"""Weekly per-vehicle snapshots for the breakdown-risk model.

Each row = (vehicle, Monday). Features use only data strictly BEFORE the snapshot date;
label = a breakdown occurs in the next HORIZON_DAYS days. Vehicles that are down for a
breakdown repair on the snapshot date are skipped.

Run:  python src/features.py
"""
import numpy as np
import pandas as pd

import config as C
from db import query

HORIZON_DAYS = 30
WARMUP_DAYS = 180  # let service history build up before the first snapshot
SENSORS = ["engine_rpm", "lub_oil_pressure", "fuel_pressure", "coolant_pressure", "lub_oil_temp", "coolant_temp"]
CRITICAL = {s: v[0] for s, v in C.SERVICES.items() if v[3]}  # service -> interval km
slug = lambda s: s.lower().replace(" ", "_").replace("-", "_")


def _day(series):
    return pd.to_datetime(series).values.astype("datetime64[D]").astype(np.int64)


def build_features(as_of=None):
    """Weekly labelled snapshots, or (as_of=date) one unlabelled 'today' snapshot per vehicle."""
    vehicles = query("SELECT * FROM vehicles")
    trips = query("SELECT * FROM trips ORDER BY trip_date, id")
    maint = query("SELECT * FROM maintenance ORDER BY maintenance_date, id")
    sens = query("SELECT * FROM sensor_readings ORDER BY reading_date")
    trips["day"], maint["day"], sens["day"] = _day(trips.trip_date), _day(maint.maintenance_date), _day(sens.reading_date)
    trips["kmpl"] = trips.distance_km / trips.fuel_litres

    start = pd.Timestamp(C.START_DATE) + pd.Timedelta(days=WARMUP_DAYS)
    end = pd.Timestamp(C.END_DATE) - pd.Timedelta(days=HORIZON_DAYS)
    snaps = pd.date_range(start, end, freq="W-MON") if as_of is None else [pd.Timestamp(as_of)]

    rows = []
    for v in vehicles.itertuples():
        t = trips[trips.vehicle_id == v.id]
        m = maint[maint.vehicle_id == v.id]
        s = sens[sens.vehicle_id == v.id]
        td, mk = t.day.values, m.day.values
        bd = m[m.kind == "Breakdown"]
        for snap in snaps:
            d = np.datetime64(snap.date(), "D").astype(np.int64)
            # skip while in the workshop for a breakdown repair
            if as_of is None and ((bd.day.values <= d) & (d <= bd.day.values + bd.downtime_days.values)).any():
                continue
            past_t = t[td < d]
            past_m = m[mk < d]
            if past_t.empty:
                continue
            odo = past_t.odometer_end_km.iloc[-1]
            w30 = past_t[past_t.day >= d - 30]
            w7 = past_t[past_t.day >= d - 7]
            base = past_t[(past_t.day >= d - 120) & (past_t.day < d - 30)]
            r = {"vehicle_id": v.id, "snapshot_date": snap.date(), "age_years": snap.year - v.year,
                 "odometer_km": odo, "km_per_l_rated": v.km_per_l, "is_petrol": int(v.fuel_type == "Petrol"),
                 "vehicle_type": v.vehicle_type, "depot_id": v.depot_id,
                 "km_7d": w7.distance_km.sum(), "km_30d": w30.distance_km.sum(), "trips_30d": len(w30),
                 "harsh_per_100km_30d": w30.harsh_braking_events.sum() / max(w30.distance_km.sum(), 1) * 100}

            # fuel efficiency: robust (median per-trip km/l) vs rated and vs previous 90 days
            k30 = w30.kmpl.median() if len(w30) else np.nan
            kb = base.kmpl.median() if len(base) else np.nan
            r["kmpl_ratio_rated_30d"] = k30 / v.km_per_l
            r["kmpl_change_vs_prev"] = k30 / kb - 1 if kb == kb else np.nan

            # service history
            overdue = []
            for svc, interval in CRITICAL.items():
                done = past_m[past_m.maintenance_type == svc]
                # breakdown repairs also reset the matching service
                bk = past_m[past_m.maintenance_type.map(lambda x: C.BREAKDOWNS.get(x, (0, None))[1] == svc)]
                last = max(done.odometer_km.max() if len(done) else -1, bk.odometer_km.max() if len(bk) else -1)
                if last < 0:
                    r[f"km_since_{slug(svc)}"] = r[f"ratio_{slug(svc)}"] = np.nan
                else:
                    r[f"km_since_{slug(svc)}"] = odo - last
                    r[f"ratio_{slug(svc)}"] = (odo - last) / interval
                    overdue.append(max(0.0, (odo - last) / interval - 1))
            r["service_debt"] = float(np.mean(overdue)) if overdue else np.nan
            r["days_since_service"] = d - past_m[past_m.kind == "Preventive"].day.max() if (past_m.kind == "Preventive").any() else np.nan
            pb = past_m[past_m.kind == "Breakdown"]
            r["breakdowns_180d"] = int((pb.day >= d - 180).sum())
            r["days_since_breakdown"] = d - pb.day.max() if len(pb) else np.nan
            r["preventive_90d"] = int(((past_m.kind == "Preventive") & (past_m.day >= d - 90)).sum())

            # sensors: latest + 4-week mean
            ps = s[s.day < d].tail(4)
            for c in SENSORS:
                r[f"{c}_last"] = ps[c].iloc[-1] if len(ps) else np.nan
                r[f"{c}_mean4w"] = ps[c].mean() if len(ps) else np.nan

            # label
            r["breakdown_next_30d"] = (np.nan if as_of is not None else
                                       int(((bd.day.values >= d) & (bd.day.values < d + HORIZON_DAYS)).any()))
            rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = build_features()
    df.to_csv(C.PROCESSED / "features.csv", index=False)
    print(df.shape)
    print(f"positive rate: {df.breakdown_next_30d.mean():.3f}  ({df.breakdown_next_30d.sum()} positives)")
    print(df.isna().mean().round(2)[lambda x: x > 0].to_string())
