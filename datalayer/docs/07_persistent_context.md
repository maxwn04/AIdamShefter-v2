# Reporter Memory Boundary

Persistent reporter memory no longer belongs to `datalayer`.

`datalayer` owns Sleeper API fetch, normalization, in-memory SQLite loading, and
factual query tools. Narrative memory now lives in `reporter_memory/` so it can
evolve independently from Sleeper data loading.

## Current Ownership

- `reporter_memory/context_store.py` — `ContextStore`, schema creation, reads,
  writes, stale marking, history, and persisted facts.
- `reporter_memory/context_tools.py` — legacy-style memory tool definitions and
  handlers used by reporter integrations.
- `reporter_v2/runner/tools/persistent_tools.py` — v2 tool surface exposed to
  the model.
- `.data/context.db` — default file-backed SQLite database for reporter memory.

`datalayer/context_store.py`, `datalayer/context_tools.py`, `sleeperdl context`,
and `sleeperdl memory` have been removed.

## Schema

Canonical memory schema docs live in `reporter_memory/`. Current schema version
is `3` (`reporter_memory.schema.SCHEMA_VERSION`).

The store supports multiple leagues and seasons in the same SQLite file. Storyline
identity is scoped by `(league_id, season, id)`, and all storyline history and
persisted fact lookups are scoped by the same league and season. Reusing a
storyline ID in another league or season is valid and isolated.

Main tables:

- `storylines` — Persistent narrative threads with lifecycle status, priority,
  tags, team IDs, week created, and week last updated.
- `team_context` — One row per `(league_id, season, roster_id)` with narrative
  and outlook.
- `league_context` — Key/value league notes scoped by league and season.
- `storyline_history` — Snapshots of previous storyline state on update.
- `persisted_facts` — Verified facts attached to a storyline for continuity.
- `context_meta` — Schema version metadata.

Legacy schema versions are intentionally not migrated. If an old `.data/context.db`
exists, delete or recreate it.

## Reporter V2 Flow

1. `reporter_v2` creates a `ContextStore` using the loaded Sleeper league ID and
   season.
2. The runner registers persistent tools when a context store is available:
   `save_persistent_storyline`, `save_team_context`, `save_league_note`,
   `load_persistent_storylines`, `load_team_context`, and `load_league_notes`.
3. Memory is treated as narrative context and research leads, not factual truth.
4. Current article facts still come from datalayer query tools and the v2 brief.

## Datalayer Contract

The datalayer should not import or re-export reporter memory code. It may provide
factual lookup support used by reporter memory callers, such as roster resolution,
but memory persistence remains outside the datalayer package.
