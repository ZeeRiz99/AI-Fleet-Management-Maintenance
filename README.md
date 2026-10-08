# AI Fleet Management & Maintenance System

**Live demo:** https://ai-fleet-management.streamlit.app/ (Streamlit Community Cloud; may take a minute to wake up)

Predicts which vehicles are likely to break down in the next 30 days, explains why (SHAP), flags abnormal fuel use,
and puts a rupee value on acting early. Built for a Pakistan fleet: km, litres, PKR.

```
vehicles / drivers / trips / fuel / maintenance -> SQLite -> features -> ML
   -> breakdown risk (XGBoost + SHAP) + fuel anomalies -> alerts with Rs impact -> Streamlit dashboard + assistant chat
```

## Quick start (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/run_pipeline.py            # ~4 min: data -> SQLite -> features -> models -> alerts
streamlit run app/streamlit_app.py    # dashboard at http://localhost:8501
python -m pytest -q                   # sanity tests
```

`python src/run_pipeline.py --skip-generate` reuses the existing CSVs. The raw datasets in `data/raw/` are included.

## What is in the dashboard

| Tab | What it shows |
|---|---|
| Overview | fleet KPIs, fuel cost per km trend, maintenance spend, risk by depot |
| Risk & Alerts | vehicles ranked by 30-day breakdown risk, reasons, recommended service, Rs saving, CSV export |
| Vehicle | one vehicle: risk, why, fuel-efficiency trend, engine readings, maintenance history |
| Fuel | cost per km by vehicle/model/depot/route, price trend, flagged anomalies with excess Rs |
| Maintenance | spend by type, breakdowns per month, costliest vehicles |
| Drivers | experience vs harsh braking |
| Model | metrics, SHAP drivers, honest limitations |
| Assistant | ask in Roman Urdu / English; calls the same data as tools |

### Assistant modes
| Mode | When | Needs |
|---|---|---|
| **Gemini** (free tier) | a Gemini key is set | free key from https://aistudio.google.com/apikey |
| **Claude** | an Anthropic key is set and no Gemini key | `ANTHROPIC_API_KEY` (paid) |
| **Offline** | no key, or any LLM call fails (quota, network, bad key) | nothing |

Give the key either in the dashboard sidebar ("Assistant AI key", kept only in that browser session) or as an environment
variable (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`; optional `GEMINI_MODEL`, `FLEET_AGENT_MODEL`,
`FLEET_LLM_PROVIDER=offline|gemini|anthropic`). All three modes use the same tools on the same data, so the LLM can only
quote numbers the tools return. The offline router is kept as a fallback so the demo never breaks when a free quota runs out.

**Honest status:** the Gemini and Claude tool loops are tested with fake clients (`tests/test_agent_llm.py`) and the SDK
request types are built with the real libraries, but they have **not been run against the live APIs** (no keys were
available during the build). Default Gemini model is `gemini-3.8-flash`; if Google has retired it, set `GEMINI_MODEL`.

## Project layout

| Path | Purpose |
|---|---|
| `src/config.py` | prices (petrol Rs 387.40/L, diesel Rs 400.35/L), unit conversions, simulation + cost assumptions |
| `src/generate_data.py` | hybrid generator (see below) |
| `src/db.py` | CSV -> `data/fleet.db` (SQLite) |
| `src/features.py` | weekly per-vehicle snapshots; label = breakdown in next 30 days |
| `src/train.py` | XGBoost, time-based split, threshold on validation, SHAP |
| `src/anomaly.py` | fuel anomaly detection: rolling-baseline rule vs IsolationForest |
| `src/alerts.py` | today's scores + reasons + cost impact -> `data/processed/alerts.csv` |
| `src/agent.py` | assistant tools + offline/Claude chat |
| `src/eda.py` | data-quality report -> `reports/data_quality.md` |
| `app/streamlit_app.py` | dashboard |
| `tests/` | data integrity, no-leakage, label, model, alert and assistant tests |

## Data: hybrid, and what that means

* **mindweave/vehicle-fleet-management** (Hugging Face, CC-BY-NC): the free sample has only 58 vehicles, 15 drivers and 50
  maintenance rows and no breakdown labels. It is used as the **template**: vehicles, depot sizes, trip-distance and mpg
  statistics, converted to km/litres/PKR and mapped to Pakistani cities and models (Hiace, Isuzu NPR, Sprinter).
* **mukherjee78/predictive-maintenance-engine-data** (Hugging Face, MIT): 19,535 real engine-sensor readings. Weekly
  sensor readings per vehicle are **sampled from it**, from the "needs attention" class more often when the vehicle's
  services are overdue. The README of that dataset does not define its labels; label 0 is assumed "needs attention"
  because it shows higher RPM and lower fuel pressure.
* **Simulated** 2023-2025: trips, fuel, maintenance and breakdowns. Breakdown hazard depends on overdue services, vehicle
  age and driver harshness; fuel anomalies (+35% to +120% litres) are injected as ground truth. The generator is kept so
  the project does not depend on the non-commercial licence of mindweave.

## Results (time-based test on 2025) and how to read them

**Breakdown risk** (train < 2024-12-01, 30-day gap, test 2025; 2,689 weekly snapshots, 20% positive):

| Model | ROC-AUC | PR-AUC | Precision | Recall | Precision in top 10% |
|---|---|---|---|---|---|
| XGBoost | 0.741 | 0.414 | 0.343 | 0.690 | 0.515 |
| Baseline: overdue-service rule | 0.705 | 0.411 | 0.396 | 0.479 | 0.519 |
| Random | 0.500 | 0.200 | - | - | - |

Probabilities are not re-weighted for class imbalance, so they are close to calibrated (mean predicted 16% vs 20% actual on
test). The threshold (0.133) is chosen on a validation window. Main drivers (SHAP): vehicle age, overdue-service load, km since
brake / transmission service, change in fuel efficiency.

**Fuel anomalies** (test 2025): rule "km/l below 0.81 x the vehicle's own recent median" gets precision 0.99 / recall 1.00
(F1 0.994); IsolationForest gets F1 0.941. This is high because the injected anomalies are strong - expect lower on real data.

**Alerts today:** 9 High, 21 Medium, 28 Low vehicles; servicing the High/Medium ones is estimated to save about Rs 0.6M net
under the assumptions below.

## Assumptions to review (all in `src/config.py`)

* Downtime costs Rs 25,000 per vehicle-day; an overdue service removes 60% of breakdown risk. These drive every "net saving" figure.
* Risk tiers: High >= 30%, Medium >= 15% probability of a breakdown within 30 days.
* Fuel prices: today's rates are the ones given; the earlier history is a smooth simulated drift, not real prices.
* "Today" is 2026-01-01 (the day after the data ends).

## Limitations

* The fleet is simulated, so the model rediscovers the structure that was put into the data. It shows the method works end to
  end; it does not prove accuracy on a real fleet. Re-train on real telematics/maintenance records before relying on it.
* The risk model beats a plain "overdue services" rule on recall and ROC-AUC but not clearly on top-10% precision.
* Fuel anomalies are easy to detect here because they were injected strongly; real leaks and theft are subtler.
* GPS/IoT is out of scope; it is a natural extension (live odometer, idling, routes).

## Data sources and licences

| Data | Source | Licence | Use here |
|---|---|---|---|
| `data/raw/{depots,drivers,vehicles,trips,maintenance}.csv` | Hugging Face `mindweave/vehicle-fleet-management` (free sample) | CC-BY-NC 4.0 (non-commercial) | template for the simulator; academic use |
| `data/raw/engine/engine_sensors.csv` | Hugging Face `mukherjee78/predictive-maintenance-engine-data` | MIT | real engine-sensor readings sampled into the simulation |
| `data/processed/*`, `data/fleet.db` | generated by `src/generate_data.py` | this project | simulated fleet (2023-2025) |

Attribution: mindweave (vehicle-fleet-management) and mukherjee78 (predictive-maintenance-engine-data) on Hugging Face.
Because of the non-commercial licence, do not use the bundled mindweave sample in a commercial product; the generator can
be rewritten to run without it.

## Python version and install notes
Python 3.11+ (developed on 3.14). `requirements.txt` has loose minimums; `requirements-lock.txt` has the exact versions
the results above were produced with. Generated files (`data/processed`, `data/fleet.db`, `models/`, `reports/`) are
included so the dashboard runs immediately; `python src/run_pipeline.py` rebuilds them.
