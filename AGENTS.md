# AGENTS.md

## What This Project Is

AIdamShefter-v2 is an AI-powered fantasy football reporter. It has two major subsystems:

1. **Datalayer** (`datalayer/`) — Fetches Sleeper fantasy football league data, normalizes it into dataclasses, loads it into an in-memory SQLite database, and exposes typed query methods + a guarded SQL escape hatch.
2. **Reporter** (`reporter/`) — An OpenAI Agents SDK-based pipeline that uses the datalayer tools to research league data, then writes data-grounded articles with configurable voice, bias, and style.

The pipeline: `Sleeper API → Normalize → In-Memory SQLite → Query API → Reporter Agent → Article`

## Setup

```bash
pip install -e .                   # Installs both datalayer CLI and reporter CLI
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
pytest                                          # All tests (datalayer + reporter)
pytest datalayer/tests/                         # All datalayer tests
pytest datalayer/tests/unit/                    # Datalayer unit tests
pytest datalayer/tests/integration/             # Datalayer integration tests
pytest reporter/tests/                          # Reporter tests

# Datalayer CLI
sleeperdl app                                   # Interactive query shell
sleeperdl load-export --output out.sqlite       # Export to SQLite file

# Reporter CLI
reporter "weekly recap"                         # Natural language request
reporter "snarky recap, roast Team Taco" -w 8   # With week and style hints
reporter "power rankings with analysis"         # Any article type
reporter                                        # Interactive prompt
```

## Project Structure

```
datalayer/
├── sleeper_data/
│   ├── sleeper_league_data.py    # Facade: SleeperLeagueData (main entry point)
│   ├── config.py                 # SleeperConfig, load_config()
│   ├── sleeper_api/              # HTTP fetch layer (client.py, endpoints.py)
│   ├── normalize/                # Raw JSON → dataclasses (one module per entity)
│   ├── schema/
│   │   ├── models.py             # 15 dataclass models (single source of truth)
│   │   └── ddl.py                # DDL generation, DDL_REGISTRY
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

reporter/
├── __init__.py
├── agent/                        # Core agent logic (config, schemas, workflows)
├── app/                          # CLI entry point (runner.py, config.py)
├── tools/                        # Tool registry + adapter
├── prompts/                      # Prompt templates
├── docs/                         # Design docs
└── tests/                        # Reporter tests
```

## Code Conventions

### Python Style

- **Python 3.11+** — use modern syntax (`X | Y` unions, `match` statements where appropriate)
- **Dataclasses over dicts** — all domain models are `@dataclass` in `schema/models.py`
- **Type hints everywhere** — function signatures, return types, variables where non-obvious
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants
- **Imports**: stdlib → third-party → local, separated by blank lines. Use absolute imports from package root (`from datalayer.sleeper_data.schema.models import Player`)

### Patterns

- **Facade pattern**: `SleeperLeagueData` is the single public entry point for all datalayer queries
- **Normalize layer**: Each entity type has its own normalizer module — raw JSON in, dataclass out
- **Query functions**: Pure functions that take a `sqlite3.Connection` and return dicts. Name resolution handled by `_resolvers.py`
- **Tool definitions**: OpenAI function-calling format in `datalayer/tools.py`, adapted for Agents SDK in `reporter/tools/`

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
- **Dataclasses as schema**: `schema/models.py` is the single source of truth for entity shape
- **Query-time joins**: Names resolved at query time, not denormalized into storage
- **Brief-first writing**: Research produces a verified artifact before any drafting happens
- **Bias = framing only**: Bias changes word choice and emphasis, never facts or numbers
- **Guarded SQL**: Agent can explore freely with SELECT-only + auto-LIMIT
- **Full observability**: ResearchLog captures every tool call, reasoning step, and timing
