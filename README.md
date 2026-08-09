# AIdamShefter-v2

AI-powered fantasy football reporter. Fetches Sleeper league data, loads it into
an in-memory SQLite database, uses persistent reporter memory for narrative
continuity, and writes data-grounded articles with the reporter v2 runner.

## Setup

```bash
pip install -e .
```

Create a `.env` file in the project root:

```
SLEEPER_LEAGUE_ID=<league_id>
OPENAI_API_KEY=<key>
```

## Quick Start

```bash
# Datalayer CLI
sleeperdl app                                          # Interactive query shell
sleeperdl load-export --output out.sqlite

# Reporter CLI
reporter-v2 "weekly recap" --week 8                    # Natural language request
reporter-v2 "snarky recap, roast Team Taco" --week 8   # With week and style hints
reporter-v2 "power rankings with analysis" --week 8    # Any article type
reporter-v2 "deep dive on Team Taco's season" --week 8 # Team-focused
```

## API Server

The product API exposes process health now and provides the versioned route
boundary for generation, memory, and Sleeper-data APIs as their services land.

```bash
export AIDAM_DATABASE_URL=postgresql+psycopg://aidam_api:password@localhost/aidam
export AIDAM_DATABASE_REQUIRE_TLS=false  # isolated local PostgreSQL only
aidam-api
```

The server listens on `127.0.0.1:8000` by default. Override that with
`AIDAM_API_HOST` and `AIDAM_API_PORT`. Liveness is available at
`/health/live`; readiness at `/health/ready` also verifies the configured
database name, runtime role, and TLS policy.

## Tests

```bash
pytest                                  # All tests
pytest datalayer/tests/                 # Datalayer tests only
pytest reporter_memory/tests/           # Reporter memory tests only
pytest reporter_v2/tests/               # Reporter v2 tests only
pytest backend/tests/api/                # API boundary tests only
pytest datalayer/tests/unit/            # Datalayer unit tests
pytest datalayer/tests/integration/     # Datalayer integration tests
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
