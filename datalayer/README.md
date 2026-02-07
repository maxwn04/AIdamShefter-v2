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

- `snapshot [week]`
- `games [week]`
- `team <roster_key> [week]` — accepts team name, manager name, or roster_id
- `roster <roster_key> [week]`
- `transactions <week_from> <week_to>`
- `player <player_key> [week_to]` — accepts player name or player_id
- `sql <select_query>`
- `help`, `exit`, `quit`

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
