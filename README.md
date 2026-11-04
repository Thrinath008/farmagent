# FarmAgent

An intelligent personal farming assistant. FarmAgent helps a farmer decide whether to irrigate, and
what the weather means for crop risk, by combining live weather, published agricultural guidance, a
deterministic decision engine, and Claude with real tool calling.

**The rule it is built around: FarmAgent never gives weather-dependent advice without first retrieving
and validating the weather.** Every figure on screen says where it came from: live, cached, simulated
or unavailable. If the weather cannot be retrieved, FarmAgent says so and gives no recommendation. It
never quietly substitutes made-up data.

> FarmAgent is decision support, not an agronomist. Its rules come from published guidance plus
> documented design choices, and have not been validated in field trials. It does not diagnose crop
> disease or prescribe chemicals.

## Status

| Area | State |
|---|---|
| Backend, rule engine, agent loop, frontend | Complete, with automated tests |
| Browser flows, including failure paths | Run against the production build, with mock upstream services |
| Real OpenWeatherMap calls | **Not yet run.** Needs an API key |
| Real Claude calls | **Not yet run.** Needs an API key. See [First run with real keys](#first-run-with-real-keys) |
| Supabase, Render and Vercel deployment | **Configured, not yet run.** Needs the accounts |
| GitHub Actions workflow | **Written, not yet run.** Its migration and test commands were run by hand |

### What needs credentials

| Without... | What happens |
|---|---|
| `OPENWEATHER_API_KEY` | Weather pages say live weather is not connected. Assessments return "insufficient information". The Scenario Lab still works |
| `ANTHROPIC_API_KEY` | The assistant and farm briefing say they are not connected. The Irrigation Advisor, Crop Health and Scenario Lab still work, using the rule engine |

## Features

- **Overview**: the day's conditions, irrigation status, crop risk, forecast and the crop's season.
- **AI Farming Assistant**: ask in your own words, watch which checks run, and get a structured answer
  with reasoning, confidence and what is still unknown.
- **Weather Intelligence**: current conditions and a 5-day forecast. Rain amount and rain chance are
  charted separately, because they mean different things.
- **Irrigation Advisor**: a decision ledger showing every factor weighed, and PAU's published
  irrigation windows laid out on the crop's real dates.
- **Crop Health & Risk**: whether the weather favours known problems, and what to scout for. Never a
  diagnosis, and never a chemical recommendation.
- **Scenario Lab**: two simulated weather patterns through the real engine, side by side, clearly
  labelled as simulated.
- **My Farm and Farming History**: farms, crops, and saved advice. Stored advice is labelled "Live at
  the time", because old weather is not current weather.

## Technology

| Layer | Stack |
|---|---|
| Frontend | React, Vite, TypeScript, Tailwind CSS, shadcn/ui, Lucide, Framer Motion, Recharts, React Router, TanStack Query, React Hook Form, Zod |
| Backend | Python 3.12, FastAPI, Pydantic, HTTPX, Uvicorn, SQLAlchemy, Alembic |
| Database | PostgreSQL (Supabase in production) |
| AI | Anthropic Python SDK, with native tool calling |
| Weather | OpenWeatherMap |
| Hosting | Vercel (frontend), Render (backend), Supabase (database) |

## Architecture

```text
Browser (React) ──HTTPS──► FastAPI ──► Claude tool-calling loop ──► tools
                              │                                       │
                              ├──► rule engine (pure Python) ◄────────┤
                              ├──► weather service ──► OpenWeatherMap │
                              └──► PostgreSQL                         │
```

Secrets stay on the server. Claude chooses tools and explains results, while irrigation status and
risk come from the deterministic engine. Full detail is in
[docs/architecture.md](docs/architecture.md).

## Installation

You need Python 3.12 or newer, Node 24 (the dependencies accept 22.22 or newer), and PostgreSQL. This
was developed on Python 3.12, Node 24 and PostgreSQL 15. The backend tests also pass on Python 3.13.

```bash
git clone <your-repository-url> farmagent
cd farmagent
cp .env.example .env
```

## Environment configuration

Edit `.env` in the repository root. The backend also reads `backend/.env`.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `OPENWEATHER_API_KEY` | For live weather | From [openweathermap.org/api](https://openweathermap.org/api). New keys can take a few hours to activate |
| `ANTHROPIC_API_KEY` | For the assistant | From [console.anthropic.com](https://console.anthropic.com) |
| `ANTHROPIC_MODEL` | No | Defaults to `claude-opus-5-5` |
| `FRONTEND_URL` | In production | The frontend's address, for CORS |
| `ENVIRONMENT` | No | `development`, `test`, `staging` or `production` |
| `TRUST_PROXY_HEADERS` | On Render | `true` behind a proxy that sets `X-Forwarded-For` |

`.env.example` lists every optional setting. The frontend has one setting, `VITE_API_URL`, used only
when deployed. **Never commit `.env`, and never put a key in a `VITE_` variable**, since those ship to
the browser.

## Database setup

Any PostgreSQL database works. For example, with Docker, which matches `.env.example`:

```bash
docker run --name farmagent-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=farmagent \
  -p 5432:5432 -d postgres:15
```

The backend steps below create the tables with `alembic upgrade head`.

## Backend startup

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Keep the first line as one command: if the virtual environment cannot be created, `pip` must not go on
to install into your system Python. If `python3.12` is not on your PATH, `uv venv --python 3.12` makes
an equivalent environment.

Check it at <http://localhost:8000/api/health>, which reports what is connected without revealing any
key. Interactive API docs are at <http://localhost:8000/docs>.

## Frontend startup

```bash
cd frontend
npm ci
npm run dev
```

Open the address Vite prints, normally <http://localhost:5173>. Vite proxies `/api` to port 8000, so
no other setup is needed. Set `API_PROXY_TARGET` if your backend runs elsewhere.

## API documentation

[docs/api.md](docs/api.md) covers every endpoint, the error envelope, provenance and the event stream.

## Testing

No test calls a live API. External services are mocked with deterministic fixtures. The backend
commands assume the virtual environment is active.

```bash
# Backend, on SQLite
cd backend
pytest -q
ruff check . && ruff format --check .

# Backend, on PostgreSQL
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/farmagent_test pytest -q

# Frontend
cd ../frontend
npm test
npm run typecheck
npm run lint
npm run build
```

`.github/workflows/ci.yml` runs all of these on each pull request and on each push to `main`.

### First run with real keys

Automated tests cannot prove the real services accept our requests, so check these once by hand:

1. `GET /api/health` shows `weather_configured` and `ai_configured` as `true`.
2. The Weather page shows **Live weather**. Refresh it, and the badge should stay live.
3. Ask the assistant "Should I irrigate my wheat today?". It should show a weather check running, and
   the answer should show the weather it used.
4. If the assistant fails with a request error, check the backend log first. Set
   `ANTHROPIC_ADAPTIVE_THINKING=false` if the chosen model does not accept that setting with tools and
   structured output.

## Deployment

### 1. Database: Supabase

1. Create a project.
2. In **Connect**, copy the **Session pooler** connection string. Render cannot reach Supabase's direct
   connection, which is IPv6-only on the default plan.
3. Keep it for `DATABASE_URL`. On Render, `render.yaml` runs the migrations before starting the API.

Row-level security is enabled on every table, with no policies, so Supabase's public Data API cannot
read them. The app connects as the database owner and is unaffected. No Supabase key is used in the
frontend.

### 2. Backend: Render

1. **New > Blueprint**, and select this repository. `render.yaml` defines the service.
2. Enter `DATABASE_URL`, `ANTHROPIC_API_KEY` and `OPENWEATHER_API_KEY` when asked.
3. Set `FRONTEND_URL` once you know the Vercel address.
4. Check `https://<service>.onrender.com/api/health`.

Render's free plan sleeps when idle, so the first request after a pause can take about a minute.

### 3. Frontend: Vercel

1. Import the repository, and set **Root Directory** to `frontend`.
2. Set `VITE_API_URL` to the Render address, with no trailing slash.
3. Deploy, then set Render's `FRONTEND_URL` to the Vercel address. For preview deployments, add their
   addresses to `EXTRA_CORS_ORIGINS`.

## Demonstration scenarios

The Scenario Lab at `/scenario-lab` needs no keys and no farm. Both scenarios run through the real
engine with the same wheat crop at the same stage, and the app labels all of it as simulated.

| | Scenario A: Rain expected | Scenario B: Hot and dry |
|---|---|---|
| Weather | 24 °C, 80% humidity | 36 °C, 30% humidity |
| Rain | 85% chance, 15 mm | 5% chance, 0 mm |
| Soil moisture | Not provided | Low |
| **Status** | **Caution** | **Favorable** |
| **Action** | **Consider postponing** | **Consider irrigating** |
| Rule score | −4 | +6 |
| Confidence | Limited, because soil moisture is unknown | Moderate |
| Main crop risk | Some favourable conditions for brown rust | Conditions favour early-season heat stress |

Why they differ, from the decision ledger:

- **A:** Meaningful rain is likely (−3), and mild, humid air keeps water use down (−1). Soil moisture
  is unknown, so FarmAgent asks the farmer to check it and says the decision also depends on how much
  rain actually falls.
- **B:** The farmer reported low soil moisture (+3), hot, dry air raises water use (+2), and no rain is
  forecast (+1). FarmAgent still says to confirm by checking the soil at root depth.

Tick "Also ask Claude" to have the real agent explain each one, using the same tools as live mode. It
needs an Anthropic key and uses API credits.

Suggested demo order:

1. Run the Scenario Lab, and read the ledger for each result.
2. With real keys, add a wheat farm in Punjab through onboarding, and open the Overview.
3. Ask the assistant "Should I irrigate my wheat field today?", and watch the checks run.
4. Change soil moisture in the Irrigation Advisor to see the assessment move.
5. Remove the weather key and restart, to show that FarmAgent refuses to guess.

## Deliberate decisions

Some choices differ from what you might assume. The reasons are in
[docs/architecture.md](docs/architecture.md#deliberate-decisions-and-limits).

- Tools take coordinates and fetch weather themselves, so the model cannot supply invented values.
- The assistant streams its checks and the validated final answer, not individual tokens.
- Sign-in is a guest session stored in the browser, not Supabase Auth.
- Growth stage is chosen by the farmer, never estimated from the sowing date.
- The UI is in English. The preferred language applies to assistant replies only.
- The rate limiter is in memory, so it suits one instance.

## Agricultural rules

[docs/agricultural-assumptions.md](docs/agricultural-assumptions.md) lists every rule, its source, what
is a design heuristic rather than a sourced value, and what was searched for and not found. The main
source is Punjab Agricultural University's Package of Practices, Rabi 2025-26, along with FAO-56.

Rules are implemented for **wheat in Punjab** only. Other crops can be recorded, but FarmAgent says it
has no crop-specific rules for them.
