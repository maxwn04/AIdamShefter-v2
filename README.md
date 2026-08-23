# AIdamShefter-v2

AI-powered fantasy football reporter. Fetches Sleeper league data, loads it into
an in-memory SQLite database, uses persistent reporter memory for narrative
continuity, and writes data-grounded articles with the reporter v2 runner.

## Setup

```bash
uv python install
uv sync
```

`uv` reads `.python-version`, creates the project-local `.venv`, and installs
the exact dependency versions recorded in `uv.lock`. Copy `.env.example` to
`.env`, then provide at least:

```
SLEEPER_LEAGUE_ID=<league_id>
OPENAI_API_KEY=<key>
```

## Quick Start

```bash
# Datalayer CLI
uv run sleeperdl app                                          # Interactive query shell
uv run sleeperdl load-export --output out.sqlite

# Reporter CLI
uv run reporter-v2 "weekly recap" --week 8                    # Natural language request
uv run reporter-v2 "snarky recap, roast Team Taco" --week 8   # With week and style hints
uv run reporter-v2 "power rankings with analysis" --week 8    # Any article type
uv run reporter-v2 "deep dive on Team Taco's season" --week 8 # Team-focused
```

## API Server

The product API exposes process health, canonical memory, and the polling-oriented
generation boundary. Generation submission creates a pending row and schedules
worker-scoped execution as a FastAPI background task after sending the response.

```bash
export AIDAM_DATABASE_URL=postgresql+psycopg://aidam_api:password@localhost/aidam
export AIDAM_DATABASE_REQUIRE_TLS=false  # isolated local PostgreSQL only
uv run aidam-api
```

The server listens on `127.0.0.1:8000` by default. Override that with
`AIDAM_API_HOST` and `AIDAM_API_PORT`. Liveness is available at
`/health/live`; readiness at `/health/ready` also verifies the configured
database name, runtime role, and TLS policy.

Submit a generation under
`/api/v1/generations/competitions/{competition_id}` to schedule it automatically.
The one-shot worker command remains available for manual execution and recovery:

```bash
export AIDAM_WORKER_DATABASE_URL=postgresql+psycopg://aidam_worker:password@localhost/aidam
uv run aidam-worker execute --competition-id <uuid> --generation-id <uuid>
uv run aidam-worker reconcile-stale --competition-id <uuid> \
  --stale-before 2026-08-23T09:00:00Z --limit 100
```

The initial API is single-local-user and does not claim durable per-user
ownership. Background dispatch runs in the API process with worker-scoped
dependencies and is not durable across a hard API-process failure. There is no
queue, lease, heartbeat, or automatic resume.

## Tests

```bash
uv run pytest                                  # All tests
uv run pytest datalayer/tests/                 # Datalayer tests only
uv run pytest reporter_memory/tests/           # Reporter memory tests only
uv run pytest reporter_v2/tests/               # Reporter v2 tests only
uv run pytest backend/tests/api/               # API boundary tests only
uv run pytest backend/tests/worker/            # Worker boundary tests only
uv run pytest datalayer/tests/unit/            # Datalayer unit tests
uv run pytest datalayer/tests/integration/     # Datalayer integration tests
```

## Project Structure

```
datalayer/          # Sleeper API data layer
  sleeper_data/     # Core: fetch, normalize, store, query
  tools.py          # OpenAI function-calling tool definitions
  tests/            # Datalayer tests + fixtures
  cli/              # sleeperdl CLI

reporter_memory/    # Persistent narrative memory for reporter-generated context
  schema.py         # SCHEMA_VERSION + DDL (schema 3)
  context_store.py  # ContextStore facade
  store/            # Persistence mixins (storylines, events, triggers, FTS)
  search/           # Search pipeline, ranking, verification planning
  context_tools.py  # Legacy-style memory tool handlers for integrations

reporter_v2/        # Supported AI reporter agent
  runner/           # Single-loop runner and tools
  app/              # CLI runner and config
  prompts/          # System prompt
  procedures/       # Procedure files loaded by the runner
  tests/            # Reporter v2 tests
```

## Memory Refactor Notes

- Persistent memory lives in `reporter_memory/`, not `datalayer/`.
- `.data/context.db` uses reporter memory schema `3`.
- Storyline IDs are scoped by `(league_id, season, id)`.
- `sleeperdl context` and `sleeperdl memory` have been removed.
- The installed reporter CLI is `reporter-v2`.

See `AGENTS.md` and the docs under `reporter_v2/docs/` for architecture details.
