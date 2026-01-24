# Design Doc: Python-First Sleeper Fantasy League Data Layer (MVP)

## Summary

Build an MVP data layer that, on startup, **fetches Sleeper league data fresh**, **normalizes it into a stable canonical schema (Python dataclasses)**, loads it into an **in-memory SQLite database**, and exposes a single entrypoint class—`SleeperLeagueData`—for both the reporter agent and a CLI. The layer supports a **week override env var** to fix offseason “wrong current week” behavior and to enable mid-season mocking.

---

## Goals

* **Fresh startup load**: pull league + rosters + matchups + standings-related inputs + transactions + players and populate DB each run.
* **Canonical schema**: normalize raw Sleeper JSON into dataclasses that represent stable, human/LLM-friendly entities.
* **In-memory relational store**: load canonical entities into SQLite `:memory:` for easy joins and flexible querying.
* **Single access class**: `SleeperLeagueData` provides:

  * a small set of default “research queries”
  * a safe tool to run custom queries (SQL) for agent experimentation
* **Week override**: allow env var to override “effective week” (offseason bug + mocking).

## Non-goals (MVP)

* Persistent storage across runs (no file-based DB in MVP).
* Full historical reconstruction by replaying transactions.
* Projections, advanced analytics, or heavy caching strategies.
* Multi-league/multi-season orchestration (supported structurally, but not required for MVP).

---

## High-level Architecture

### Modules

1. **Fetch Layer (`sleeper_api/`)**

   * Wraps HTTP calls, returns raw JSON.
   * No transformation beyond minimal validation.
   * Optional: simple request logging + file dump for debugging.

2. **Normalize Layer (`normalize/`)**

   * Converts raw JSON into canonical dataclasses.
   * Resolves IDs into readable attributes where possible (e.g., `roster_id -> team_name`).
   * Computes **derived** entities needed for reporting (e.g., pairing matchup rows into games; standings snapshots if feasible).

3. **Store Layer (`store/`)**

   * Creates in-memory SQLite schema.
   * Inserts dataclass rows.
   * Defines indexes for common query paths.

4. **Query Layer (`queries/`)**

   * “Thin” helpers: a few curated queries + a generic SQL execution method.
   * Outputs results as:

     * Python objects (dataclasses) and/or
     * JSON-ready dicts for the reporter agent.

5. **Facade (`SleeperLeagueData`)**

   * Orchestrates end-to-end: resolve week → fetch → normalize → load → expose query API.
   * Used by CLI and agent tools.

---

## Configuration

### Required

* `SLEEPER_LEAGUE_ID` (string/int)

### Week override

* `SLEEPER_WEEK_OVERRIDE` (int, optional)

  * If set, this becomes the **effective week** used for snapshot-style queries and “report as of week N.”
* Optional clamps (nice-to-have for robustness):

  * `SLEEPER_WEEK_MIN` (default 1)
  * `SLEEPER_WEEK_MAX` (default 18 or 17 depending on league rules; allow override)

### Runtime behavior

* On startup:

  * compute `computed_week` via Sleeper “state” (or equivalent)
  * compute `effective_week = override_week if set else computed_week`
  * store both in a `season_context` table (or in-memory object + DB row)

---

## Canonical Schema (Dataclasses)

Dataclasses are the single source of truth for normalized fields and table definitions.

### Core entities

* `League`

  * `league_id`, `season`, `name`, `sport`, `scoring_settings_json`, `roster_positions_json`, `playoff_week_start`, `playoff_teams`
* `SeasonContext`

  * `league_id`, `computed_week`, `override_week`, `effective_week`, `generated_at`

### People/teams

* `User`

  * `user_id`, `display_name`, `avatar`, `metadata_json`
* `Roster`

  * `league_id`, `roster_id`, `owner_user_id`, `settings_json`, `metadata_json`
* `TeamProfile` (LLM-friendly identity)

  * `league_id`, `roster_id`, `team_name`, `manager_name`, `avatar_url`

### Matchups

* `MatchupRow` (Sleeper gives rows per roster per matchup_id)

  * `league_id`, `season`, `week`, `matchup_id`, `roster_id`, `points`, `starters_json`, `players_json`
* `Game` (derived pairing of two matchup rows)

  * `league_id`, `season`, `week`, `matchup_id`, `roster_id_a`, `roster_id_b`, `points_a`, `points_b`, `winner_roster_id`, `is_playoffs`

### Players

* `Player`

  * `player_id`, `full_name`, `position`, `nfl_team`, `status`, `injury_status`, `metadata_json`, `updated_at`
* `PlayerWeekStats` (optional in MVP if you pull weekly scoring stats)

  * `league_id`, `season`, `week`, `player_id`, `points`, `stats_json`

### Transactions

* `Transaction`

  * `league_id`, `season`, `week`, `transaction_id`, `type`, `status`, `created_ts`, `settings_json`, `metadata_json`
* `TransactionMove`

  * `transaction_id`, `roster_id`, `player_id`, `direction` (“add”/“drop”), `bid_amount`, `from_roster_id`, `to_roster_id`

### Standings (derived)

* `StandingsWeek`

  * `league_id`, `season`, `week`, `roster_id`, `wins`, `losses`, `ties`, `points_for`, `points_against`, `rank`, `streak_type`, `streak_len`

**MVP note:** If standings derivation is complex for your first pass, you can store what Sleeper provides in `rosters.settings_json` and derive standings only for the effective week first. Then iterate to weekly snapshots later.

---

## SQLite In-Memory Store

### Connection

* Use `sqlite3.connect(":memory:")`
* Enable:

  * `PRAGMA foreign_keys = ON`
  * `PRAGMA journal_mode = MEMORY` (optional)
  * `PRAGMA temp_store = MEMORY` (optional)

### Table creation strategy

* Define a small internal “DDL builder” that:

  * maps dataclass fields → SQLite column types
  * creates tables + PK/FK/indexes
* Store JSON-ish fields as `TEXT` containing JSON.

### Indexing (recommended for MVP performance)

* `matchups(league_id, season, week)`
* `matchups(week, matchup_id)`
* `games(league_id, season, week)`
* `transactions(league_id, season, week)`
* `transaction_moves(transaction_id)`
* `player_week_stats(player_id, week)`
* `rosters(league_id, roster_id)`

---

## Startup Load: End-to-End Flow

### 1) Resolve effective week

* Fetch computed week from Sleeper.
* Apply override.
* Store `SeasonContext`.

### 2) Fetch raw data (minimum set)

MVP recommended fetches:

* League metadata
* Users + rosters (+ team names)
* Matchups for weeks `1..effective_week` (or just the last N weeks if you want faster MVP)
* Transactions for weeks `1..effective_week` (or last N weeks)
* Player dictionary (once per run)

### 3) Normalize

* Convert each raw payload into dataclass lists.
* Derive:

  * `Game` rows by pairing `MatchupRow`s on `(week, matchup_id)`
  * (Optional) `StandingsWeek` by week based on matchup results

### 4) Load into DB

* Create tables.
* Bulk insert rows (executemany).
* Create indexes.

### 5) Expose query API

* `SleeperLeagueData` now serves queries against the loaded DB.

---

## `SleeperLeagueData` Facade API

### Construction

```python
data = SleeperLeagueData(
    league_id="123456789",
    week_override=os.getenv("SLEEPER_WEEK_OVERRIDE"),
)
data.load()  # fetch → normalize → populate sqlite
```

### Key properties

* `data.conn`: sqlite connection (optional; keep private by default)
* `data.effective_week`, `data.computed_week`
* `data.league`: League dataclass

### Default query helpers (MVP set)

1. **League snapshot**

   * `get_league_snapshot(week: int | None = None) -> dict`
   * Returns standings-ish summary, notable matchups, top scorers (if available), transactions.

2. **Team dossier**

   * `get_team_dossier(roster_key: str | int, week: int | None = None) -> dict`
   * Accepts roster ID, team name, or manager name.
   * Record, rank trend (if you compute it), recent games, roster highlights, transaction activity.

3. **Week games**

   * `get_week_games(week: int | None = None) -> list[dict]`
   * Paired games with readable team names.

4. **Recent transactions**

   * `get_transactions(week_from: int, week_to: int) -> list[dict]`

5. **Player dossier**

   * `get_player_summary(player_key: str, week_to: int | None = None) -> dict`
   * Accepts player ID or full name.

6. **Roster views**

   * `get_roster_current(roster_key: str | int) -> dict`
   * `get_roster_snapshot(roster_key: str | int, week: int) -> dict`
   * Accepts roster ID, team name, or manager name.

### Custom SQL tool (for agent)

* `run_sql(query: str, params: tuple | dict | None = None, *, limit: int = 200) -> dict`

  * Returns:

    * `columns`: list[str]
    * `rows`: list[list[Any]]
    * `row_count`: int
  * Safety/guardrails:

    * allow only `SELECT` in MVP
    * enforce a `limit` if missing (append `LIMIT ...` unless query already has one)
    * timebox execution (best-effort)
    * prohibit PRAGMA/ATTACH by simple keyword blacklist

This gives your agent the “make its own queries” power without turning the DB into a footgun.

---

## “LLM-Readable” Output Strategy

Even though storage is relational, your reporter will prefer **curated JSON views**. Each default query should produce:

* stable field names
* readable names instead of IDs where possible
* short lists + computed highlights
* include `as_of_week` so narratives don’t mismatch

Example output contracts:

* `LeagueSnapshotV1`
* `TeamDossierV1`
* `WeekGamesV1`

Version the view schemas (`...V1`) so you can evolve without breaking prompts/tools.

---

## CLI (MVP)

Provide a small CLI for debugging + manual usage:

* `sleeperdl load`
  Loads data and prints a summary (effective week, team count, weeks loaded, etc.)

* `sleeperdl snapshot --week 12`
  Prints `get_league_snapshot(12)` as JSON.

* `sleeperdl team --roster-id 3 --week 12`

* `sleeperdl sql "SELECT ..."`
  Runs `run_sql` and pretty-prints.

---

## Testing Strategy

* **Unit tests**

  * Normalizers: raw fixture JSON → expected dataclasses.
  * Week override resolution.
  * Game pairing logic: matchup rows → game rows.

* **Integration tests**

  * “Load from fixtures” mode (no network):

    * `SleeperLeagueData(load_from_fixtures_dir=...)`
  * Validate DB row counts, key indexes exist, example queries return stable shape.

---

## Observability & Debugging (MVP-friendly)

* Log:

  * effective week resolution (`computed_week`, `override_week`, `effective_week`)
  * counts inserted per table
  * fetch durations per endpoint
* Optional: dump raw JSON to `./.cache/sleeper/{league_id}/...` for quick inspection.

---

## Open Questions / Planned Iterations

* How far back to load in MVP:

  * Full season `1..effective_week` vs last `N` weeks for speed.
* Standings derivation:

  * Start with effective-week standings only, then add weekly history.
* Player points:

  * Confirm which Sleeper endpoints you’ll use for weekly scoring to populate `PlayerWeekStats`.

---

## Proposed Folder Layout

```
datalayer/
  sleeper_data/
    __init__.py
    config.py
    sleeper_league_data.py        # SleeperLeagueData facade
    sleeper_api/
      client.py                   # HTTP calls
      endpoints.py
    schema/
      models.py                   # dataclasses
      ddl.py                      # dataclass -> sqlite DDL mapping
    normalize/
      league.py
      rosters.py
      matchups.py
      transactions.py
      players.py
      derive_games.py
      derive_standings.py
    store/
      sqlite_store.py             # create tables, bulk insert, indexes
    queries/
      defaults.py                 # snapshot/dossier queries
      sql_tool.py                 # run_sql guardrails
  cli/
    main.py
  tests/
    fixtures/
    test_normalize_*.py
    test_queries_*.py
```

---