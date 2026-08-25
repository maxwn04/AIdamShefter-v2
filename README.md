# AIdamShefter-v2

AI-powered fantasy football reporter. It refreshes Sleeper league data into a
durable PostgreSQL product database, maintains narrative memory, and writes
data-grounded articles through the reporter generation service.

## Setup

```bash
uv python install
uv sync --locked
corepack enable
corepack install --global pnpm@11.19.0
pnpm --dir frontend install --frozen-lockfile
```

`uv` reads `.python-version`, creates the project-local `.venv`, and installs
the exact dependency versions recorded in `uv.lock`. Copy `.env.example` to
`.env`, then provide at least:

```
SLEEPER_LEAGUE_ID=<league_id>
OPENAI_API_KEY=<key>
```

The checked-in database values are for the isolated local Compose service. Start
it and apply the current schema before starting the application:

```bash
docker compose -f compose.database.yml up --detach --wait
uv run --env-file .env alembic -c backend/migrations/alembic.ini upgrade head
```

The Compose database stores its data in a temporary filesystem and starts empty
after the service is recreated. It is intended for local development and release
review, not durable deployment.

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
uv run --env-file .env aidam-api
```

The server listens on `127.0.0.1:8000` by default. Override that with
`AIDAM_API_HOST` and `AIDAM_API_PORT`. Liveness is available at
`/health/live`; readiness at `/health/ready` also verifies the configured
database name, runtime role, and TLS policy.

Confirm both checks before opening the frontend:

```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
```

Submit a generation under
`/api/v1/generations/competitions/{competition_id}` to schedule it automatically.
The one-shot worker command remains available for manual execution and recovery:

```bash
uv run --env-file .env aidam-worker execute --competition-id <uuid> --generation-id <uuid>
uv run --env-file .env aidam-worker reconcile-stale --competition-id <uuid> \
  --stale-before 2026-08-23T09:00:00Z --limit 100
uv run --env-file .env aidam-worker reconcile-stale-refreshes \
  --competition-id <uuid> --stale-before 2026-08-23T09:00:00Z --limit 100
```

The initial API is single-local-user and does not claim durable per-user
ownership. Background dispatch runs in the API process with worker-scoped
dependencies and is not durable across a hard API-process failure. There is no
queue, lease, heartbeat, or automatic resume.

A hard process failure during a Sleeper refresh can likewise leave a refresh in
`running`. After confirming that no refresh process still owns the work, an
operator can run `reconcile-stale-refreshes` with an explicit timezone-aware
cutoff. The command does not refetch or resume work: it derives each terminal
status from the refresh plan and its latest durable API attempts, using a bounded
competition-scoped batch. Because refreshes do not have a lease or heartbeat,
this recovery is deliberately manual rather than age-triggered at API startup.

## Frontend

The local operator frontend lives under `frontend/` and requires Node.js
22.22.x plus pnpm 11.19.0. Keep the API command above running in one terminal,
then start Vite from a second terminal:

```bash
pnpm --dir frontend dev
```

Vite serves the application on `http://127.0.0.1:5173` and proxies `/api` and
`/health` to the local API. The default configuration needs no frontend `.env`.
To use a different local API port, copy `frontend/.env.example` to
`frontend/.env` and change `AIDAM_API_PROXY_TARGET`. Leave
`VITE_API_BASE_URL` blank so browser requests remain same-origin.

This initial release is supported only as a single-operator application bound
to loopback. FastAPI intentionally does not enable CORS, and the Vite development
server is the supported frontend serving path. Remote access, public deployment,
TLS termination, authentication, and production static-asset hosting require a
separate deployment design and are not supported by this release.

The committed TypeScript API contract is generated directly from FastAPI:

```bash
pnpm --dir frontend api:generate
pnpm --dir frontend api:check
```

Set `AIDAM_PYTHON` only when the generator cannot discover the repository's
Python virtual environment.

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
