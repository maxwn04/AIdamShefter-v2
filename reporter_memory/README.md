# Reporter Memory

`reporter_memory` stores reporter-generated narrative memory across runs.

It is separate from `datalayer`: Sleeper data remains freshly loaded into
in-memory SQLite, while narrative context is persisted in `.data/context.db`.

## Package Contents

- `schema.py` — `SCHEMA_VERSION` and SQLite DDL (schema `3`).
- `context_store.py` — `ContextStore` facade composing store mixins.
- `store/` — persistence internals:
  - `base.py` — connection + migration
  - `serializers.py` — row/JSON helpers
  - `storylines.py` — storylines, team/league context, history, facts
  - `events.py` — events, entities, storyline-event links
  - `triggers.py` — callback triggers
  - `access.py` — memory access recording
  - `fts.py` — FTS5 sync/search/rebuild
- `search/` — agent-facing retrieval:
  - `pipeline.py` — `search_story_memory` orchestrator
  - `candidates.py` — `get_memory_candidate`
  - `discovery.py` — trigger/entity/team/FTS matchers
  - `ranking.py` — candidate merge, hydrate, scoring
  - `verification.py` — verification planning + fact-link helpers
- `context_tools.py` — legacy-style memory tool specs and handlers.
- `tests/` — store and search regression tests.

## Schema Behavior

Storyline identity is scoped by `(league_id, season, id)`. History and persisted
facts are also scoped by league and season, so the same storyline ID can safely
exist in different leagues or seasons.

Schema `2.1` context databases are migrated in place. Older schemas are not
supported and should be deleted or recreated if the store reports an unsupported
schema version.

## Usage

```python
from reporter_memory import ContextStore, search_story_memory

store = ContextStore(".data/context.db", league_id="123", season="2026")
store.upsert_storyline(
    {
        "id": "story_2026_w8_alpha_surge",
        "headline": "Alpha Keeps Climbing",
        "summary": "Alpha's playoff push now has real momentum.",
        "status": "active",
        "priority": 1,
        "tags": ["surge", "playoff-race"],
        "team_ids": [1],
    },
    week=8,
)

leads = search_story_memory(
    store,
    week=8,
    query="playoff surge",
    current_entities=[{"entity_type": "team", "entity_id": "1"}],
)
```

Reporter v2 registers model-facing tools from
`reporter_v2/runner/tools/memory_tools.py` (search/write/verification) and
`reporter_v2/runner/tools/persistent_tools.py` (legacy load/save). Direct use of
`ContextStore` / `search_story_memory` is mainly for scripts, tests, and skills
that operate outside the v2 runner.
