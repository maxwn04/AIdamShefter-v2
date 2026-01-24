## Sleeper Data Layer

### Setup

1. Create a `.env` file (project root) with:
   - `SLEEPER_LEAGUE_ID=your_league_id`
   - Optional: `SLEEPER_WEEK_OVERRIDE=12`

2. Install dependencies:
   - `pip install -r requirements.txt`

### CLI Usage

- Export a local SQLite file:
  - `sleeperdl load-export --output ".cache/sleeper/<league_id>.sqlite"`
  - Or: `python -m datalayer.cli.main load-export --output ".cache/sleeper/<league_id>.sqlite"`

- Run interactive app (loads once, then query):
  - `sleeperdl app`
  - Or: `python -m datalayer.cli.main app`

### App Commands

- `snapshot [week]`
- `games [week]`
- `team <roster_id> [week]`
- `transactions <week_from> <week_to>`
- `player <player_id> [week_to]`
- `sql <select_query>`
- `help`, `exit`, `quit`

### Programmatic Usage

```python
from datalayer.sleeper_data import SleeperLeagueData

data = SleeperLeagueData()
data.load()
snapshot = data.get_league_snapshot()
```
