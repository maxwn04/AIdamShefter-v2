# AIda Skills Architecture

This document describes the current AIda skill workflow after the reporter
memory refactor.

## Current Split

- `sleeperdl` remains the CLI for Sleeper data snapshots and factual queries.
- `reporter_memory` owns persistent narrative memory in `.data/context.db`.
- `reporter_v2` is the supported reporter runtime.
- `reporter` v1 is deprecated and retained only as historical source.

Do not use `sleeperdl context` or `sleeperdl memory`; those datalayer commands
were removed when memory moved to `reporter_memory/`.

## AIda Report Writer Skill

The `.agents/skills/aida-report-writer/SKILL.md` workflow uses:

1. `sleeperdl load --output <snapshot> --refresh` to create one Sleeper snapshot
   per article run.
2. `sleeperdl query ... --snapshot <snapshot>` for all factual research.
3. Short Python snippets using `reporter_memory.ContextStore` to read and write
   persistent storylines, team context, league notes, and persisted facts.
4. A compact run brief and final Markdown article in the run directory.

Memory is continuity, not evidence. Any remembered storyline used in prose must
be verified against the current Sleeper snapshot before drafting.

## Memory Store

Default DB path:

```text
.data/context.db
```

Schema:

- Current schema version: `2.1`.
- Storyline identity is scoped by `(league_id, season, id)`.
- Storyline history and persisted facts are scoped by league and season.
- Legacy DB schemas are not migrated; delete or recreate old context DBs.

Primary API:

```python
from reporter_memory import ContextStore

store = ContextStore(".data/context.db", league_id=league_id, season=season)
```

The skills should derive `league_id` and `season` from the same Sleeper snapshot
used for factual research.

## Factual Query Commands

Create or refresh a snapshot:

```bash
sleeperdl load --output "$snapshot" --refresh
```

Run factual queries:

```bash
sleeperdl query league_snapshot week=8 --snapshot "$snapshot"
sleeperdl query standings week=8 --snapshot "$snapshot"
sleeperdl query week_games week=8 --snapshot "$snapshot"
sleeperdl query transactions week_from=8 week_to=8 --snapshot "$snapshot"
sleeperdl query team_game roster_key="Team Taco" week=8 --snapshot "$snapshot"
sleeperdl query player_weekly_log player_key="Patrick Mahomes" --snapshot "$snapshot"
sleeperdl query run_sql query="SELECT team_name, wins FROM standings WHERE week = 8" --snapshot "$snapshot"
```

Use `sleeperdl tools` to inspect available factual tools.

## Memory Read Pattern

Read full memory for the snapshot scope:

```bash
python - "$snapshot" <<'PY'
import json
import sys

from datalayer.sleeper_data import SleeperLeagueData
from reporter_memory import ContextStore

snapshot = sys.argv[1]
data = SleeperLeagueData.from_file(snapshot)
season = str(data.run_sql("SELECT season FROM leagues LIMIT 1")["rows"][0][0])
store = ContextStore(".data/context.db", league_id=data.league_id, season=season)
context = store.get_full_context()
print(json.dumps({
    "has_previous_context": bool(
        context["storylines"] or context["team_context"] or context["league_context"]
    ),
    **context,
}, indent=2, default=str))
store.close()
PY
```

Enrich selected storylines:

```bash
python - "$snapshot" story_alpha_surge story_trade_fallout <<'PY'
import json
import sys

from datalayer.sleeper_data import SleeperLeagueData
from reporter_memory import ContextStore

snapshot, *storyline_ids = sys.argv[1:]
data = SleeperLeagueData.from_file(snapshot)
season = str(data.run_sql("SELECT season FROM leagues LIMIT 1")["rows"][0][0])
store = ContextStore(".data/context.db", league_id=data.league_id, season=season)
print(json.dumps(store.get_enriched_storylines(storyline_ids), indent=2, default=str))
store.close()
PY
```

## Memory Write Pattern

Skills should create a compact JSON file of memory updates after drafting, then
apply it with `reporter_memory`.

Example update file:

```json
{
  "storylines": [
    {
      "id": "story_2026_w8_alpha_surge",
      "headline": "Alpha Keeps Climbing",
      "summary": "Alpha extended its surge with another high-scoring win and is now a playoff threat.",
      "status": "active",
      "priority": 1,
      "tags": ["surge", "playoff-race"],
      "team_keys": ["Alpha"]
    }
  ],
  "team_context": [
    {
      "roster_key": "Alpha",
      "narrative": "Alpha is surging behind consistent top-end scoring.",
      "outlook": "surging"
    }
  ],
  "league_notes": [
    {
      "key": "week_8_theme",
      "value": "Week 8 was defined by playoff volatility and bench-point regret."
    }
  ],
  "persisted_facts": [
    {
      "storyline_id": "story_2026_w8_alpha_surge",
      "facts": [
        {
          "id": "fact_alpha_w8_score",
          "claim_text": "Alpha beat Beta 142.3 to 98.7 in Week 8.",
          "data_refs": ["team_game:Alpha,week=8"],
          "numbers": {"alpha_points": 142.3, "beta_points": 98.7, "week": 8},
          "category": "score"
        }
      ]
    }
  ]
}
```

Apply updates:

```bash
python - "$snapshot" "$run_dir/context_updates.json" "$week" <<'PY'
import json
import sys

from datalayer.sleeper_data import SleeperLeagueData
from datalayer.sleeper_data.queries._resolvers import resolve_roster_id
from reporter_memory import ContextStore

snapshot, updates_path, week_raw = sys.argv[1:]
week = int(week_raw)
data = SleeperLeagueData.from_file(snapshot)
season = str(data.run_sql("SELECT season FROM leagues LIMIT 1")["rows"][0][0])
store = ContextStore(".data/context.db", league_id=data.league_id, season=season)
updates = json.loads(open(updates_path, encoding="utf-8").read())

def resolve_team_ids(team_keys):
    team_ids = []
    for key in team_keys:
        result = resolve_roster_id(data._query_conn, data.league_id, key)
        if result.get("found"):
            team_ids.append(int(result["roster_id"]))
    return team_ids

for storyline in updates.get("storylines", []):
    payload = dict(storyline)
    payload["team_ids"] = resolve_team_ids(payload.pop("team_keys", []))
    store.upsert_storyline(payload, week=week)

for note in updates.get("team_context", []):
    team_ids = resolve_team_ids([note["roster_key"]])
    if team_ids:
        store.upsert_team_context(
            team_ids[0],
            note["narrative"],
            note.get("outlook"),
            week=week,
        )

for note in updates.get("league_notes", []):
    store.upsert_league_context(note["key"], note["value"], week=week)

for fact_group in updates.get("persisted_facts", []):
    store.persist_facts(
        fact_group.get("facts", []),
        fact_group["storyline_id"],
        week=week,
    )

store.close()
PY
```

## Skill Responsibilities

- Read memory before research.
- Treat memory as leads and continuity only.
- Verify all current claims with `sleeperdl query` outputs.
- Build a brief before drafting.
- Persist only durable arcs that can matter in later weeks.
- Prefer resolving or ignoring stale arcs over repeating them uncritically.

## Season Simulation

The `.agents/skills/aida-season-simulator/SKILL.md` skill resets
`.data/context.db`, then runs `aida-report-writer` sequentially week by week.
The sequential order matters because each week reads the memory written by
previous weeks.
