# AGENTS.md

## What This Project Is

AIdamShefter-v2 is an AI-powered fantasy football reporter. It has three major subsystems:

1. **Datalayer** (`datalayer/`) — Fetches Sleeper fantasy football league data, normalizes it into dataclasses, loads it into an in-memory SQLite database, and exposes typed query methods + a guarded SQL escape hatch.
2. **Reporter Memory** (`reporter_memory/`) — Persistent reporter-generated narrative memory: storylines, team context, league notes, history, persisted facts, events, triggers, and access history. Current schema is `3`; memory rows are scoped by league and season.
3. **Reporter V2** (`reporter_v2/`) — A single-loop agent that uses datalayer tools and reporter memory to research league data, then writes data-grounded articles with configurable voice, bias, and style.

`sleeperdl context` and `sleeperdl memory` are removed; memory access belongs to
`reporter_memory` and reporter v2 persistent tools.

The pipeline: `Sleeper API → Normalize → In-Memory SQLite → Query API → Reporter Agent → Article`

## Setup

```bash
pip install -e .                   # Installs datalayer CLI and reporter-v2 CLI
```

Required `.env` file in project root:
```
SLEEPER_LEAGUE_ID=<league_id>      # Required
OPENAI_API_KEY=<key>               # Required for reporter
SLEEPER_WEEK_OVERRIDE=12           # Optional: pin to a specific week (useful offseason)
REPORTER_MODEL=gpt-5-mini          # Optional: default model for reporter
REPORTER_OUTPUT_DIR=.output        # Optional: where articles are saved
```

## Common Commands

```bash
# Tests
pytest                                          # All default tests
pytest datalayer/tests/                         # All datalayer tests
pytest reporter_memory/tests/                   # Reporter memory tests
pytest reporter_v2/tests/                       # Reporter v2 tests
pytest datalayer/tests/unit/                    # Datalayer unit tests
pytest datalayer/tests/integration/             # Datalayer integration tests

# Datalayer CLI
sleeperdl app                                   # Interactive query shell
sleeperdl load-export --output out.sqlite       # Export to SQLite file

# Reporter CLI
reporter-v2 "weekly recap" --week 8                         # Natural language request
reporter-v2 "snarky recap, roast Team Taco" --week 8         # With week and style hints
reporter-v2 "power rankings with analysis" --week 8          # Any article type
```

## Project Structure

```
datalayer/
├── sleeper_data/
│   ├── sleeper_league_data.py    # Facade: SleeperLeagueData (main entry point)
│   ├── load.py                   # Fetch → normalize → store orchestration
│   ├── config.py                 # SleeperConfig, load_config()
│   ├── sleeper_api/              # HTTP fetch layer (client.py, endpoints.py)
│   ├── normalize/                # Raw JSON → dataclasses (one module per entity)
│   ├── schema/                   # One module per table (row DTO + Core Table)
│   ├── store/sqlite_store.py     # create_tables(), bulk_insert()
│   └── queries/                  # Query functions + resolvers + sql_tool
├── tools.py                      # SLEEPER_TOOLS (OpenAI function-calling format)
├── cli/main.py                   # sleeperdl CLI
├── tests/
│   ├── conftest.py               # Fixtures (loads JSON from fixtures/sleeper/)
│   ├── fixtures/sleeper/         # league.json, users.json, matchups_week1.json, etc.
│   ├── unit/                     # normalize/, queries/, schema/ tests
│   └── integration/              # Full load, CLI, week override tests
└── docs/                         # Design docs

reporter_memory/
├── schema.py                     # SCHEMA_VERSION + DDL
├── context_store.py              # ContextStore facade (store mixins)
├── store/                        # Persistence: storylines, events, triggers, FTS
├── search/                       # Search pipeline, ranking, verification planning
├── context_tools.py              # Legacy-style memory tool definitions/handlers
└── tests/                        # Reporter memory tests

reporter_v2/
├── runner/                       # Core runner logic and tools
├── app/                          # CLI entry point
├── prompts/                      # Prompt templates
├── procedures/                   # Procedure files loaded by the runner
└── tests/                        # Reporter v2 tests
```

## Code Conventions

### Python Style

- **Python 3.11+** — use modern syntax (`X | Y` unions, `match` statements where appropriate)
- **Dataclasses over dicts** — domain row models are `@dataclass` in `schema/<table>.py`
- **Type hints everywhere** — function signatures, return types, variables where non-obvious
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants
- **Imports**: stdlib → third-party → local, separated by blank lines. Prefer `from datalayer.sleeper_data.schema import Player`

### Patterns

- **Facade pattern**: `SleeperLeagueData` is the single public entry point for all datalayer queries
- **Load pipeline**: `load.load_league` owns fetch → normalize → store; facade owns connection lifecycle
- **Normalize layer**: Each entity type has its own normalizer module — raw JSON in, dataclass out
- **Query functions**: Pure functions that take a SQLAlchemy `Connection` and return dicts. Name resolution handled by `_resolvers.py`
- **Tool definitions**: OpenAI function-calling format in `datalayer/tools.py`; reporter v2 registers model-facing tools under `reporter_v2/runner/tools/`

### Error Handling

- Query methods return `{"found": false, ...}` for missing entities — no exceptions for "not found"
- Only validate at boundaries (API input, SQL injection guards)
- Trust internal code paths — don't add defensive checks inside normalizers or query functions

### Testing

- **Fixtures**: JSON snapshots from Sleeper API live in `datalayer/tests/fixtures/sleeper/`
- **conftest.py**: Provides `loaded_data` fixture — a fully loaded `SleeperLeagueData` instance backed by fixture data
- **Monkeypatching**: Integration tests monkeypatch `SleeperClient` to return fixture data instead of hitting the API
- **No mocks for SQLite**: Tests use real in-memory SQLite — the store is fast enough
- **Test organization**: `unit/` for pure function tests (normalizers, queries, schema), `integration/` for full load + CLI tests

## Design Principles

- **Fresh load every run**: No persistence; Sleeper API is source of truth
- **One module per table**: `schema/<table>.py` owns the row DTO and SQLAlchemy Core `Table`
- **Query-time joins**: Names resolved at query time, not denormalized into storage
- **Brief-first writing**: Research produces a verified artifact before any drafting happens
- **Bias = framing only**: Bias changes word choice and emphasis, never facts or numbers
- **Guarded SQL**: Agent can explore freely with SELECT-only + auto-LIMIT
- **Full observability**: ResearchLog captures every tool call, reasoning step, and timing
