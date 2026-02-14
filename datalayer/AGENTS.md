# Datalayer Architecture

## Entry Point: `SleeperLeagueData`

**File:** `sleeper_data/sleeper_league_data.py`

```python
from datalayer.sleeper_data import SleeperLeagueData

data = SleeperLeagueData()  # Reads SLEEPER_LEAGUE_ID from env
data.load()                  # Fetches all data, normalizes, loads into SQLite

# Curated query methods (all accept names or IDs via roster_key/player_key):
data.get_league_snapshot(week=None)
data.get_week_games(week=None)
data.get_week_games_with_players(week=None)
data.get_week_player_leaderboard(week=None, limit=10)
data.get_season_leaders(week_from=None, week_to=None, position=None, roster_key=None, role=None, sort_by="total", limit=10)
data.get_team_dossier(roster_key, week=None)
data.get_team_schedule(roster_key)
data.get_team_game(roster_key, week=None)
data.get_team_game_with_players(roster_key, week=None)
data.get_roster_current(roster_key)
data.get_roster_snapshot(roster_key, week)
data.get_transactions(week_from, week_to)
data.get_team_transactions(roster_key, week_from, week_to)
data.get_week_transactions(week=None)
data.get_team_week_transactions(roster_key, week=None)
data.get_player_summary(player_key)
data.get_player_weekly_log(player_key, week_from=None, week_to=None)
data.run_sql(query, params=None, limit=200)  # SELECT-only, auto-limited
```

## Query Return Shapes

Most queries return dicts with a `found` key. List-returning queries return `list[dict]` directly.

**`get_league_snapshot(week=8)`** — League-wide context:
```json
{
  "found": true,
  "as_of_week": 8,
  "league": {"name": "...", "season": "2024", "playoff_week_start": 14},
  "standings": [
    {"roster_id": 1, "team_name": "...", "wins": 7, "losses": 1, "points_for": 1204.5, "rank": 1}
  ],
  "games": [
    {"week": 8, "matchup_id": 1, "team_a": "...", "team_b": "...", "points_a": 142.3, "points_b": 98.7, "winner": "..."}
  ],
  "transactions": [...]
}
```

**`get_team_dossier("Team Taco", week=8)`** — Team profile:
```json
{
  "found": true,
  "as_of_week": 8,
  "team": {"team_name": "Team Taco", "manager_name": "..."},
  "standings": {"wins": 7, "losses": 1, "record": "7-1", "rank": 1, "points_for": 1204.5, "streak_type": "W", "streak_len": 4},
  "recent_games": [{"week": 8, "team_a": "...", "points_a": 142.3, "points_b": 98.7, "winner_roster_id": 1}]
}
```

**`get_week_games(week=8)`** — Returns `list[dict]`:
```json
[
  {"week": 8, "matchup_id": 1, "team_a": "Team Taco", "team_b": "The Waiver Wire", "points_a": 142.3, "points_b": 98.7, "winner": "Team Taco"}
]
```

**`get_player_weekly_log("Patrick Mahomes")`** — Player season log (pass `week_from`/`week_to` to filter):
```json
{
  "found": true,
  "player_name": "Patrick Mahomes",
  "weeks_played": 8,
  "total_points": 185.4,
  "avg_points": 23.2,
  "performances": [
    {"week": 1, "points": 28.5, "role": "starter", "team_name": "Team Taco"}
  ]
}
```

**`get_season_leaders(position="QB", limit=5)`** — Season-long rankings, returns `list[dict]`:
```json
[
  {
    "rank": 1,
    "player_name": "Patrick Mahomes",
    "position": "QB",
    "nfl_team": "KC",
    "team_name": "Team Taco",
    "total_points": 285.4,
    "avg_points": 23.8,
    "weeks_played": 12,
    "best_week": 42.3,
    "worst_week": 8.1
  }
]
```

**`get_transactions(week_from=7, week_to=8)`** — Returns `list[dict]`:
```json
[
  {
    "week": 8, "transaction_id": 123, "type": "trade", "status": "complete",
    "details": [
      {"team_name": "Team Taco", "assets_received": [{"asset_type": "player", "player_name": "...", "position": "WR"}], "assets_sent": [...]}
    ]
  }
]
```

**`run_sql("SELECT team_name, wins FROM standings WHERE week = 8 ORDER BY rank")`** — Raw SQL:
```json
{
  "columns": ["team_name", "wins"],
  "rows": [["Team Taco", 7], ["The Waiver Wire", 6]],
  "row_count": 2
}
```

Not-found responses return `{"found": false, ...}` with context about what was searched.

## Load Flow (what `data.load()` does)

1. Creates in-memory SQLite (`check_same_thread=False` for async)
2. Fetches league metadata, users, rosters, NFL state → normalizes → inserts
3. Seeds draft picks (roster × 3 seasons × rounds), applies traded picks
4. Fetches all players → inserts
5. For each week 1..effective_week: matchups → MatchupRows + PlayerPerformances + Games; transactions → TransactionMoves
6. Derives standings from roster metadata
7. Stores SeasonContext (computed_week, override_week, effective_week)

## SQLite Schema (13 tables)

| Table | Model | Key Columns |
|---|---|---|
| `leagues` | League | league_id, season, name, playoff_week_start |
| `season_context` | SeasonContext | league_id, computed_week, effective_week |
| `users` | User | user_id, display_name |
| `rosters` | Roster | league_id, roster_id, owner_user_id, record_string |
| `roster_players` | RosterPlayer | league_id, roster_id, player_id, role |
| `team_profiles` | TeamProfile | league_id, roster_id, team_name, manager_name |
| `draft_picks` | DraftPick | league_id, season, round, original_roster_id, current_roster_id |
| `players` | Player | player_id, full_name, position, nfl_team, status |
| `matchups` | MatchupRow | league_id, season, week, matchup_id, roster_id, points |
| `player_performances` | PlayerPerformance | league_id, season, week, player_id, roster_id, points, role |
| `games` | Game | league_id, season, week, matchup_id, roster_id_a/b, points_a/b, winner_roster_id |
| `standings` | StandingsWeek | league_id, season, week, roster_id, wins, losses, rank, streak_type/len |
| `transactions` | Transaction | league_id, season, week, transaction_id, type, status |
| `transaction_moves` | TransactionMove | transaction_id, roster_id, player_id, asset_type, direction, pick metadata |

All models defined in `sleeper_data/schema/models.py`. DDL with indexes in `schema/ddl.py`.

## Name Resolution

Query methods accept `roster_key` (team name, manager name, or roster_id as string) and `player_key` (player name or player_id). Resolution is case-insensitive with ambiguity handling. Implementation in `queries/_resolvers.py`.

## Guarded SQL (`run_sql`)

- Only `SELECT` allowed — blocks INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, REPLACE, PRAGMA
- Auto-adds `LIMIT` if missing
- Returns `{columns, rows, row_count}`
- Implementation in `queries/sql_tool.py`

## Testing

- **Fixtures**: JSON snapshots from Sleeper API in `tests/fixtures/sleeper/`
- **conftest.py**: `loaded_data` fixture — fully loaded `SleeperLeagueData` from fixture data
- **Monkeypatching**: Integration tests monkeypatch `SleeperClient` to return fixture data
- **No mocks for SQLite**: Real in-memory SQLite in tests — fast enough
- **Organization**: `unit/` for normalizers, queries, schema; `integration/` for full load + CLI

## Design Docs

- `docs/architecture.md` — High-level overview
- `docs/01_datalayer.md` — Core data layer design, schema, startup flow
- `docs/02_surfacing_names.md` — Name resolution strategy
- `docs/03_picks.md` — Draft pick ownership tracking
- `docs/04_transactions.md` — Transaction + pick metadata design
- `docs/05_player_performances.md` — Player-level scoring extraction
