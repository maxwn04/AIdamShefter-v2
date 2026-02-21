## Sleeper Data Layer

### Setup

1. Create a `.env` file (project root) with:
   - `SLEEPER_LEAGUE_ID=your_league_id`
   - Optional: `SLEEPER_WEEK_OVERRIDE=12`

2. Install:
   - `pip install -e .`

### CLI Usage

- Export a local SQLite file:
  - `sleeperdl load-export --output ".cache/sleeper/<league_id>.sqlite"`

- Run interactive app (loads once, then query):
  - `sleeperdl app`

### App Commands

The interactive app uses the same tool names as the agent API. Parameters can be passed positionally or as `key=value` pairs.

**League-wide:**
- `get_league_snapshot [week]`
- `get_standings [week]`
- `get_week_games [week]`
- `get_week_games_with_players [week]`
- `get_week_player_leaderboard [week] [limit]`
- `get_season_leaders [week_from] [week_to] [position] [roster_key] [role] [sort_by] [limit]`
- `get_bench_analysis [roster_key] [week]`
- `get_transactions <week_from> <week_to>`
- `get_week_transactions [week]`
- `get_playoff_bracket [bracket_type]`

**Team-specific:**
- `get_team_dossier <roster_key> [week]`
- `get_team_schedule <roster_key>`
- `get_team_game <roster_key> [week]`
- `get_team_game_with_players <roster_key> [week]`
- `get_roster_current <roster_key>`
- `get_roster_snapshot <roster_key> <week>`
- `get_team_transactions <roster_key> <week_from> <week_to>`
- `get_team_week_transactions <roster_key> [week_from] [week_to]`
- `get_team_playoff_path <roster_key>`

**Player-specific:**
- `get_player_summary <player_key>`
- `get_player_weekly_log <player_key> [week_from] [week_to]`

**Other:**
- `run_sql <query> [limit]` — SELECT-only, auto-limited
- `save [output_path]` — export SQLite file
- `tools` / `help` — show available commands
- `exit` / `quit`

All `roster_key` parameters accept team name, manager name, or roster_id. All `player_key` parameters accept player name or player_id. Resolution is case-insensitive.

### SQLite Storage

The database uses **SQLAlchemy** with an **in-memory SQLite** backend (`create_engine("sqlite://")`). Data is fetched fresh from the Sleeper API on every `load()` call and is not persisted to disk unless you explicitly export it:

- CLI: `sleeperdl load-export --output out.sqlite`
- App: `save [output_path]` (defaults to `.cache/sleeper/<league_id>.sqlite`)
- Code: `data.save_to_file("out.sqlite")`

### Programmatic Usage

```python
from datalayer.sleeper_data import SleeperLeagueData

data = SleeperLeagueData()
data.load()
snapshot = data.get_league_snapshot()
```

### Tests

```bash
pytest datalayer/tests/                 # All datalayer tests
pytest datalayer/tests/unit/            # Unit tests only
pytest datalayer/tests/integration/     # Integration tests only
```

Test fixtures live in `datalayer/tests/fixtures/sleeper/`.
