"""Run the whole pipeline end to end:  python src/run_pipeline.py [--skip-generate]

generate data -> SQLite -> features -> risk model -> fuel anomalies -> alerts.
(features.py takes ~2.5 minutes; --skip-generate reuses existing data/processed/*.csv)
"""
import sys
import time

import alerts
import anomaly
import config as C
import db
import features
import generate_data
import train


def step(name, fn):
    t = time.time()
    print(f"\n=== {name} ===")
    fn()
    print(f"[{name}: {time.time() - t:.0f}s]")


def make_features():
    features.build_features().to_csv(C.PROCESSED / "features.csv", index=False)


def make_alerts():
    alerts.score_today().to_csv(C.PROCESSED / "alerts.csv", index=False)


if __name__ == "__main__":
    if "--skip-generate" not in sys.argv:
        step("generate data", generate_data.main)
    step("load SQLite", db.build_db)
    step("features", make_features)
    step("train risk model", train.main)
    step("fuel anomalies", anomaly.main)
    step("alerts + cost impact", make_alerts)
    print("\nDone. Launch the dashboard:  streamlit run app/streamlit_app.py")
