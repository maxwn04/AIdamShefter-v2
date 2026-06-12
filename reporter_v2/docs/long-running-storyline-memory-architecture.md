# Long-Running Storyline Memory: Architecture

## Purpose

Build a real memory layer for `reporter-v2`: source-backed events, entity-aware
search, callback triggers, and tools that support agentic storyline discovery.

This remodel can be implemented separately from the prompting pass. The prompt
pass improves behavior with the current schema; this architecture gives the agent
better memory primitives.

## Design Decisions

- Memory search returns leads, not article-ready facts.
- The agent chooses which leads are interesting enough to verify and use.
- Events are evidence. Storylines are narrative reflections.
- Exact entities and callback triggers are the primary recall signals.
- FTS ships before embeddings because names, tags, players, teams, and phrases
  matter heavily in fantasy-football memory.
- Embeddings are optional and should index rich memory documents, not just titles
  and summaries.
- SQLite remains the near-term source of truth.
- Memory should move out of `datalayer` into `reporter_memory/`.
- If the datalayer later becomes persistent SQL, memory may share the same
  physical database while keeping a separate logical module and table namespace.

## Package Boundary

Move memory implementation to `reporter_memory/`.

Reasoning:

- `datalayer` owns Sleeper fetch, normalize, load, and factual queries.
- Memory owns reporter-generated narrative state, source-backed callbacks,
  retrieval, and usage history.
- Reporter v1, reporter v2, and CLI inspection can share one memory package.

Keep compatibility shims:

- `datalayer/context_store.py` re-exports `ContextStore` and `SCHEMA_VERSION`.
- `datalayer/context_tools.py` re-exports legacy context tools.
- `sleeperdl context` and `sleeperdl memory` keep working.

If memory later shares a DB with persistent datalayer tables, keep logical
separation through table prefixes or schemas:

- `sleeper_*` for canonical Sleeper data;
- `reporter_memory_*` for narrative memory.

## Storage Model

Increment the memory store to schema v3.

All memory queries must scope by `(league_id, season, id)` or use globally
namespaced IDs. Existing history/fact lookups should be fixed so repeated IDs
cannot cross-contaminate leagues or seasons.

### `storylines`

Narrative cards. Keep existing fields and add:

- `arc_type`
- `importance`
- `origin_week`
- `future_callback_condition`
- `last_accessed_week`
- `last_accessed_at`

Semantics:

- `priority`: article planning rank, where `1` is most important.
- `importance`: retrieval weight, where higher is more important.

### `story_events`

Append-only source-backed event memory.

Key fields:

- scoped `id`
- `week`
- `event_type`: `trade`, `matchup`, `waiver`, `playoff`, `lineup`, `receipt`,
  `standing`
- `headline`
- `summary`
- `importance`
- `confidence`: `verified`, `inferred`, `needs_verification`
- `source_refs_json`
- `numbers_json`
- optional `transaction_id`
- optional `matchup_id`
- access timestamps

Use events for reusable evidence: trades, matchup receipts, waiver pickups,
bench mistakes, playoff reversals, and standings swings.

### `story_event_entities`

Normalized links from events to entities:

- `team`
- `manager`
- `player`
- `matchup`
- `transaction`

Use canonical IDs where available. Names are display fields or fallback aliases,
not durable identity.

Useful roles:

- `buyer`
- `seller`
- `winner`
- `loser`
- `asset_sent`
- `asset_received`
- `former_team`
- `current_team`

### `storyline_event_links`

Join narrative cards to source-backed events.

Link types:

- `origin`
- `update`
- `payoff`
- `callback`
- `evidence`

### `storyline_triggers`

Explicit dormant callback conditions.

Key fields:

- scoped `id`
- optional `storyline_id`
- optional `event_id`
- `trigger_type`
- `status`: `open`, `fired`, `expired`, `resolved`
- optional `target_week`
- `condition_json`
- `fire_policy`: `one_shot`, `recurring`, `until_resolved`
- `fired_week`

Define `condition_json` schemas for:

- `rematch`
- `playoff_path`
- `trade_evaluation`
- `player_against_former_team`
- `waiver_player_started`
- `standings_swing`

Triggers are recall hooks, not editorial decisions. A fired trigger should move
a candidate into the agent's attention, not directly into the article.

### `story_memory_fts`

FTS5 index over:

- owner type and ID;
- league and season;
- headline;
- summary;
- tags;
- entity text;
- trigger text.

Maintenance requirements:

- update rows when storyline/event/trigger text changes;
- rebuild rows when entity links change;
- provide a backfill method for existing DBs.

### `memory_accesses`

Durable feedback trail for retrieval and verification.

Track:

- week;
- candidate owner type and ID;
- usage: `article_callback`, `research_context`, `discarded`;
- linked brief storyline ID;
- fact links;
- reason;
- created timestamp.

This complements the verified callback layer in the run brief: the brief records
what was safe to draft, while access history helps later ranking and debugging.

### Optional `story_embeddings`

Do not ship embeddings first.

If added later:

- hide them behind an adapter;
- key by owner type, owner ID, model, version, and text hash;
- embed rich memory documents containing arc type, entities, event summaries,
  trigger text, and linked facts.

## Tool Surface

Keep existing tools for compatibility:

- `save_persistent_storyline`
- `save_team_context`
- `save_league_note`
- `load_persistent_storylines`
- `load_team_context`
- `load_league_notes`

Add search-first tools.

### `search_story_memory`

Returns memory leads for the current article.

Inputs:

- `week`
- `article_request`
- `query`
- `current_entities`
- `current_events`
- `trigger_types`
- `filters`
- `include_resolved`
- `limit`

Outputs:

- ranked candidates;
- matched entities;
- matched triggers;
- linked events;
- source refs;
- `why_relevant`;
- `why_now`;
- score components;
- verification status;
- required fact roles;
- suggested datalayer calls.

This tool prioritizes attention. It does not decide what to write.

### `get_memory_candidate`

Expands a selected candidate with:

- linked events;
- persisted facts;
- history;
- triggers;
- source refs.

Use this after `search_story_memory` instead of loading all memory.

### Brief Callback Tools

These record verified callbacks inside the run brief:

- `save_memory_callback(id, callback_type, claim_text, old_event_fact_id,
  current_event_fact_id, why_now, interestingness_reason, memory_refs, tags)`

The tool should reject callbacks unless both the older event and current payoff
already exist as saved brief facts. Speculative leads stay in research; only
verified callbacks become draftable brief material.

### Verification Tools

#### `plan_memory_verification`

Inputs:

- `candidate_id`
- `callback_id`
- `intended_callback_claim`
- `current_week`

Returns required fact roles and suggested datalayer calls.

Examples:

- original trade receipt: `transactions(week_from=3, week_to=3)`
- current payoff: `team_game(roster_key=..., week=12)`
- player trend: `player_weekly_log(player_key=..., week_from=3, week_to=12)`
- playoff implication: `playoff_bracket(...)` or `team_playoff_path(...)`

#### `record_memory_verification`

Inputs:

- `fact_links`
- `status`: `verified`, `rejected`, `needs_more_evidence`
- `reason`

Callback verification should require at least:

- `origin_receipt` or equivalent old-event fact;
- `current_payoff` or equivalent current-event fact.

### Persistence Tools

#### `save_memory_event`

Saves source-backed event evidence.

Inputs:

- `id`
- `event_type`
- `week`
- `headline`
- `summary`
- `importance`
- `confidence`
- `source_refs`
- `numbers`
- `entities`
- optional `transaction_id`
- optional `matchup_id`

If `confidence` is `verified`, require at least one structured source ref.

#### `upsert_storyline_memory_card`

Supersedes `save_persistent_storyline`, with the old tool kept as a wrapper.

Inputs:

- `id`
- `headline`
- `summary`
- `status`
- `priority`
- `importance`
- `arc_type`
- `origin_week`
- `future_callback_condition`
- `tags`
- `entities`
- `evidence_event_ids`
- `trigger_specs`

#### `save_storyline_trigger`

Inputs:

- `storyline_id`
- `event_id`
- `trigger_type`
- `target_week`
- `condition`
- `fire_policy`

#### `mark_memory_used`

Inputs:

- `candidate_id`
- `week`
- `usage`: `article_callback`, `research_context`, `discarded`
- `linked_storyline_id`
- `fact_links`
- `reason`

Updates access metadata and trigger state when appropriate.

### Post-Run Fact Persistence

V2 should automatically persist brief facts linked to storylines after article
generation, matching v1 behavior. Prefer a post-run step in `generate_article`
over a model-called tool.

## Retrieval Design

Candidate generation should combine:

1. Trigger matches:
   - rematch;
   - playoff path;
   - player against former team;
   - trade evaluation;
   - waiver/drop payoff.
2. Entity overlap:
   - same teams;
   - same players;
   - same managers;
   - same transaction;
   - same matchup.
3. FTS lexical matches:
   - names;
   - tags;
   - arc types;
   - themes like revenge, collapse, receipt, regret.
4. Optional vector matches later.

Ranking should expose components:

```text
score =
  trigger_match
  + entity_overlap
  + event_fit
  + lexical_score
  + importance
  + confidence
  + dormant_callback_boost
  + optional_vector_score
  + light_recency_bonus
  - resolved_penalty
```

Policy:

- Ranking is not editorial selection.
- Dormant arcs should not be buried by recency.
- Resolved arcs are excluded by default unless requested or explicitly triggered.
- Retrieved memories used in prose must be verified through brief facts.

## Rollout

1. Move memory implementation to `reporter_memory/` with datalayer shims.
2. Fix league/season scoping in existing memory.
3. Add v2 post-run fact persistence.
4. Add v3 event/entity/link/trigger/FTS tables.
5. Add `search_story_memory` and `get_memory_candidate`.
6. Add verified brief callback, verification, persistence, and usage tools.
7. Add optional vector search only after SQL and FTS misses are observed.

## References

- `sqlite-vec`: https://github.com/asg017/sqlite-vec
- `sqlite-vec` release note: https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html
- SQLite-Vector: https://www.sqlite.ai/sqlite-vector
- pgvector: https://github.com/pgvector/pgvector
