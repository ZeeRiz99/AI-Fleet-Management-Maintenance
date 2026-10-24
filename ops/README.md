# FleetLog AI — AI Fleet Log Assistant (`ops/`)

A driver + manager agent on top of this repo's breakdown-risk model. Drivers talk to it on Telegram, WhatsApp or in
the Android app (Roman Urdu / Urdu / English, text or voice); managers get alerts with buttons and a morning brief.
Spec and decisions: [docs/fleetlog-ai/SPEC.md](../docs/fleetlog-ai/SPEC.md).

Live demo: [t.me/zeeriz_bot](https://t.me/zeeriz_bot) · health: https://fleetlog-ai.vercel.app/health

## How it works

```
Telegram / WhatsApp / app ──> ops/web.py (FastAPI on Vercel) ──> ops/brain.py (LangGraph)
                                                                   guard ─> identify ─> agent (LLM + tools) ─> finalize
                                                                                     └> offline (keyword router + same tools)
tools (ops/tools_driver.py, ops/tools_manager.py) ──> risk model output (alerts.csv, fleet.db) + store (Upstash Redis)
ops/channels.py delivers alerts to every channel · ops/jobs.py runs the morning brief (Vercel Cron)
```

| Module | Role |
|---|---|
| `brain.py` | entry point `handle(user_id, text)`: rate limits, commands (`driver <REG>`, `manager`, `brief`, `reset`), LLM agent with role-scoped tools, offline fallback, demo copy of manager alerts, history |
| `issue_flow.py` | LangGraph issue workflow: understand → assess risk → decide (escalate?) → record → notify |
| `tools_driver.py` / `tools_manager.py` | the only way the agent touches data; roles are enforced in `core.run_tool` |
| `llm.py` / `speech.py` | provider chains (Gemini → Groq; several models each; a failing model rests 2 min) |
| `router.py` | offline keyword router: the bot still works with no key or no quota |
| `store.py` | Upstash Redis (REST) or SQLite, same interface; atomic slot locks |
| `telegram.py` / `whatsapp.py` / `channels.py` | channels and delivery |
| `web.py` | `/health`, `/webhooks/telegram`, `/webhooks/whatsapp`, `/api/chat` (app), `/cron/morning` |
| `jobs.py` | daily brief + reminders, idempotent per day |
| `vercel_bundle.py` / `setup_telegram.py` | deployment and bot setup commands |

### Guards (each one comes from a live test)

* A reply that claims "booked / reported / approved" without the matching tool, or contains numbers no tool returned,
  is rejected and the offline router answers with real tools (`brain.ungrounded`).
* If the LLM fails after a tool ran, the reply is built from the tool results, so nothing runs twice.
* Safety advice always leads the reply, never twice; one report per problem per 30 minutes; acknowledgements
  ("haan", "ok", 👍) get a short reply.
* A driver only sees their own vehicle; manager buttons only work for managers.

## Run locally

```powershell
pip install -r requirements-ops.txt                 # pandas, numpy, langgraph, fastapi, uvicorn
copy .env.example .env                              # then fill in keys (never commit .env)
python -m pytest tests/test_ops.py tests/test_telegram.py tests/test_jobs.py tests/test_whatsapp.py tests/test_deploy.py
uvicorn ops.web:app --port 8100                     # web app (set PYTHONPATH=src)
python -m ops.setup_telegram poll                   # Telegram bot from the laptop, no webhook needed
python -m ops.jobs morning                          # send today's brief once
```

`api.telegram.org` is blocked on some Pakistani connections: the laptop then needs a VPN for `poll`, `set` and `info`.
The deployed bot on Vercel is not affected.

## Configuration

All settings are environment variables; [`.env.example`](../.env.example) lists every one with a comment. `ops/env.py`
loads `.env` (quotes allowed) without overriding variables the host already set.

| Needed for | Variables |
|---|---|
| AI | `GEMINI_API_KEY` ([AI Studio](https://aistudio.google.com/apikey)), `GROQ_API_KEY` ([Groq](https://console.groq.com)); models in `OPS_GEMINI_MODEL`, `OPS_GROQ_MODEL` (comma-separated, tried in order) |
| Telegram | `TELEGRAM_BOT_TOKEN` (@BotFather), `TELEGRAM_WEBHOOK_SECRET` (`python -m ops.setup_telegram secret`) |
| Store | `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` (REST, not read-only); without them: SQLite |
| App chat | `OPS_APP_KEY` (same value as `fleetlog.appKey` in `android/local.properties`) |
| Brief | `CRON_SECRET`, `OPS_BRIEF_HOUR_PKT` (default 8) |
| WhatsApp | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_MANAGER_NUMBERS`, optional `WHATSAPP_ALERT_TEMPLATE` |
| Client mode | `OPS_DEMO_MODE=0` (no demo copy), `OPS_RESTRICT_MANAGER=1` + `TELEGRAM_MANAGER_CHAT_IDS` / `WHATSAPP_MANAGER_NUMBERS` |

## Deploy (Vercel + Upstash, free tiers)

1. Upstash: create a Redis database in **us-east-1** (next to Vercel's default region; every message makes 20–40 store
   calls), copy the REST URL and token into `.env`.
2. Vercel, once: `npx vercel@63.1.2 login`, then `python -m ops.vercel_bundle` and
   `cd build/vercel && npx vercel@63.1.2 link --yes --project fleetlog-ai`.
3. `python -m ops.vercel_bundle --push-env` copies the settings from `.env` (values go through the CLI's stdin).
4. `python -m ops.vercel_bundle --deploy` builds `build/vercel` and deploys; it refuses unless the folder is linked to
   `fleetlog-ai`. Check `https://<project>.vercel.app/health`: `store_persistent` must be `true`.
5. `python -m ops.setup_telegram set https://<project>.vercel.app` points the bot at Vercel.

The bundle (`build/vercel`, git-ignored, ~12 MB) holds `ops/`, three `src/` modules and the demo data; `.env` and the
CLI's `.env.local` are never uploaded. Settings changes need a redeploy.

## WhatsApp (built, not yet live-tested)

developers.facebook.com → create an app → add WhatsApp → API Setup: copy the access token and phone number ID; app
secret from App settings → Basic. Webhook URL `https://<project>.vercel.app/webhooks/whatsapp`, verify token =
`WHATSAPP_VERIFY_TOKEN`, subscribe to `messages`. Add your number as a test recipient. Free-form messages reach a user
only within 24 hours of their last message; alerts outside that window need an approved template
(`WHATSAPP_ALERT_TEMPLATE`, one body variable).

## Free-tier limits (checked 22 Oct 2026)

| Service | Limit that matters |
|---|---|
| Vercel Hobby | 300 s per request, 1M invocations and 4 h active CPU per month; cron once a day, ±59 min, may fire twice (the brief is idempotent); **non-commercial use only** |
| Upstash free | 500K commands per month, 256 MB: roughly 400–800 messages a day |
| Gemini free | busy models answer 503 often; two models are configured and a failing one rests |
| Groq free | 8,000 tokens/minute per model (about 2–3 agent messages a minute); blocked from VPN/datacenter IPs |
| Telegram | free; WhatsApp: business-initiated messages need templates and Meta's pricing |

A client deployment: Vercel Pro (commercial use, per-minute cron), a paid LLM key, WhatsApp templates approved.

## Honest notes

* Vehicle risk, fuel suspects and savings come from the **simulated fleet scored as of 1 Jan 2026**; issues, bookings,
  fuel logs and shifts reported through the bot are live. Workshops are demo entries.
* Live-tested (22–24 Oct 2026): Gemini and Groq agent, voice notes, the Telegram bot on the laptop and on Vercel, the
  brief, the store on Upstash. Not live-tested yet: WhatsApp, the app's chat screen on a phone.
* LLM answers vary; the guards above catch the failure modes seen so far, not every possible one.
* Demo mode shows the manager's alert to the reporter so one visitor can try the whole flow; switch it off for clients.

## Tests

`tests/test_ops.py` (agent, workflow, booking rules, guards), `test_telegram.py`, `test_whatsapp.py`, `test_jobs.py`,
`test_deploy.py`: 120+ tests, all offline with fakes (no network, no keys). Android: `AssistantContractTest` parses a
real `/api/chat` response.
