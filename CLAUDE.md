# AI Fleet Management and Maintenance System

User writes in Roman Urdu; reply in Roman Urdu. Pakistan context: km, litres, PKR.
Class project first, freelance portfolio later. Hero feature = **predictive maintenance**.

## Environment
- Windows, PowerShell. Python 3.14 venv at `.venv` (activate: `.venv\Scripts\Activate.ps1`, or call `.venv\Scripts\python.exe`).
- Packages in requirements.txt: pandas, numpy, scikit-learn, xgboost, shap, streamlit, plotly, sqlalchemy, datasets, huggingface_hub.
- Keep all work inside this folder. Scripts in `src/` import `config as C` (run as `python src/xxx.py`).

## Architecture (agreed)
Vehicles/Drivers/Trips/Fuel/Maintenance -> SQLite -> features -> ML (risk model, fuel anomaly, SHAP)
-> alerts + Rs cost impact -> Streamlit dashboard -> (last) agent chat that calls DB/model as tools.
SQLite, not PostgreSQL. GPS/IoT is NOT in scope (future extension).

## Data (hybrid)
- `data/raw/*.csv`: mindweave/vehicle-fleet-management free sample (CC-BY-NC, US units, tiny: 58 vehicles, 50 maintenance rows, no breakdown labels).
- `data/raw/engine/engine_sensors.csv`: mukherjee78/predictive-maintenance-engine-data (MIT, 19,535 rows). Label 0 assumed "needs attention" (README does not define it; signal is weak).
- `src/generate_data.py` simulates 2023-01-01..2025-12-31 in Pakistan units, modelled on mindweave, with weekly sensor readings sampled from the engine data. Output: `data/processed/*.csv`. Fixed seed 42.
- `src/db.py` loads CSVs into `data/fleet.db`. `src/config.py` holds prices (petrol Rs 387.40/L, diesel Rs 400.35/L), conversions, hazard parameters.
- Current output (fuel_cost = litres x price exactly; fixed after a test caught rounding drift): ~48.5k trips, ~3.8k maintenance rows (379 breakdowns, 2.18/vehicle-year), ~8.9k sensor readings, 58 vehicles, 24 drivers, 3 depots (Lahore, Islamabad, Karachi).
- Hazard params were tuned (HAZARD_DEBT=10, AGE=0.30, BASE=0.0011) because the first values (2.2) made risk almost unlearnable (ROC-AUC 0.51). The planted structure is service debt + age + driver harshness; say this openly in the report (synthetic data).
- Known caveats: fuel price history is simulated drift, not real; `is_fuel_anomaly` is ground truth for evaluation only (never a feature); all vehicles end as "active".

## Status: build COMPLETE (all modules delivered, 33 tests pass)
- [x] Env, data download, config, generator, SQLite (`src/run_pipeline.py` runs everything, ~4 min)
- [x] EDA -> `reports/data_quality.md` (`src/eda.py`); features; XGBoost risk model (ROC 0.741, recall 0.69; baseline rule ROC 0.705, top-10% precision equal) + SHAP
- [x] Fuel anomaly (`src/anomaly.py`, F1 0.994 on injected anomalies; too easy, say so), alerts + Rs cost impact (`src/alerts.py`, assumptions in config.py)
- [x] Streamlit dashboard `app/streamlit_app.py` (8 tabs, screenshot-checked with Playwright+Edge), assistant chat `src/agent.py`
- [x] tests/test_pipeline.py, README.md
- Assistant has 3 modes (Gemini free tier / Claude / offline fallback) in `src/agent.py`; key can be pasted in the dashboard sidebar. 33 tests pass. Gemini+Claude loops are tested with FAKE clients only; never run live (no keys during build). Default Gemini model `gemini-3.8-flash` (override with GEMINI_MODEL); on 404/429 it auto-falls to the next flash/flash-lite model, retries 503s, and on total failure uses the offline router. User saw live 503 and 429 (free quota) from Gemini, so the request format reached Google, but a full successful Gemini tool-call answer was never confirmed.
- Done: git repo (pushed to GitHub, public by user choice: https://github.com/ZeeRiz99/AI-Fleet-Management-Maintenance), clean-install test from the zip (33 passed). Not done: deploy. `notebooks/` is empty on purpose (EDA is `src/eda.py` -> reports/data_quality.md).
- Ideas if continuing: real data instead of simulation; tune model / try survival model; WhatsApp/email alerts; deploy (Streamlit Cloud); GPS/IoT.

## Rules agreed with user
- Time-based split, never random (avoid leakage). Report precision/recall.
- Keep the synthetic generator as a portfolio asset (avoids mindweave NC license issue for clients).

## UI / design conventions (dashboard redesign, Oct 2026)
- Theme lives in `.streamlit/config.toml`: light base, primary #2563EB, background #F4F6FB, dark navy sidebar (#0F172A).
- All styling is in the `CSS` string at the top of `app/streamlit_app.py`. Don't scatter inline styles elsewhere.
- Helpers to reuse for new UI:
  - `kpi(col, icon, label, value, sub, tone, full=None)` -> KPI card; tones: blue, green, red, amber, violet, teal.
    Use `rs_short()` (Rs 1.95 Cr / Rs 39.9 Lakh) for rupee KPI values and pass the exact `rs()` amount as `full` (hover).
  - `card()` -> white rounded container (key prefix `card_`, styled via `.st-key-card_*`)
  - `chart_card(fig, h)` -> chart inside a card; always use this (or `chart()`) instead of st.plotly_chart directly.
    `chart()` sets paper/plot bgcolor explicitly because Streamlit 1.64 paints unset ones with the theme grey even with theme=None.
  - `section(title, sub)` -> section heading
- Charts: use the `px` wrapper (applies LABELS + "plotly_white+fleet" template).
- Colors: risk tiers via TIER_COLORS (High red, Medium amber, Low green); Preventive/Breakdown via KIND_COLORS.
- Tables: always give st.dataframe a column_config with readable names and Rs/number formatting; never mix numbers and
  strings in one column (Arrow error) - format the whole column as text instead.
- Tabs CSS targets `[data-testid="stTab"]` / `[role="tablist"]` (Streamlit >= 1.60, react-aria) with `data-baseweb` fallbacks.
- KPI rows hold at most 3-4 cards so values never get cut off (Overview uses 2 rows of 3).
- Assistant tab: chat_input uses key="chat_q"; user bubbles styled blue via :has(stChatMessageAvatarUser); badge shows short provider name.
- Checked visually at 1440 px and 390 px (phone) with Playwright + Edge. Don't change the data/model logic when doing UI work.
