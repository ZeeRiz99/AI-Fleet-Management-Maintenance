"""Load the generated CSVs into SQLite (data/fleet.db) and provide a query helper.

Run:  python src/db.py
"""
import sqlite3

import pandas as pd

import config as C

TABLES = ["depots", "drivers", "vehicles", "trips", "maintenance", "sensor_readings"]
INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_trips_vehicle_date ON trips(vehicle_id, trip_date)",
    "CREATE INDEX IF NOT EXISTS ix_trips_driver ON trips(driver_id)",
    "CREATE INDEX IF NOT EXISTS ix_maint_vehicle_date ON maintenance(vehicle_id, maintenance_date)",
    "CREATE INDEX IF NOT EXISTS ix_sensor_vehicle_date ON sensor_readings(vehicle_id, reading_date)",
]


def build_db():
    with sqlite3.connect(C.DB_PATH) as con:
        for name in TABLES:
            pd.read_csv(C.PROCESSED / f"{name}.csv").to_sql(name, con, if_exists="replace", index=False)
        for stmt in INDEXES:
            con.execute(stmt)


def query(sql, params=()):
    with sqlite3.connect(C.DB_PATH) as con:
        return pd.read_sql_query(sql, con, params=params)


if __name__ == "__main__":
    build_db()
    for name in TABLES:
        print(f"{name:16s} {query(f'SELECT COUNT(*) n FROM {name}').at[0, 'n']:>7} rows")
    print(query("""SELECT v.make_model, v.fuel_type, COUNT(DISTINCT v.id) vehicles,
                          ROUND(SUM(t.fuel_cost_pkr) / SUM(t.distance_km), 1) pkr_per_km
                   FROM vehicles v JOIN trips t ON t.vehicle_id = v.id GROUP BY 1, 2""").to_string(index=False))
