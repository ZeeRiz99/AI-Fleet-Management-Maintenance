# FleetAI: Android app

Native Android client for the **AI Fleet Management & Maintenance System**
([backend + ML repo](https://github.com/ZeeRiz99/AI-Fleet-Management-Maintenance),
[web dashboard](https://ai-fleet-management.streamlit.app/)).
A fleet manager can see which vehicles are likely to break down in the next 30 days and why. They can record a
service and watch the real model re-score the vehicle, check fuel fill-ups for abnormal use, and work through alerts.
Built for a Pakistan fleet: km, litres, PKR.

```
Android app (Kotlin, Compose)  --HTTPS/JSON + JWT-->  FastAPI (/api/v1)  -->  SQLite (fleet data)
                                                          |
                                                          +--> XGBoost risk model + SHAP, fuel-anomaly rule
```

The app never talks to Streamlit or the database directly. Everything goes through the REST API.

## Screens

| Screen | What it does |
|---|---|
| Login | JWT sign-in; the session survives app restarts until the token expires |
| Home (Dashboard) | fleet KPIs, AI risk split (High/Medium/Low), top at-risk vehicles, health ring, 30-day fuel summary, quick links |
| Vehicles | search, filter chips (risk tier, status, vehicle type), sort (risk, health, mileage, registration) |
| Vehicle detail | specs, health score, **AI prediction** (risk %, plain-language explanation, SHAP factor bars), recommendation with Rs saving, **Mark service done** (writes to the API, model re-scores), **Re-run AI**, maintenance schedule and history, recent trips |
| Maintenance | overdue / due-soon / spend summary, tabs: Overdue, Upcoming, Completed (paged, Preventive vs Breakdown filter) |
| Fuel analytics | 7/30/90/365-day totals, 24-month cost, efficiency and diesel price charts, cost per km by vehicle/depot/model, **AI fuel-entry check**, detected anomalies |
| Drivers + driver detail | safety and performance scores (formulas shown on screen), most-driven vehicle, recent trips |
| Trips | completed trips, newest first (an honest "0 live" card: GPS tracking is not in the data) |
| Alerts | unread badge on the bottom bar, category filters, mark read / mark all read (optimistic, rolled back on error) |
| Profile | account, light/dark/system theme, server address + **Test connection**, AI model card (metrics, SHAP drivers), reset demo data, sign out |

Bottom navigation: Home · Vehicles · Maintenance · Alerts · Profile. Fuel, Drivers and Trips open from Home.

Every data screen has loading skeletons, empty and error states with retry, and pull-to-refresh. If the server is
unreachable, the last successful response is shown with an "Offline — showing data saved …" banner (read-only cache).

## AI features (all real, none mocked)

- **Breakdown risk (XGBoost)**: 30-day breakdown probability per vehicle, trained on a time-based split
  (test = 2025, ROC-AUC 0.74, recall 0.69). Served by the API; the app shows it, never computes it.
- **Explanations (SHAP)**: top factors that raise or lower each vehicle's risk, with readable values.
- **Write-back loop**: "Mark service done" inserts a preventive service record, then the API rebuilds features and
  re-scores the vehicle. Example from testing: a Brake Inspection on BAB-21-6978 moved risk from 65% to 28%
  (High → Medium) and health from 20 to 62. Profile → "Reset demo data" undoes it.
- **Fuel anomaly check**: a trip's km/l is compared with the vehicle's median over its previous 15 trips and flagged
  below 0.81× (F1 0.99 on injected anomalies; synthetic, so that number is optimistic).
- **Health / safety / performance scores**: transparent formulas, printed on the screens that use them.

The fleet data is simulated (hybrid of two public datasets + a generator); see the backend README for details and limits.

## Architecture

MVVM, single activity, Jetpack Compose, unidirectional data flow.

```
ui/screens (Composables)  ->  presentation (ViewModels, StateFlow<ScreenState<T>>)
                          ->  data/repository/FleetRepository  ->  data/remote (Retrofit FleetApi)
                                                               ->  data/local (DataStore settings, response cache)
```

| Package | Contents |
|---|---|
| `di/AppContainer` | manual dependency injection (one container per app; no Hilt to keep the build light) |
| `data/remote` | `FleetApi` (Retrofit), `ApiProvider` (rebuilds the client when the server URL changes, adds the bearer token), `ApiResult` (Success / typed Failure) |
| `data/local` | `SettingsStore` (DataStore: theme, server URL, session), `ResponseCache` (last good JSON per endpoint) |
| `data/repository` | `FleetRepository`: `fetch` caches successful reads and falls back to the cache when offline; `send` for writes (never cached); a 401 clears the session |
| `domain/model` | serializable DTOs matching the API (snake_case via `JsonNamingStrategy.SnakeCase`) |
| `presentation` | one ViewModel per screen, `ScreenState<T>` (loading / data / error / offline / refreshing) |
| `navigation` | type-safe routes, bottom bar with alert badge, login gate |
| `ui/theme`, `ui/components` | Material 3 light/dark schemes, semantic tones (critical/warning/success/info), cards, chips, Canvas charts (no chart library) |

**Stack:** Kotlin 2.2, AGP 9.2, Compose BOM 2026.06, Material 3, Navigation 2.9, Lifecycle 2.10, Retrofit 3 +
OkHttp 4, kotlinx.serialization 1.9, DataStore, SplashScreen. minSdk 26, targetSdk 36.

## Run it

### 1. Start the API (on the laptop)

In the backend repo (see its README for the one-time setup):

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Interactive API docs: http://localhost:8000/docs. Demo login: `admin` / `fleet123` (set `FLEET_ADMIN_PASSWORD`
for anything beyond a local demo).

### 2. Build and install the app

Open this folder in Android Studio and press Run. Or from PowerShell:

```powershell
.\gradlew.bat assembleDebug            # APK: app\build\outputs\apk\debug\app-debug.apk
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

### 3. Point the app at the server

| Device | Server address (Login screen → "Server", or Profile → Server) |
|---|---|
| Android emulator | `http://10.0.2.2:8000` (default) |
| Phone over USB | run `adb reverse tcp:8000 tcp:8000`, then use `http://localhost:8000` |
| Phone on the same Wi-Fi | `http://<laptop LAN IP>:8000` (allow port 8000 in Windows Firewall) |

Use **Profile → Test connection** to check it.

## Tests

```powershell
.\gradlew.bat testDebugUnitTest
```

`ApiContractTest` (9 tests) decodes real JSON responses captured from the running API
(`app/src/test/resources/api/`) with the app's own JSON settings. It also covers the filter, sort and alert-read logic.
If the API's response shape changes, these tests fail before the app does. The backend has its own 47 tests
(including 14 API tests). Every screen was checked by hand on an emulator in light and dark mode.

## Production checklist (not done for the class demo)

- Serve the API over **HTTPS** and remove `cleartextTrafficPermitted` from `res/xml/network_security_config.xml`.
- Set `FLEET_API_SECRET` and `FLEET_ADMIN_PASSWORD`; add real user management and roles (the API has one admin user).
- Move SQLite to PostgreSQL for concurrent writes; run uvicorn behind a reverse proxy with several workers.
- Store the token in EncryptedSharedPreferences / Keystore, and add refresh tokens.
- Release build: enable R8 minification, sign with a release key, change `DEFAULT_API_URL` to the hosted API.
- Push notifications (FCM) for new High-risk alerts; live GPS tracking needs real telematics data.
- Retrain the model on real fleet data; the current metrics come from simulated data.
