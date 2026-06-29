# Reporter Memory

`reporter_memory` stores reporter-generated narrative memory across runs.

It is separate from `datalayer`: Sleeper data remains freshly loaded into
in-memory SQLite, while narrative context is persisted in `.data/context.db`.

## Package Contents

- `context_store.py` — `ContextStore` and schema version `3`.
- `context_tools.py` — legacy-style memory tool specs and handlers.
- `tests/` — store and scoping regression tests.

## Schema Behavior

Storyline identity is scoped by `(league_id, season, id)`. History and persisted
facts are also scoped by league and season, so the same storyline ID can safely
exist in different leagues or seasons.

Schema `2.1` context databases are migrated in place. Older schemas are not
supported and should be deleted or recreated if the store reports an unsupported
schema version.

## Usage

```python
from reporter_memory import ContextStore

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
```

Reporter v2 registers model-facing persistent tools from
`reporter_v2/runner/tools/persistent_tools.py`; direct use of `ContextStore` is
mainly for scripts, tests, and skills that operate outside the v2 runner.
