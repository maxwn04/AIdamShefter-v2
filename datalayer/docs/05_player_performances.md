# Player Performances Table

## Context

Matchups are currently stored with player-level data embedded as JSON blobs
(`players_json`, `players_points_json`, `starters_json`). This makes it easy to
persist raw API payloads but forces downstream queries to parse JSON in Python.
As the AI reporter expands, we need to ask detailed questions about individual
players and their weekly contributions, which is awkward and inefficient with
JSON-only storage.

Because data is re-collected each run, we do not need a migration of existing
state. We can extend the schema and backfill the table during the ingestion
process.

## Goals

- Enable SQL-first queries for player performance by week and season.
- Keep matchup-level data intact while avoiding JSON wrangling for routine
  player lookups.
- Support richer player questions (streaks, top weeks, role-based scoring).
- Maintain a clear lineage to roster and matchup context.

## Non-Goals

- Replace or remove existing matchup JSON columns.
- Create historical migrations or ETL backfills outside the regular run.

## Proposal

Introduce a new `player_performances` table, populated during normalization of
weekly matchups. Each row represents a single player's points for a roster in a
specific week, with optional matchup context and role indicators.

### Proposed schema

Table name: `player_performances`

Suggested columns:

- `league_id` (TEXT, not null)
- `season` (TEXT, not null)
- `week` (INTEGER, not null)
- `player_id` (TEXT, not null)
- `roster_id` (INTEGER, not null)
- `matchup_id` (INTEGER, not null)
- `points` (REAL, not null)
- `role` (TEXT, nullable; values like `starter` or `bench`)

Primary key: (`league_id`, `season`, `week`, `player_id`, `roster_id`)

Indexes:

- `idx_player_perf_league_week` on (`league_id`, `week`)
- `idx_player_perf_player_week` on (`player_id`, `season`, `week`)
- `idx_player_perf_roster_week` on (`league_id`, `roster_id`, `week`)

Foreign keys:

- (`league_id`) -> `leagues.league_id`
- (`league_id`, `roster_id`) -> `rosters.(league_id, roster_id)`
- (`player_id`) -> `players.player_id`

### Normalization approach

During matchup normalization:

1. For each matchup row, parse `players_json`, `players_points_json`,
   `starters_json`.
2. Emit `player_performances` rows for each player in `players_json`.
3. Store `role` as `starter` if the player appears in `starters_json`,
   otherwise `bench`.
4. Use `points` from `players_points_json` when present, otherwise `0.0`.

This keeps the `matchups` table as a raw record and surfaces player scoring in
normalized, query-friendly form.

### Query impact

Examples unlocked by the new table:

- "Top 10 scorers in week 7"
- "Player X weekly points over the last 5 weeks"
- "Starter vs bench points by roster"
- "Average points per position over season"

### Implementation plan

1. Add a `PlayerPerformance` model in `schema/models.py`.
2. Add a `player_performances` entry in `schema/ddl.py`.
3. Extend `normalize/matchups.py` to emit performance rows alongside matchup
   rows, using the same raw payloads.
4. Update the ingestion pipeline to insert these rows into SQLite.
5. Add one or two query helpers in `queries/defaults.py` for common use cases
   (week leaderboard, player weekly log).

## Risks and considerations

- The table will grow quickly (players per roster per week), but SQLite should
  handle this with indexing and in-memory queries scoped by week or player.
- Some players may be missing from `players_points_json`. The plan explicitly
  stores `0.0` for these cases to simplify aggregations.
- Trades mid-week could theoretically introduce edge cases, but the table is
  derived directly from matchup payloads, so it reflects the source of truth.

