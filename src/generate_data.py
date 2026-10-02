"""Synthetic fleet generator modelled on the mindweave sample (Pakistan units/prices).

Hybrid approach:
  * vehicles / depot sizes / trip-distance and mpg statistics come from the mindweave sample
    in data/raw (converted to km, litres, PKR);
  * trips, fuel, maintenance and breakdowns are simulated over START_DATE..END_DATE;
  * weekly engine-sensor readings are *sampled from the real engine dataset* in
    data/raw/engine, conditioned on how overdue the vehicle's services are.

Breakdown risk is driven by overdue services ("service debt"), vehicle age and driver
harshness, so a model can later learn real structure and SHAP can explain it.
Run:  python src/generate_data.py
"""
import numpy as np
import pandas as pd

import config as C

DRIVER_NAMES = [
    "Muhammad Imran", "Ali Raza", "Usman Ghani", "Bilal Ahmed", "Hamza Tariq", "Kashif Mehmood",
    "Faisal Iqbal", "Shahid Hussain", "Zubair Khan", "Naveed Akhtar", "Asif Javed", "Tahir Mahmood",
    "Rashid Ali", "Waqas Ahmad", "Adnan Siddiqui", "Junaid Malik", "Saeed Anwar", "Irfan Baig",
    "Noman Sheikh", "Rizwan Haider", "Khalid Mehmood", "Sajid Rehman", "Arslan Butt", "Danish Qureshi",
]
SERVICE_NAMES = list(C.SERVICES)
CRITICAL = [s for s, v in C.SERVICES.items() if v[3]]
# Engine dataset label 0 = higher RPM / lower fuel pressure (stressed). Assumed "needs attention";
# the dataset README does not define the labels.
ATTENTION_LABEL = 0


def build_static(rng):
    raw_v = pd.read_csv(C.RAW / "vehicles.csv")
    vehicles = pd.DataFrame({
        "id": raw_v["id"],
        "depot_id": raw_v["depot_id"],
        "vehicle_type": raw_v["vehicle_type"],
        "year": raw_v["year"],
    })
    models = vehicles["vehicle_type"].map(lambda t: C.VEHICLE_MAP[t])
    vehicles["make_model"] = models.map(lambda m: m[0])
    fuel = models.map(lambda m: m[1])
    petrol = (vehicles["vehicle_type"] == "Cargo Van") & (rng.random(len(vehicles)) < C.PETROL_SHARE_CARGO_VAN)
    vehicles["fuel_type"] = np.where(petrol, "Petrol", fuel)
    kmpl = raw_v["mpg"] * C.MPG_TO_KM_PER_L
    vehicles["km_per_l"] = np.where(petrol, kmpl * 0.85, kmpl).round(2)
    vehicles["odometer_start_km"] = (raw_v["odometer_start"] * C.KM_PER_MILE).round().astype(int)
    prefix = vehicles["depot_id"].map(lambda d: C.DEPOT_CITIES[d][2])
    vehicles["registration"] = [f"{p}-{str(y)[2:]}-{rng.integers(1000, 9999)}"
                                for p, y in zip(prefix, vehicles["year"])]

    counts = vehicles["depot_id"].value_counts().sort_index()
    depots = pd.DataFrame({"id": counts.index,
                           "name": [C.DEPOT_CITIES[d][0] for d in counts.index],
                           "city": [C.DEPOT_CITIES[d][1] for d in counts.index],
                           "vehicles": counts.values})

    # drivers per depot proportional to fleet size
    alloc = np.maximum(1, np.round(counts.values / counts.values.sum() * C.N_DRIVERS)).astype(int)
    alloc[np.argmax(alloc)] += C.N_DRIVERS - alloc.sum()
    depot_of_driver = np.repeat(counts.index.values, alloc)
    exp_years = rng.integers(1, 21, C.N_DRIVERS)
    harsh = np.clip(1.25 - 0.02 * exp_years + rng.normal(0, 0.12, C.N_DRIVERS), 0.75, 1.5)
    names = list(rng.permutation(DRIVER_NAMES)[:C.N_DRIVERS])
    drivers = pd.DataFrame({
        "id": np.arange(1, C.N_DRIVERS + 1), "name": names,
        "license_number": [f"{C.DEPOT_CITIES[d][2]}-{rng.integers(1_000_000, 9_999_999)}" for d in depot_of_driver],
        "depot_id": depot_of_driver, "experience_years": exp_years,
    })
    return vehicles, depots, drivers, harsh  # harsh stays hidden ground truth


def fuel_price_series(dates, rng):
    """Daily price per fuel type: linear drift to today's rate, weekly noise."""
    progress = np.linspace(0, 1, len(dates))
    idx = C.FUEL_PRICE_START_INDEX + (1 - C.FUEL_PRICE_START_INDEX) * progress
    weekly = np.repeat(rng.normal(0, C.FUEL_PRICE_NOISE, len(dates) // 7 + 1), 7)[:len(dates)]
    return {f: pd.Series(p * idx * (1 + weekly), index=dates) for f, p in C.FUEL_PRICE_NOW.items()}


def load_engine_pools():
    e = pd.read_csv(C.RAW / "engine" / "engine_sensors.csv")
    e.columns = ["engine_rpm", "lub_oil_pressure", "fuel_pressure", "coolant_pressure",
                 "lub_oil_temp", "coolant_temp", "label"]
    return {k: g.drop(columns="label").reset_index(drop=True) for k, g in e.groupby("label")}


def simulate(seed=C.SEED):
    rng = np.random.default_rng(seed)
    vehicles, depots, drivers, harsh = build_static(rng)
    dates = pd.date_range(C.START_DATE, C.END_DATE)
    prices = fuel_price_series(dates, rng)
    pools = load_engine_pools()
    drivers_by_depot = {d: drivers.index[drivers["depot_id"] == d].to_numpy() for d in depots["id"]}

    trips, maint, sensors = [], [], []
    end_status = {}
    for v in vehicles.itertuples():
        odo = float(v.odometer_start_km)
        lateness = rng.uniform(0.0, 0.9)  # how long this vehicle's services slip past due
        last_km = {s: odo - rng.uniform(0, C.SERVICES[s][0]) for s in SERVICE_NAMES if C.SERVICES[s][0]}
        last_day = {s: dates[0] - pd.Timedelta(days=int(rng.uniform(0, C.SERVICES[s][1])))
                    for s in SERVICE_NAMES if C.SERVICES[s][1]}
        down_until = dates[0] - pd.Timedelta(days=1)
        mult = C.COST_TYPE_MULT[v.vehicle_type]
        pool_idx = drivers_by_depot[v.depot_id]

        for day in dates:
            years = (day - dates[0]).days / 365
            infl = (1 + C.COST_INFLATION_PER_YEAR) ** years
            age = day.year - v.year
            if day <= down_until:
                continue

            ratios = {s: (odo - last_km[s]) / C.SERVICES[s][0] for s in last_km}
            debt = float(np.clip(np.mean([max(0.0, ratios[s] - 1) for s in CRITICAL if s in ratios]), 0, 2.5))

            # weekly sensor snapshot (Mondays)
            if day.weekday() == 0:
                p_attn = 0.15 + 0.6 * (1 - np.exp(-1.5 * debt))
                pool = pools[ATTENTION_LABEL if rng.random() < p_attn else 1 - ATTENTION_LABEL]
                sensors.append({"vehicle_id": v.id, "reading_date": day.date(), "odometer_km": round(odo),
                                **pool.iloc[rng.integers(len(pool))].round(3).to_dict()})

            # preventive service when overdue (acts with some probability each day -> realistic slippage)
            due = [s for s in ratios if ratios[s] >= 1 + lateness]
            due += [s for s in last_day if (day - last_day[s]).days >= C.SERVICES[s][1] * (1 + lateness / 2)]
            if due and rng.random() < 0.25:
                s = due[0]
                cost = C.SERVICES[s][2] * mult * infl * rng.lognormal(0, 0.25)
                maint.append({"vehicle_id": v.id, "maintenance_date": day.date(), "maintenance_type": s,
                              "kind": "Preventive", "odometer_km": round(odo), "cost_pkr": round(cost, -1),
                              "downtime_days": 0, "notes": f"{s} at {round(odo)} km"})
                if s in last_km:
                    last_km[s] = odo
                else:
                    last_day[s] = day
                continue  # vehicle in workshop today

            p_active = C.SUNDAY_ACTIVE_PROB if day.weekday() == 6 else C.ACTIVE_DAY_PROB
            if rng.random() > p_active:
                continue

            day_km = 0.0
            drv = pool_idx[rng.integers(len(pool_idx))]
            for _ in range(1 if rng.random() < 0.8 else 2):
                km = float(np.clip(rng.normal(C.TRIP_KM_MEAN, C.TRIP_KM_SD), C.TRIP_KM_MIN, C.TRIP_KM_MAX))
                eff = v.km_per_l * np.exp(-0.18 * debt) * (0.995 ** age) * rng.normal(1, 0.05)
                litres = km / eff
                anomaly = rng.random() < C.FUEL_ANOMALY_RATE
                if anomaly:
                    litres *= rng.uniform(1.35, 2.2)
                litres = round(litres, 1)  # cost below must equal the stored litres x stored price
                price = round(prices[v.fuel_type][day] * (1 + rng.normal(0, 0.01)), 2)
                start_h = float(np.clip(rng.normal(7.5, 1.2), 5, 11))
                dur_h = km / rng.uniform(38, 55) + 0.5
                fmt = lambda h: f"{int(h) % 24:02d}:{int((h % 1) * 60):02d}"
                trips.append({
                    "vehicle_id": v.id, "driver_id": int(drivers.at[drv, "id"]), "trip_date": day.date(),
                    "route": C.ROUTES[rng.integers(len(C.ROUTES))], "distance_km": round(km),
                    "fuel_litres": litres, "fuel_price_per_litre": price,
                    "fuel_cost_pkr": round(litres * price, 2), "start_time": fmt(start_h),
                    "end_time": fmt(start_h + dur_h),
                    "harsh_braking_events": int(rng.poisson(km / 100 * 0.6 * harsh[drv] ** 3)),
                    "odometer_end_km": round(odo + km), "is_fuel_anomaly": int(anomaly)})
                odo += km
                day_km += km

            hazard = C.HAZARD_BASE * np.exp(C.HAZARD_DEBT * debt + C.HAZARD_AGE * age
                                            + C.HAZARD_HARSH * (harsh[drv] - 1)) * (day_km / C.TRIP_KM_MEAN)
            if rng.random() < 1 - np.exp(-hazard):
                kinds = list(C.BREAKDOWNS)
                w = np.array([max(0.0, ratios.get(C.BREAKDOWNS[k][1], 0) - 1) + 0.3 for k in kinds])
                kind = kinds[rng.choice(len(kinds), p=w / w.sum())]
                med, reset = C.BREAKDOWNS[kind]
                cost = med * mult * infl * rng.lognormal(0, 0.5)
                down = int(np.clip(rng.gamma(2, 1.5) + 1, 1, 12))
                maint.append({"vehicle_id": v.id, "maintenance_date": day.date(), "maintenance_type": kind,
                              "kind": "Breakdown", "odometer_km": round(odo), "cost_pkr": round(cost, -1),
                              "downtime_days": down, "notes": f"{kind} at {round(odo)} km"})
                last_km[reset] = odo
                down_until = day + pd.Timedelta(days=down)
        end_status[v.id] = "maintenance" if down_until >= dates[-1] else "active"

    vehicles["status"] = vehicles["id"].map(end_status)
    out = {"depots": depots, "drivers": drivers, "vehicles": vehicles,
           "trips": pd.DataFrame(trips), "maintenance": pd.DataFrame(maint),
           "sensor_readings": pd.DataFrame(sensors)}
    for name in ("trips", "maintenance", "sensor_readings"):
        out[name].insert(0, "id", np.arange(1, len(out[name]) + 1))
    return out


def main():
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    tables = simulate()
    for name, df in tables.items():
        df.to_csv(C.PROCESSED / f"{name}.csv", index=False)
        print(f"{name:16s} {df.shape}")
    m = tables["maintenance"]
    n_bd = (m["kind"] == "Breakdown").sum()
    years = len(pd.date_range(C.START_DATE, C.END_DATE)) / 365
    print(f"\nbreakdowns: {n_bd} ({n_bd / len(tables['vehicles']) / years:.2f} per vehicle-year)")


if __name__ == "__main__":
    main()
