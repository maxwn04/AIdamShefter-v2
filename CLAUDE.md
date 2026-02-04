# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based data layer for Sleeper fantasy football leagues, designed to serve AI-powered fantasy football reporting. It fetches raw data from the Sleeper API, normalizes it into canonical dataclasses, loads it into an in-memory SQLite database, and exposes query methods for downstream consumers.

**Core Entry Point:** `SleeperLeagueData` (in `datalayer/sleeper_data/sleeper_league_data.py`)

## Setup

1. Create a `.env` file in the project root with:
   ```
   SLEEPER_LEAGUE_ID=your_league_id
   SLEEPER_WEEK_OVERRIDE=12  # Optional: override current week
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install package in development mode (for CLI access):
   ```bash
   pip install -e .
   ```

## Common Commands

### Running Tests

```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/datalayer/unit/queries/test_sql_tool.py

# Run tests with verbose output
pytest -v

# Run integration tests only
pytest tests/datalayer/integration/

# Run unit tests only
pytest tests/datalayer/unit/
```

### CLI Usage

```bash
# Export data to SQLite file
sleeperdl load-export --output ".cache/sleeper/<league_id>.sqlite"

# Or use module syntax
python -m datalayer.cli.main load-export --output ".cache/sleeper/<league_id>.sqlite"

# Run interactive app (loads once, then query)
sleeperdl app
python -m datalayer.cli.main app
```

### Interactive App Commands

Once in the app, use these commands:
- `snapshot [week]` - League standings snapshot
- `games [week]` - All matchups for a week
- `team <roster_id> [week]` - Team dossier (record, streaks, etc.)
- `roster <roster_id> [week]` - Current roster composition
- `transactions <week_from> <week_to>` - Transactions in a week range
- `player <player_id> [week_to]` - Player weekly performance log
- `sql <select_query>` - Run custom SELECT query
- `help`, `exit`, `quit`

## Architecture

The system follows a layered pipeline:

```
Sleeper API → Normalize → In-Memory SQLite → Query API → Reporter/CLI
```

### Key Layers

1. **Fetch Layer** (`datalayer/sleeper_data/sleeper_api/`)
   - `client.py`: HTTP client wrapper
   - `endpoints.py`: API endpoint definitions
   - Returns raw JSON from Sleeper API

2. **Normalize Layer** (`datalayer/sleeper_data/normalize/`)
   - Converts raw JSON into canonical dataclasses
   - Modules: `league.py`, `users.py`, `rosters.py`, `matchups.py`, `players.py`, `transactions.py`, `standings.py`
   - Derives computed entities (e.g., pairing matchup rows into games)
   - Resolves IDs into human-readable attributes

3. **Schema Layer** (`datalayer/sleeper_data/schema/`)
   - `models.py`: Canonical dataclass definitions (single source of truth)
   - `ddl.py`: DDL generation from dataclasses for SQLite tables

4. **Store Layer** (`datalayer/sleeper_data/store/`)
   - `sqlite_store.py`: In-memory SQLite operations
   - Functions: `create_tables()`, `bulk_insert()`

5. **Query Layer** (`datalayer/sleeper_data/queries/`)
   - `defaults.py`: Curated query methods (e.g., `get_league_snapshot()`, `get_team_schedule()`, `get_player_weekly_log()`)
   - `sql_tool.py`: Guarded SQL execution (prevents writes, limits results)

6. **Facade** (`datalayer/sleeper_data/sleeper_league_data.py`)
   - `SleeperLeagueData` class orchestrates: resolve week → fetch → normalize → load → expose queries

### Design Principles

- **In-memory SQLite**: Fast loads, rich joins, no persistence complexity in MVP
- **Dataclasses as schema**: Single source of truth for data shape
- **Query-time joins**: Avoid denormalized names; keep identities current
- **Name resolution**: Accept inputs by name or ID; return human-readable outputs
- **Guarded SQL**: Supports exploration while preventing writes and unbounded queries
- **Week override**: Environment variable (`SLEEPER_WEEK_OVERRIDE`) fixes offseason "current week" issues and enables mid-season testing

## Programmatic Usage

```python
from datalayer.sleeper_data import SleeperLeagueData

data = SleeperLeagueData()
data.load()

# Get league snapshot
snapshot = data.get_league_snapshot()

# Get team schedule
schedule = data.get_team_schedule(roster_id=1)

# Run custom SQL
results = data.run_sql("SELECT * FROM rosters LIMIT 10")
```

## Testing Structure

- `tests/datalayer/conftest.py`: Shared fixtures
- `tests/datalayer/unit/`: Unit tests for individual modules (queries, schema, normalize)
- `tests/datalayer/integration/`: Integration tests (CLI, full data load, week override)

## Configuration (`datalayer/sleeper_data/config.py`)

Configuration is loaded from environment variables via `load_config()`:
- `SLEEPER_LEAGUE_ID`: Required league identifier
- `SLEEPER_WEEK_OVERRIDE`: Optional integer to override the effective week

## Additional Documentation

Detailed design documents are in `datalayer/docs/`:
- `architecture.md`: High-level architecture overview
- `01_datalayer.md`: Core data layer design
- `02_surfacing_names.md`: Name resolution approach
- `03_picks.md`: Draft pick tracking
- `04_transactions.md`: Transaction processing
- `05_player_performances.md`: Player performance tracking
