# CLAUDE.md

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
├── tests/                        # Datalayer tests
│   ├── conftest.py               # Fixtures (loads JSON from fixtures/sleeper/)
│   ├── fixtures/sleeper/         # league.json, users.json, matchups_week1.json, etc.
│   ├── unit/                     # normalize/, queries/, schema/ tests
│   └── integration/              # Full load, CLI, week override tests
└── docs/                         # Design docs (architecture, transactions, picks, etc.)

reporter/
├── __init__.py
├── agent/
│   ├── reporter_agent.py         # ReporterAgent, ResearchAgent, DraftAgent
│   ├── clarify.py                # ClarificationAgent (interactive config gathering)
│   ├── config.py                 # ReportConfig, ToneControls, BiasProfile
│   ├── schemas.py                # ReportBrief, Fact, Storyline, ArticleOutput
│   ├── policies.py               # Tool use rules, bias constraints, evidence checking
│   ├── research_log.py           # ResearchLog (audit trail)
│   └── workflows.py              # generate_report() / generate_report_async()
├── app/
│   ├── runner.py                 # CLI entry point (reporter command)
│   └── config.py                 # ReporterConfig, load_config()
├── tools/
│   ├── registry.py               # Creates OpenAI Agents SDK Tool objects
│   └── sleeper_tools.py          # ResearchToolAdapter, TOOL_DOCS
├── prompts/                      # Prompt templates (system, research, draft, bias)
├── docs/                         # Reporter design docs
└── tests/                        # Reporter tests
```

## Architecture: Datalayer

### Entry Point: `SleeperLeagueData`

**File:** `datalayer/sleeper_data/sleeper_league_data.py`

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

### Query Return Shapes

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

### Load Flow (what `data.load()` does)

1. Creates in-memory SQLite (`check_same_thread=False` for async)
2. Fetches league metadata, users, rosters, NFL state → normalizes → inserts
3. Seeds draft picks (roster × 3 seasons × rounds), applies traded picks
4. Fetches all players → inserts
5. For each week 1..effective_week: matchups → MatchupRows + PlayerPerformances + Games; transactions → TransactionMoves
6. Derives standings from roster metadata
7. Stores SeasonContext (computed_week, override_week, effective_week)

### SQLite Schema (13 tables)

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

All models defined in `datalayer/sleeper_data/schema/models.py`. DDL with indexes in `schema/ddl.py`.

### Name Resolution

Query methods accept `roster_key` (team name, manager name, or roster_id as string) and `player_key` (player name or player_id). Resolution is case-insensitive with ambiguity handling. Implementation in `queries/_resolvers.py`.

### Guarded SQL (`run_sql`)

- Only `SELECT` allowed — blocks INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, REPLACE, PRAGMA
- Auto-adds `LIMIT` if missing
- Returns `{columns, rows, row_count}`
- Implementation in `queries/sql_tool.py`

## Architecture: Reporter Agent

### Two-Phase Pipeline

**Phase 1 — Research** (`ResearchAgent`): Has full tool access. Iteratively queries the datalayer, builds a `ReportBrief` containing verified `Fact` objects and `Storyline` narratives. All tool calls logged in `ResearchLog`.

**Phase 2 — Draft** (`DraftAgent`): No tool access. Writes the article purely from the `ReportBrief`, applying configured voice and style. Cannot hallucinate data because it can only reference facts from the brief.

### Key Types

**ReportConfig** (`reporter/agent/config.py`): What to write.
- `time_range` (TimeRange): week_start, week_end
- `voice` (str): "sports columnist", "snarky columnist", "hype broadcaster", etc.
- `tone` (ToneControls): snark_level 0-3, hype_level 0-3
- `bias_profile` (BiasProfile): favored_teams, disfavored_teams, intensity 0-3
- `focus_hints`, `focus_teams`, `avoid_topics`, `length_target`, `custom_instructions`

**ReportBrief** (`reporter/agent/schemas.py`): Research output, draft input.
- `facts: list[Fact]` — Atomic verified claims with `data_refs` and `numbers`
- `storylines: list[Storyline]` — Narrative threads with `supporting_fact_ids` and priority
- `outline: list[Section]` — Planned article structure
- `style: ResolvedStyle`, `bias: ResolvedBias`

**ArticleOutput** (`reporter/agent/schemas.py`): Final output.
- `article` (str): Markdown article
- `config`, `brief`, `research_log`, `verification`

### Tool System

**Tool definitions** are in `datalayer/tools.py` as `SLEEPER_TOOLS` (OpenAI function-calling format, 16 tools). `create_tool_handlers(data)` returns a `dict[str, Callable]` mapping tool names to `SleeperLeagueData` methods.

The reporter's `ResearchToolAdapter` (`reporter/tools/sleeper_tools.py`) wraps these handlers with logging. `create_tool_registry()` (`reporter/tools/registry.py`) converts them to OpenAI Agents SDK `Tool` objects.

### Prompts

All prompt templates live in `reporter/prompts/`:
- `research_agent.md`, `draft_agent.md` — Phase-specific system prompts
- `system_base.md` — Core reporter identity and rules
- `brief_building.md`, `drafting.md`, `verification.md` — Phase guidelines
- `bias/bias_rules.md` — Bias framing rules

### Programmatic Usage

```python
from reporter.agent.workflows import generate_report

output = generate_report(
    "Write a weekly recap",
    week=8,
    voice="snarky columnist",
    snark_level=2,
    favored_teams=["Team Taco"],
)
print(output.article)
```

## Design Principles

- **Fresh load every run**: No persistence; Sleeper API is source of truth
- **Dataclasses as schema**: `schema/models.py` is the single source of truth for entity shape
- **Query-time joins**: Names resolved at query time, not denormalized into storage
- **Brief-first writing**: Research produces a verified artifact before any drafting happens
- **Bias = framing only**: Bias changes word choice and emphasis, never facts or numbers
- **Guarded SQL**: Agent can explore freely with SELECT-only + auto-LIMIT
- **Full observability**: ResearchLog captures every tool call, reasoning step, and timing

## Design Docs

Detailed design rationale lives in:
- `datalayer/docs/architecture.md` — High-level overview
- `datalayer/docs/01_datalayer.md` — Core data layer design, schema, startup flow
- `datalayer/docs/02_surfacing_names.md` — Name resolution strategy
- `datalayer/docs/03_picks.md` — Draft pick ownership tracking
- `datalayer/docs/04_transactions.md` — Transaction + pick metadata design
- `datalayer/docs/05_player_performances.md` — Player-level scoring extraction
- `reporter/docs/design.md` — Original reporter design (historical reference)
- `reporter/docs/redesign_iterative_research.md` — Iterative research architecture (current)
