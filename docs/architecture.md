# Architecture

## System overview

```text
                     Browser (React, Vercel)
                              │  HTTPS, X-Guest-Token. No API keys ever reach here.
                              ▼
                     FastAPI (Render)
      ┌───────────────────────┼─────────────────────────┐
      │                       │                         │
  api/ routers          agents/farm_agent          middleware
      │                 Claude tool-calling loop    request id, rate limit,
      │                       │                     safe errors, CORS
      │                 tools/registry
      │                       │
      ├───────────┬───────────┘
      ▼           ▼
 services/     intelligence/
 weather       rule engine: irrigation, pest_risk, crops, confidence
 farms, etc.   Pure functions over validated data. No I/O.
      │
      ├── OpenWeatherMap (server side only)
      ├── Anthropic API (server side only)
      └── PostgreSQL (Supabase): farms, conversations, history, weather cache
```

## Principles

**Weather first, or no advice.** Weather-dependent advice requires weather that was retrieved and
validated during that request's chain. This is enforced by code at three levels (see
[Enforcement](#how-weather-first-is-enforced)), not just by the prompt.

**The engine decides, Claude explains.** Irrigation status and risk come from a deterministic Python
engine. Claude chooses tools and explains results in plain language, and is told not to overrule the
engine.

**Provenance travels with the data.** Every weather value carries `live`, `cached`, `simulated` or
`unavailable` from the provider layer to the screen.

**Unknown stays unknown.** Missing values are `null` in the database and "—" on screen. A missing
reading never looks like a measured zero.

## Repository layout

```text
backend/app/
  api/            HTTP routers, dependencies
  agents/         Claude loop, prompts, output schema
  tools/          Tool definitions, registry, WeatherLedger
  services/       OpenWeatherMap client, weather cache, farms, conversations, scenarios
  intelligence/   Rule engine. No network or database access
    crops/        One module per crop. Adding a crop means adding a profile here
  models/         SQLAlchemy tables
  schemas/        Pydantic API and weather models
  database/       Engine, sessions, UTC column type
  core/           Settings, errors, middleware, text helpers
backend/alembic/  Migrations
backend/tests/    Pytest, with mocked HTTP. No test reaches a live API

frontend/src/
  features/       One folder per page
  components/     Shared UI: provenance, decision ledger, season strip, charts, states
  components/ui/  shadcn/ui primitives
  services/api.ts The only module that talks to the backend
  hooks/          TanStack Query hooks
  providers/      Selected farm and crop
  lib/            Formatting and labels
  types/          API contract, mirroring backend/app/schemas
  test/           Fixtures, a route-table fetch mock, render helpers
```

## Data flow: a question to the assistant

1. The farmer sends a question. `AssistantPage` calls `POST /api/agent/chat/stream`.
2. The router loads the guest's farm and builds a context block: stored details only, marked as data.
3. `FarmAgent.run` calls Claude with the system prompt, history, tools, and a JSON schema for the final
   answer. The stable prompt sits behind a cache breakpoint.
4. Claude responds with `tool_use`. For each call, the registry validates the arguments, runs the tool
   in the backend, and records the result. The browser receives `tool_start` and `tool_end` events.
5. A weather tool goes through `WeatherService`, then the cache or provider. Validated weather goes
   into the turn's `WeatherLedger`.
6. Tool results go back to Claude, which may ask for more.
7. When Claude ends the turn, its answer is parsed against the schema and checked against the rules
   below. If it fails, Claude gets up to two chances to correct it. If it still fails, the server replaces
   it with a safe answer.
8. The server attaches `weather_context` from the ledger and stores the exchange. Failed runs store
   nothing.
9. The browser receives `final`, loads the stored exchange, and shows it with its provenance.

## Claude integration

- Official Anthropic Python SDK, with a manual loop rather than a tool runner, because the loop has
  to enforce budgets and inspect results.
- Default model `claude-opus-5-5`, set by `ANTHROPIC_MODEL`. Adaptive thinking is on by default
  (`ANTHROPIC_ADAPTIVE_THINKING`).
- Final answers use `output_config.format` with a JSON schema.
- Seven tools: `get_current_weather`, `get_weather_forecast`, `get_crop_information`,
  `assess_irrigation_need`, `assess_weather_pest_risk`, `get_location_information`,
  `save_recommendation`.

Guard rails:

| Limit | Default | When reached |
|---|---|---|
| Iterations | 6 | The last call has `tool_choice: none`, so Claude has to answer |
| Tool calls | 8 | Further calls get a "budget exhausted" result |
| Total time | 150 s | The turn fails with `agent_timeout` |
| Message length | 4000 characters | Rejected |
| History | 20 messages | Older ones are not sent |

Tool errors are returned to Claude as `is_error` results, so it can explain them. Farm details, farmer
messages and tool results are marked as data, and instructions inside them are not followed.

### How weather first is enforced

1. **Tools take coordinates, not weather.** `assess_irrigation_need` and `assess_weather_pest_risk`
   fetch weather themselves. The model has no way to feed in invented values. The spec suggested
   passing weather values to these tools. This is a deliberate change, because it removes that risk
   entirely.
2. **The ledger.** `WeatherLedger` records what validated weather this turn actually retrieved.
   `weather_context` in the answer comes from the ledger, not from the model.
3. **The final check.** A weather-dependent answer with no verified weather is sent back for
   correction. If weather tools were tried and failed, `recommendation` is forced to null, and
   confidence and risk are lowered. An answer containing a dosage is also rejected, and if it is not
   corrected the server removes the advice.

### Why the answer is not streamed token by token

The stream carries agent events and the validated final answer, not model tokens. Streaming tokens
would show the farmer text that the final check might still reject, such as advice without verified
weather, or a dose. What the farmer sees live is the honest part: which checks are running and what
they returned.

## Weather service

`services/openweather.py` is the only code that calls OpenWeatherMap. It validates each response
against strict Pydantic models. Implausible or malformed data raises `WeatherDataInvalidError` and is
not used. The API key stays out of logs and errors: a failed request logs only the exception type and
path, because an HTTP exception's message can contain the URL, and the URL carries the key.

`services/weather.py` adds the cache and provenance:

| Situation | Result |
|---|---|
| Within TTL (current 10 min, forecast 30 min) | `cached` |
| Expired or `refresh=true`, provider answers | `live` |
| Provider fails, cached copy under 6 h old | `cached`, flagged stale if expired, with a warning |
| Provider fails, no usable cache | Error. **Never simulated data** |
| Observation over 3 h old | `is_stale: true`, which lowers confidence and blocks "favorable" |
| No API key | `weather_not_configured` |

Retries with backoff cover connection failures, timeouts, 429 and 5xx responses, but not 401s. Simulated weather enters only
through `SimulatedWeatherProvider`, which only the Scenario Lab can reach.

## The rule engine

`intelligence/` has no network or database access, so it is easy to test and reason about. See
[agricultural-assumptions.md](agricultural-assumptions.md) for every rule. A crop is a `CropProfile`
of stages, threat rules and sources. Adding one does not change the engine.

## Scenario Lab

Two fixed scenarios go through the same `assess_irrigation` and `assess_pest_risk` functions as live
data, and optionally the real agent loop, by swapping the weather provider. There are no canned
answers. Results are labelled `simulated` from the provider through to the page.

## Data model

```text
users ──< farms ──< farm_crops
users ──< conversations ──< messages
users ──< recommendations
weather_cache (keyed by rounded coordinates and kind)
```

Conversations and recommendations belong to the user. Their link to a farm is optional, and is cleared
rather than cascaded when the farm is deleted, so history survives. Recommendations can also link to
the conversation they came from.

Migrations are in `backend/alembic/versions`. Every table has row-level security enabled with no
policies. The app connects as the database owner, which bypasses RLS, so this closes Supabase's
auto-generated Data API to these tables without affecting the app.

## Security

- API keys exist only on the server, read from the environment. Nothing in `frontend/` knows them.
- Guest tokens are random, shown once, and stored hashed. Every query is scoped to the guest's id.
- Errors use one envelope with a request id. Internal exception text is never returned.
- Input is validated by Pydantic. Queries are parameterized through SQLAlchemy.
- Per-client rate limits. `TRUST_PROXY_HEADERS` controls whether `X-Forwarded-For` is believed.
- CORS allows only `FRONTEND_URL` and `EXTRA_CORS_ORIGINS`, plus `localhost:5173` in development and
  test.
- The rate limiter is in memory and per process. Several instances would each keep their own count.
  This suits a single small instance. Scaling out needs a shared store.

## Frontend

React 19 with React Router and TanStack Query. Pages load lazily inside a `Suspense` boundary in
`AppShell`, so the sidebar stays mounted and live while a page's code loads.

Choices that protect honesty:

- `ProvenanceBadge` is the only way weather is labelled. It has a `historical` mode, so stored advice
  says "Live at the time" rather than "Live weather".
- `displayMeta` downgrades data to cached and out of date when a refresh fails.
- Weather queries re-request every 10 minutes. Within the TTL the server says `cached`, so an old
  response cannot keep its live label.
- `retry: false`, so failures appear with a retry button instead of being retried out of sight.
- Forecast times use the farm's timezone offset, not the browser's.
- Rain amount and rain chance are separate charts, each with one axis. A 90% chance of 0.2 mm and a
  30% chance of 25 mm are very different days, and a shared chart invites reading one as the other.

## Deliberate decisions and limits

| Decision | Reason |
|---|---|
| Guest sessions, not Supabase Auth | A farmer can start at once. The cost: clearing browser data loses access to that profile |
| Growth stage is selected, never estimated | No verified Punjab stage-by-day table was found |
| UI is in English. Preferred language applies to assistant replies | Translating agricultural guidance needs review by someone who knows the terms |
| Wheat only | The spec says not to claim crop support before the rules exist |
| No live test against real providers in CI | Tests use mocked responses by design, and CI has no keys |
| Tools fetch weather themselves, rather than receiving values as the spec suggested | See [How weather first is enforced](#how-weather-first-is-enforced) |
| Agent events and a validated answer are streamed, not tokens | See [Why the answer is not streamed token by token](#why-the-answer-is-not-streamed-token-by-token) |
