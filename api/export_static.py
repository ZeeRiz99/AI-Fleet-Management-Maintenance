"""Export a read-only snapshot of the REST API as static JSON files (served from GitHub for the Android app).

    python -m api.export_static            # writes static-api/v1/...

The Android app's "GitHub data" mode reads these files from raw.githubusercontent.com, so it works on any phone
without a running server. Every file is a real API response produced by the same code and model (XGBoost + SHAP)
on a fresh copy of the demo database; nothing is hand-made. Writes (record a service / re-score) still need the
live server. Re-run this after retraining the model or regenerating the data, then commit static-api/.
"""
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static-api" / "v1"
PAGE = 200                      # API maximum page size
TRIPS_EXPORTED = 300            # newest trips in the global list (the full table has ~48k rows)
FUEL_DAYS = (7, 30, 90, 365)    # periods offered by the app's Fuel screen
DRIVER_DAYS = 180


def write(rel, data):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def paged(client, url, params, total=None):
    items, offset = [], 0
    while True:
        page = client.get(url, params={**params, "limit": PAGE, "offset": offset}).raise_for_status().json()
        items += page["items"]
        offset += PAGE
        limit = page["total"] if total is None else min(total, page["total"])
        if offset >= limit or not page["items"]:
            return page, items[:limit]


def main():
    runtime = tempfile.mkdtemp(prefix="fleet_export_")
    os.environ["FLEET_RUNTIME_DIR"] = runtime          # fresh demo copy: no services recorded from the app
    from fastapi.testclient import TestClient
    from api import main as api_main
    from api import settings as S
    import config as C

    if OUT.exists():
        shutil.rmtree(OUT)
    try:
        with TestClient(api_main.app) as client:
            password = os.environ.get("FLEET_ADMIN_PASSWORD", S.DEMO_PASSWORD)
            token = client.post("/api/v1/auth/login", json={"username": S.ADMIN_USER, "password": password})
            client.headers["Authorization"] = f"Bearer {token.raise_for_status().json()['access_token']}"
            client.post("/api/v1/admin/reset-demo").raise_for_status()   # always publish the original demo data
            get = lambda url, **params: client.get(f"/api/v1/{url}", params=params).raise_for_status().json()

            write("health.json", get("health"))
            write("dashboard.json", get("dashboard"))
            vehicles = get("vehicles")
            write("vehicles.json", vehicles)
            for v in vehicles:
                write(f"vehicles/{v['id']}.json", get(f"vehicles/{v['id']}"))

            write("maintenance/summary.json", get("maintenance/summary"))
            for status in ("overdue", "due_soon", "ok", "unknown"):
                write(f"maintenance/schedule_{status}.json", get("maintenance/schedule", status=status, limit=600))
            _, history = paged(client, "/api/v1/maintenance/history", {})
            write("maintenance/history.json", {"total": len(history), "items": history})

            for days in FUEL_DAYS:
                write(f"fuel/summary_{days}.json", get("fuel/summary", days=days))
                write(f"fuel/anomalies_{days}.json", get("fuel/anomalies", days=days, limit=100))
            svc = api_main.service()
            baselines = {}
            for vid in svc.vehicle_ids():
                hist = svc.trips[svc.trips.vehicle_id == vid].tail(svc.anomaly_window)
                v = svc.vehicles.loc[vid]
                baselines[str(int(vid))] = {"registration": v.registration, "baseline_km_per_l": float(hist.kmpl.median()),
                                            "fuel_price": C.FUEL_PRICE_NOW[v.fuel_type]}
            write("fuel/baselines.json", {"threshold": svc.anomaly_threshold, "window": svc.anomaly_window,
                                          "vehicles": baselines})

            drivers = get("drivers", days=DRIVER_DAYS)
            write("drivers.json", drivers)
            for d in drivers["items"]:
                write(f"drivers/{d['id']}.json", get(f"drivers/{d['id']}", days=DRIVER_DAYS))
            first, trips = paged(client, "/api/v1/trips", {}, total=TRIPS_EXPORTED)
            write("trips.json", {**first, "total": len(trips), "all_trips": first["total"], "items": trips,
                                 "note": f"{first['note']} This offline snapshot lists the {len(trips)} most recent of "
                                         f"{first['total']:,} trips."})

            write("alerts.json", get("alerts"))
            write("ai/model.json", get("ai/model"))

            commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                    text=True).stdout.strip()
            write("manifest.json", {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "source_commit": commit, "as_of": C.AS_OF_DATE, "vehicles": len(vehicles),
                                    "drivers": len(drivers["items"]), "maintenance_records": len(history),
                                    "trips_exported": len(trips)})
    finally:
        shutil.rmtree(runtime, ignore_errors=True)
    files = list(OUT.rglob("*.json"))
    print(f"wrote {len(files)} files, {sum(f.stat().st_size for f in files) / 1e6:.1f} MB -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
