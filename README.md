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
| Browser flows, including failure paths | Run against the production build, with mock upstream services. The main flows also ran on the dev server with live weather and Claude |
| Real OpenWeatherMap calls | **Tested** on the local dev server, through the whole app |
| Real Claude calls | **Tested** with `claude-haiku-5-5` on the local dev server, including tool calls and streaming. See [First run with real keys](#first-run-with-real-keys) |
| Vercel and Neon deployment | **Deployed** at <https://farmagent-eight.vercel.app>. Health, every main API route, streaming, rate limits and every page were checked on the live site |
| GitHub Actions workflow | **Tested.** Backend and frontend jobs pass, including the migration on PostgreSQL 17 |

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
| Database | PostgreSQL (Neon in production) |
| AI | Anthropic Python SDK, with native tool calling |
| Weather | OpenWeatherMap |
| Hosting | Vercel (frontend and API, one project with two services), Neon (database) |

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
was developed on Python 3.12 and Node 24. The backend tests also pass on Python 3.13, and on PostgreSQL
15 and 17. The Neon database runs 17.

```bash
git clone <your-repository-url> farmagent
cd farmagent
cp .env.example .env
```

If you have the code as a ZIP, skip the clone and start in the folder that holds this README. On
Windows, use `copy` instead of `cp`, and `.venv\Scripts\activate` in place of `source .venv/bin/activate`.

## Libraries and data

`requirements.txt` in the repository root lists the backend's Python libraries, and
`frontend/package.json` lists the frontend's. No dataset is used and no model is trained. Weather comes
live from OpenWeatherMap, and the crop rules are written in `backend/app/intelligence/`.

## Environment configuration

Edit `.env` in the repository root. The backend also reads `backend/.env`.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `OPENWEATHER_API_KEY` | For live weather | From [openweathermap.org/api](https://openweathermap.org/api). New keys can take a few hours to activate |
| `ANTHROPIC_API_KEY` | For the assistant | From [console.anthropic.com](https://console.anthropic.com) |
| `ANTHROPIC_MODEL` | No | Defaults to `claude-haiku-5-5` |
| `FRONTEND_URL` | In production | The frontend's address, for CORS |
| `ENVIRONMENT` | No | `development`, `test`, `staging` or `production` |
| `TRUST_PROXY_HEADERS` | On Vercel | `true` behind a proxy that sets `X-Forwarded-For`, as Vercel does |

`.env.example` lists every optional setting. The frontend has one optional setting, `VITE_API_URL`, for
an API on a different address. On Vercel the API shares the site's address, so it stays unset. **Never
commit `.env`, and never put a key in a `VITE_` variable**, since those ship to the browser.

## Database setup

Any PostgreSQL database works. For example, with Docker, which matches `.env.example`:

```bash
docker run --name farmagent-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=farmagent \
  -p 5432:5432 -d postgres:17
```

To run your own local cluster instead, `.pgdata/` is git-ignored for its data. Point `DATABASE_URL` at its
port. SQLite will not work, because the migration enables row-level security.

The backend steps below create the tables with `alembic upgrade head`.

## Backend startup

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

With conda, run this from the repository root instead of the first three lines. It installs the
requirements too:

```bash
conda env create -f backend/environment.yml
conda activate farmagent
cd backend
```

For the venv route, keep the first line as one command: if the virtual environment cannot be created, `pip` must not go on
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
4. If the assistant fails with a request error, check the backend log first. It also records the
   tokens used by each model call.

## Deployment

FarmAgent runs as one Vercel project with two services, defined in `vercel.json`: the Vite frontend,
and the FastAPI backend, which receives every request under `/api`. The database is on Neon. Both run
in Singapore (Vercel `sin1`, Neon `aws-ap-southeast-1`), close to each other and to users in India.

The live site is <https://farmagent-eight.vercel.app>.

### 1. Database: Neon

1. Create a Neon project with PostgreSQL 17, in AWS Asia Pacific (Singapore).
2. Copy two connection strings: the pooled one, whose host contains `-pooler`, for the app, and the
   direct one for migrations.
3. Create the tables from your machine, using the direct string:

   ```bash
   cd backend
   DATABASE_URL='<direct connection string>' alembic upgrade head
   ```

   Run this again whenever a migration is added. Vercel does not run migrations.

Row-level security is enabled on every table, with no policies. The app connects as the database
owner, which bypasses it, so the app is unaffected.

### 2. Frontend and API: Vercel

1. Install the CLI (`npm i -g vercel`, or put `npx` before each command), then run `vercel login`, and
   `vercel link` in the repository root.
2. Add these settings for Production, for example `vercel env add ANTHROPIC_API_KEY production
   --sensitive`, which asks for the value:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Neon's pooled connection string |
   | `ANTHROPIC_API_KEY`, `OPENWEATHER_API_KEY` | Your keys |
   | `ANTHROPIC_MODEL` | `claude-haiku-5-5` |
   | `ENVIRONMENT` | `production` |
   | `TRUST_PROXY_HEADERS` | `true` |
   | `FRONTEND_URL` | The site's production address |

3. Run `vercel deploy --prod`, then open `/api/health` on the new address.

`.vercelignore` keeps `.env`, the local database and the tests out of the upload. Vercel installs the
backend's libraries from `backend/pyproject.toml`, so it must list the same libraries as
`requirements.txt`. A backend test checks that.

The project is also connected to the GitHub repository, so each push to `main` deploys to production.
Preview deployments only get these settings if you add them for Preview as well.

The site is public, and every assistant answer uses the Anthropic account's credits. The per-client
rate limits stop bursts, but a spending limit in the Anthropic console is the real cap.

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
- Sign-in is a guest session stored in the browser, not an account with a password.
- Growth stage is chosen by the farmer, never estimated from the sowing date.
- The UI is in English. The preferred language applies to assistant replies only.
- The rate limiter is in memory. On Vercel each instance keeps its own count, so limits are approximate.

## Agricultural rules

[docs/agricultural-assumptions.md](docs/agricultural-assumptions.md) lists every rule, its source, what
is a design heuristic rather than a sourced value, and what was searched for and not found. The main
source is Punjab Agricultural University's Package of Practices, Rabi 2025-26, along with FAO-56.

Rules are implemented for **wheat in Punjab** only. Other crops can be recorded, but FarmAgent says it
has no crop-specific rules for them.
