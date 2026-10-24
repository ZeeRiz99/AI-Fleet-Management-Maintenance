# FleetLog AI — AI Fleet Log Assistant (spec v2)

*Urdu voice notes samjhe, breakdown se pehle alert kare, workshop book kare.*
*Understands Urdu voice notes, alerts before breakdowns, books the workshop.*

Status: **approved 2026-10-20**, branch `feature/fleetlog-ai`. Base = the owner's master prompt (Claude Desktop
brainstorm) + 10 agreed changes + driver role + model strategy. This file is the reference for every phase.

## 1. Product and scope

FleetLog AI turns the existing ML (XGBoost breakdown risk + SHAP reasons in `data/processed/alerts.csv`, fuel
anomalies) and the existing assistant (`src/agent.py`: 7 data tools, Gemini/Claude tool loops, offline router) into an
**agent that takes actions**, for two roles (driver and manager) on Telegram, WhatsApp and the Android app.

- **Naming**: brand **FleetLog AI** (bot, app screen, LinkedIn); subtitle **AI Fleet Log Assistant**. The repo and
  project name stay `AI-Fleet-Management-Maintenance`; the agent lives in `ops/`, like `android/`.
- **Scope now**: portfolio/demo on **free tiers, no credit card**. Design is **client-ready**: every provider, key,
  limit and target is configured by environment variables, so a client deployment changes settings, not code.
- **Honesty**: the fleet is simulated; risk data is a snapshot **as of 1 Jan 2026** (no live re-scoring in the hosted
  bundle, which has no XGBoost/SHAP); booking slots use the real current time. Replies say so where it matters.

## 2. Roles

### Driver (the main source of the log)
Drivers use **WhatsApp or Telegram, mostly Urdu/Punjabi voice notes**; they will not install an app or fill forms.
A driver sees **only their own vehicle and their own data** (no other drivers, no costs, no fleet-wide data).

| # | Driver action | Example | What the agent does |
|---|---|---|---|
| 1 | Shift start | "Aaj LEA-22-2030 chala raha hoon, meter 45,200" | Links driver to the vehicle for the day, logs odometer |
| 2 | Pre-trip check | Buttons: tyres ✅ brakes ✅ oil ✅ lights ❌ | Any ❌ is logged as an issue automatically |
| 3 | Fuel log | "45 litre, Rs 18,000" or a fuel-receipt photo | Reads receipt (vision) → AI fuel check → abnormal use alerts the manager |
| 4 | Problem report | 🎤 "Brake se awaaz aa rahi hai" | Safety advice first → risk check → escalation → workshop booking |
| 5 | Emergency / accident | "Accident ho gaya" + shared location | Immediate manager alert with the location (driver's phone GPS, no tracker) |
| 6 | Workshop booking | "Pehla wala slot" | Locks the slot, confirms, sends workshop address |
| 7 | Reminders (from the agent) | "Oil change 500 km mein due hai" | Proactive messages |
| 8 | My score | "Meri driving kaisi hai?" | Own safety score + tips in Urdu |

Driver tools: `set_my_vehicle`, `start_shift`, `pretrip_check`, `log_fuel`, `report_issue`, `report_emergency`,
`find_service_slots`, `book_service`, `my_bookings`, `my_score`, `vehicle_report` (own vehicle only).

### Manager
All 7 existing data tools + `open_issues`, `upcoming_bookings`, `morning_brief`, **`plan_services(budget)`** (most
saving within a budget), **`what_if(vehicles)`** (expected loss before/after servicing, existing `net_saving` formula),
and actions on alerts: **Approve booking · Reschedule · Call driver · Resolved** (Telegram inline buttons; text
commands elsewhere). Writes by the agent need the manager's approval where they affect money or schedules.

### Workshop (later, optional)
Receives bookings, confirms, marks done → service recorded.

### Closed loop
Driver voice/photo → structured log (fuel, km, issues) → store → manager decisions and bookings → reminders to the
driver. With a real client the logs replace the simulated data and the model is retrained on them.

## 3. Workflow

1. **Identify**: `/start`, `driver <REG>`, `manager`, `subscribe`, `unsubscribe`, `brief`, `reset`. Only messages of
   ≤3 words or starting with `/` are commands. Registrations are normalised (`lea 22 2030`, `LEA222030` →
   `LEA-22-2030`) and validated against `alerts.csv`.
2. **Report issue** (text, or voice → transcribed to Roman Urdu) → `report_issue(description, severity
   low|medium|high|critical, category brakes|engine|tyres|electrical|fuel|overheating|accident|other)` → issue
   `ISS-1001…` with the vehicle's risk %, tier and top reasons. Suggested service follows the complaint (brakes →
   Brake Inspection, overheating → Coolant Flush, …); the model's `recommended_service` is mentioned if different.
   **Safety advice first** for critical / brakes / accident / overheating.
3. **Escalate** if severity high/critical, OR risk tier High, OR category brakes/accident/overheating with severity ≥
   medium. Otherwise log only (still in the brief).
4. **Manager alert** to configured targets (`TELEGRAM_MANAGER_CHAT_IDS`, `WHATSAPP_MANAGER_NUMBERS`, plus users who
   sent `subscribe`) with action buttons, and event `issue.reported` to the event webhook (`X-Fleet-Secret`).
   **Demo mode** (`OPS_DEMO_MODE=1`): the reporter also sees "— Demo: manager ko ye alert gaya —" + the copy.
5. **Booking**: `find_service_slots` → free slots in the vehicle's depot city (2 workshops per city: Lahore, Islamabad,
   Karachi; placeholder names; 09/11/14/16; Sunday closed; ≥1 h ahead; Asia/Karachi). Slot id `LHR1-20261021-09`.
   User picks ("pehla wala", a number or the code) → `book_service` locks atomically (SET NX: no double booking;
   rejects wrong city and past slots), links to the latest open issue (status → `service_booked`), booking
   `BK-2001…`, manager notified + event `booking.created`.
6. **Morning brief** (`/jobs/morning-brief`, `CRON_SECRET` bearer, once per day, `?force=1` resends): high-risk
   vehicles + Rs saving, fuel-theft suspects (30 d), driver reports (24 h), bookings (48 h), data note. JSON at
   `GET /api/v1/ops/brief|issues|bookings` (same secret).
7. **Manager questions** at any time with the manager tools.
8. **Offline fallback**: no key, daily budget used (`OPS_MAX_LLM_CALLS_PER_DAY`, default 400) or LLM error → keyword
   router runs the **same workflow**.

The driver workflow is a **LangGraph state graph** (identify → classify → report → assess risk → escalate → slots →
book → respond), checkpointed per chat; tools are plain Python functions shared with the offline router.

## 4. Models (free tiers, provider-agnostic)

One **OpenAI-compatible** client; changing provider = changing `base_url` + model name in env.

| Task | Hosted (free tier) | Local / offline |
|---|---|---|
| Agent chat + tool calling | Gemini Flash (2 models, busy → next) → fallback Groq (gpt-oss-120b) | Ollama + a 3–4B model (e.g. Qwen 2.5 3B) |
| Urdu voice → text | Gemini audio or Groq Whisper | whisper.cpp small (slow) |
| Fuel receipt photo | Gemini vision | — |
| Intent routing | own small ML classifier (no LLM call) | same |
| Embeddings / search | — | Hugging Face multilingual model, local |
| Last resort | offline keyword router | same |

Chain: Gemini → Groq → Ollama (only when reachable) → offline. Laptop: 8 GB RAM, no GPU → only 3–4B quantised models,
slow; local models never run on the hosted bundle. Hugging Face is used to download models/datasets (Spaces need PRO;
free inference credits are too small for production). Ollama is installed only after asking (~2 GB).

## 5. Architecture and hosting

```
Telegram (text/voice/location) ─webhook─┐
WhatsApp (text/voice/location) ─webhook─┼─> ops/web.py ─> ops/brain.py ─> LangGraph workflow + LLM agent + offline router
Android app (STT text) ─REST────────────┘           │
                                      tools: src/agent.py + ops/workflow.py; data: alerts.csv, fleet.db, fuel baselines
                                      ops/store.py: Upstash Redis (hosted) / SQLite (local + tests)
Vercel Cron 08:00 PKT ─> /jobs/morning-brief ─> managers;   events ─> n8n or Apps Script webhook ─> Sheets/email
```
- Free, no card: **Vercel Hobby** (Python functions; non-commercial), **Upstash Redis** free, **Gemini** free tier.
  Limits are checked against current official docs in Phase 3 before relying on them.
- Starlette (or FastAPI if the bundle stays small). `python -m ops.vercel_bundle` builds a small `build/vercel/`
  (git-ignored) with only what the ops service needs, `vercel.json` (rewrite → `/api/index`, cron) and an
  `api/index.py` that copies `fleet.db` to `/tmp` when the filesystem is read-only.

## 6. Channels and security
- **Telegram**: `POST /webhooks/telegram`, verify `X-Telegram-Bot-Api-Secret-Token`, private chats only, dedupe by
  `update_id`, typing indicator, voice via getFile, location messages, inline buttons, always 200.
  `python -m ops.setup_telegram <url>` sets webhook, commands, and shows webhook info.
- **WhatsApp (Meta Cloud API)**: GET verify, POST with `X-Hub-Signature-256` HMAC, dedupe by message id, mark read,
  audio via media id. 24-hour service window → Telegram is the demo manager channel; WhatsApp is the real driver
  channel for clients.
- **Android REST**: `POST /api/v1/agent/chat {session_id, message, role?, registration?}` → `{reply, mode, events,
  profile}`; optional `X-App-Key` (soft limit only, an APK key can be extracted); real protection = 2000-char limit,
  per-user and per-IP daily caps.
- `OPS_RESTRICT_MANAGER=1` for clients. `/health`: provider, store, channels, warnings. Secrets only in env; `.env.example`
  committed, `.env` git-ignored.
- Chat formatting: no markdown tables/headings on Telegram/WhatsApp (tables → "•" lines). History: last 10 turns,
  2-day TTL, never containing the demo copy.

## 7. Android ("Ask FleetLog AI")
Route `assistant`, opened from an ExtendedFloatingActionButton on the Dashboard; Driver/Manager chips, vehicle number,
suggestion chips, chat bubbles, event cards. Voice in via RecognizerIntent (ur-PK / en-IN), voice out via TextToSpeech;
**fallbacks**: if Urdu speech or the Urdu TTS voice is missing (e.g. Oppo A15), typing and English TTS still work.
Follow existing patterns (FleetJson, ApiResult, DataStore, container factories, FleetScaffold, FleetIcons). App name
"FleetAI" → "FleetLog AI" in this phase (v1.1 APK). Agent URL and soft app key from `android/local.properties` (`fleetlog.url`, `fleetlog.appKey`).
Ask before starting the emulator.

## 8. Phases (stop after each: tests, summary, screenshots, wait for "ok")
| # | Phase | Status (24 Oct 2026) |
|---|---|---|
| 0 | Discover existing work | **done**: nothing to integrate (no ops/ code, no patch file, n8n not installed) |
| 1 | Workflow core (LangGraph) + store + tools (driver + manager) + offline router + LLM layer with fakes + tests | **done**, live with Gemini + Groq |
| 2 | Telegram webhook + buttons + setup script + tests → local test | **done**, live-tested (laptop polling, then Vercel); no tunnel needed |
| 3 | Vercel bundle + deploy guide (verify free-tier limits) → live /health + full Telegram flow | **done**: https://fleetlog-ai.vercel.app, Upstash us-east-1 |
| 5 | Android "Ask FleetLog AI" screen → build, test on phone | built + unit-tested (v1.1 debug); emulator/phone test and release APK pending |
| 4 | Morning brief job (Vercel Cron) + optional n8n / Apps Script workflows | **done**; brief live-tested; Apps Script sample instead of n8n |
| 6 | WhatsApp → Meta test number | built + unit-tested; waiting for a Meta app |
| 7 | Docs (ops/README, limits and honesty notes), README sections, CLAUDE.md; ask before pushing the branch | docs done; release APK + merge to main need the user's OK |

Deviations from the plan, all from live tests: replies are checked against tool results (`brain.ungrounded`), safety
advice is enforced in code, one report per problem, acknowledgements get a short reply, slot filters (date/part),
several models per provider with a cooldown, Groq needs a User-Agent and nullable optional parameters, Upstash must sit
next to Vercel (us-east-1), `api.telegram.org` needs a VPN from some Pakistani connections (the deployed bot does not).

## 9. Tests (pytest, all network faked)
Registration normalisation; slots (Sunday, past, taken); store contract for SQLite and Redis (fake REST); full offline
driver flow reaching the manager; low risk not escalated; booking rules; demo mode on/off; rate limits; LLM path with a
fake client (tools per role, demo copy not sent to the model); LLM failure / budget → offline; driver privacy (cannot
read other vehicles or costs); plan_services and what_if numbers; Telegram, WhatsApp, app chat, jobs, health,
manager restriction, history. **Existing tests stay green.**

## 10. Definition of done
- Live demo: Telegram voice note "LEA-22-2030 ki brake se awaaz aa rahi hai" → safety advice + ISS id + risk → manager
  alert with buttons → "slot" → BK id → manager notified → event logged → morning brief arrives.
- The same flow in the Android app (voice in/out) and on WhatsApp (test number).
- All tests green; screenshots of each channel in `D:\Projects\_Screenshots\FleetLog-AI\` and the gallery; a clear list
  of what was verified live vs only in tests.
