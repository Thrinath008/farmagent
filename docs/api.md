# API reference

Base path `/api`. JSON everywhere except the event stream. FastAPI also serves interactive docs at
`/docs` and the OpenAPI schema at `/openapi.json`. The exact shapes are in
`backend/app/schemas/api.py` and `backend/app/schemas/weather.py`, mirrored in
`frontend/src/types/api.ts`.

## Conventions

**Authentication.** Guest sessions. `POST /api/session/guest` returns a token once; send it as
`X-Guest-Token`. The server stores only a hash. Weather, crops, scenarios and health need no token.

**Errors.** Every error uses one envelope, and never includes internal exception text or secrets:

```json
{
  "error": {
    "code": "weather_unavailable",
    "message": "Live weather could not be retrieved.",
    "request_id": "f83b00d0...",
    "fields": [{ "field": "latitude", "problem": "..." }]
  }
}
```

`fields` appears only on validation errors.

| Code | Status | Meaning |
|---|---|---|
| `bad_request` | 400 | The request cannot be used |
| `unauthorized` | 401 | Missing or unknown guest token |
| `not_found`, `location_not_found` | 404 | No such record or place |
| `validation_error` | 422 | Fields failed validation |
| `rate_limited` | 429 | Too many requests. See `Retry-After` |
| `internal_error` | 500 | Unexpected failure |
| `weather_not_configured` | 503 | No OpenWeatherMap key on the server |
| `weather_auth_failed` | 503 | The provider rejected the key |
| `weather_rate_limited` | 503 | The provider is limiting requests |
| `weather_unavailable` | 503 | The provider failed or timed out |
| `weather_data_invalid` | 502 | The provider's response failed validation |
| `agent_not_configured` | 503 | No Anthropic key on the server |
| `agent_auth_failed`, `agent_rate_limited`, `agent_unavailable` | 503 | Claude could not answer |
| `agent_timeout` | 504 | The agent ran past its total time limit |
| `database_unavailable` | 503 | The database cannot be reached |

**Rate limits**, per client per minute, by default: 120 overall, 12 for `/api/agent/*` and
`/api/scenarios/*`, 10 for `/api/session/guest`. `/api/health` is exempt. The limiter is per process.

**Weather provenance.** Every weather payload carries `meta`:

```json
{
  "provenance": "live | cached | simulated | unavailable",
  "source": "OpenWeatherMap",
  "observed_at": "2026-11-05T02:00:00Z",
  "fetched_at": "2026-11-05T02:05:00Z",
  "age_seconds": 300,
  "is_stale": false,
  "warning": null
}
```

`live` means the provider answered during this request. Within the cache TTL the server returns
`cached`. If the provider fails and a recent cached copy exists, the response is `cached` with a
`warning`. If none exists, the request fails. Simulated data is never used as a fallback.

## System

### `GET /api/health`

Always answers 200 while the process is up, and reports what is connected. No secret is ever
included.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "database": "ok",
  "weather_configured": true,
  "ai_configured": true,
  "ai_model": "claude-haiku-5-5"
}
```

`status` is `degraded` when the database is unavailable.

### `GET /api/crops`

Crop catalogue, support levels, stages, sources, and the valid soil, method and unit values.

## Session

| Method and path | Purpose |
|---|---|
| `POST /api/session/guest` | Create a guest. Returns `{ token, user }`. 201 |
| `GET /api/session/me` | The current guest |
| `PATCH /api/session/me` | Update `display_name`, `preferred_language` |
| `DELETE /api/session/me` | Delete the guest and all their data. 204 |

## Weather

Coordinates are validated: latitude -90 to 90, longitude -180 to 180.

| Method and path | Query | Purpose |
|---|---|---|
| `GET /api/weather/current` | `lat`, `lon`, `refresh` | Current conditions |
| `GET /api/weather/forecast` | `lat`, `lon`, `refresh`, `hours` (3 to 120, default 120) | Three-hourly and daily forecast |
| `GET /api/weather/geocode` | `q`, or `lat` and `lon` | Search for a place, or reverse-geocode |

`refresh=true` bypasses the cache and asks the provider.

Rain fields are always separate: `rain_mm` and `rain_probability_pct` for a period,
`rain_total_mm` and `rain_probability_max_pct` for a day. A null `rain_last_1h_mm` means the provider
reported no rain field, not a measured zero.

## Farms

Unknown values stay `null`. Nothing is filled in on the farmer's behalf.

| Method and path | Purpose |
|---|---|
| `GET /api/farms` | List farms, with crops and irrigation schedules |
| `POST /api/farms` | Create. All fields optional. 201 |
| `GET`, `PATCH`, `DELETE /api/farms/{id}` | Read, update, delete |
| `POST /api/farms/{id}/crops` | Add a crop. `crop` required. 201 |
| `PATCH`, `DELETE /api/farms/{id}/crops/{crop_id}` | Update or remove a crop |

`irrigation_schedule` on a crop is `null` when the sowing date is missing or outside PAU's published
windows.

## Assessments

The server retrieves the weather itself. A client cannot supply weather values.

### `POST /api/irrigation/assess`

```json
{
  "farm_id": "uuid or null",
  "farm_crop_id": "uuid or null",
  "latitude": null,
  "longitude": null,
  "crop": "wheat",
  "growth_stage": "tillering",
  "soil_type": "loam",
  "soil_moisture": "low | adequate | high | unknown",
  "irrigation_method": "border",
  "recent_rainfall_mm": null,
  "sowing_date": "2026-11-01",
  "force_refresh": false
}
```

Give either a farm or coordinates. Returns:

```json
{
  "assessment": { "status": "...", "action": "...", "factors": [], "score": -1, "...": "..." },
  "advice": { "recommendation": "...", "weather_context": {}, "...": "..." },
  "weather": { "provenance": "live", "...": "..." },
  "weather_issues": [],
  "farm_id": "uuid"
}
```

**A weather failure is still a 200.** The assessment says `insufficient_information`,
`advice.recommendation` is null, `weather` is null, and `weather_issues` says why, with each distinct
reason listed once. An assessment that could not use the weather is a valid answer, not a server
error.

`status`: `favorable`, `monitor`, `caution`, `insufficient_information`.
`action`: `consider_irrigating`, `consider_postponing`, `check_soil_and_reassess`,
`hold_irrigation`, `cannot_assess`.

### `POST /api/pest-risk/assess`

Takes the same target fields, without soil and method. Returns the same outer shape, with
`overall_classification` of `low`, `moderate`, `elevated` or `uncertain`, a list of `risks`, and a
`disclaimer` that this is not a diagnosis.

## Agent

Each requires a guest token and an Anthropic key on the server.

### `POST /api/agent/chat`

```json
{ "message": "Should I irrigate today?", "conversation_id": null, "farm_id": "uuid" }
```

Returns `{ conversation_id, message_id, advice, tool_log, saved_recommendation_ids }`.

`advice` is the structured answer: `intent`, `recommendation`, `summary`, `reasoning`,
`weather_context`, `risk_level`, `confidence`, `missing_information`, `next_steps`, `data_sources`,
`requires_expert_verification`, `generated_by`.

`weather_context` is filled by the server from the tools that actually ran. The model cannot supply
it.

### `POST /api/agent/chat/stream`

Same request. Responds with `text/event-stream`, one JSON object per `data:` frame:

```text
data: {"type":"status","stage":"thinking","iteration":1}
data: {"type":"tool_start","id":"toolu_1","name":"assess_irrigation_need"}
data: {"type":"tool_end","id":"toolu_1","name":"assess_irrigation_need","ok":true,"duration_ms":412,"error_code":null,"provenance":"live"}
data: {"type":"final","response":{ "...": "same as /agent/chat" }}
```

A failure arrives as `{"type":"error","code":"agent_unavailable","message":"..."}`. Failed runs store
nothing, so a retry cannot duplicate the exchange.

The stream carries agent events and the validated final answer, not model tokens. See
[architecture.md](architecture.md#why-the-answer-is-not-streamed-token-by-token).

### `POST /api/agent/analyze`

A proactive briefing. `{ "farm_id": "uuid", "farm_crop_id": "uuid or null", "focus": "optional" }`.
Returns `{ advice, tool_log }`.

## Conversations

| Method and path | Purpose |
|---|---|
| `GET /api/conversations` | List |
| `POST /api/conversations` | Create |
| `GET`, `DELETE /api/conversations/{id}` | Read with messages, or delete |

## Recommendations (Farming History)

| Method and path | Purpose |
|---|---|
| `GET /api/recommendations` | Query: `limit` (1 to 200, default 50), `farm_id`, `intent` |
| `POST /api/recommendations` | Save advice. `origin`: `assistant`, `irrigation_advisor`, `crop_health`, `scenario_lab` |
| `DELETE /api/recommendations/{id}` | Delete. 204 |

## Scenario Lab

No token needed. All weather here is simulated and labelled as such.

| Method and path | Purpose |
|---|---|
| `GET /api/scenarios` | The two fixed scenarios |
| `POST /api/scenarios/run` | `{ "include_ai": false, "scenario_ids": ["A", "B"] }`. Runs them through the real engine and compares them. `scenario_ids` defaults to both. `include_ai: true` also runs the real agent, and needs an Anthropic key |

If Claude fails, the run still succeeds, and each result's `ai.status` is `unavailable`.
