# Reporter V2 — Runner Design

## Goal

Replace the rigid multi-agent pipeline of reporter v1 with a single model loop
that flexibly decides what to do next. The runner is model-agnostic via
`litellm.acompletion()` and uses tool calls to drive research, drafting, and
verification without hard-coded phase transitions.

## Why V2

V1's pipeline is strictly linear: curation → research → drafting. Each phase runs
to completion before the next begins. This breaks down when the task demands
iteration — the model can't backtrack to research during drafting, can't fix errors
during verification, and can't interleave research with storyline curation.

V2 solves this with a single model loop. The model loads any procedure at any time,
switches freely between research/storyline/drafting/verification, and backtracks
when needed. The cost is context pressure — everything accumulates in one
conversation. The artifact system manages that cost.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Runner Loop                       │
│                                                     │
│  System Prompt (lean: identity + tool index)        │
│                                                     │
│  while not done:                                    │
│    response = completion(model, messages, tools)    │
│    if tool calls:                                   │
│      append assistant tool_call message             │
│      execute tools                                  │
│      append tool result messages                    │
│    else:                                            │
│      done = True                                    │
└─────────────────────────────────────────────────────┘
```

## Key Decisions

### Procedures replace, not stack

`load_procedure()` compacts the previous procedure's tool result and appends the
new one. Only one procedure is active at a time. History is derived from the
RunLog. The compact placeholder preserves chat-completions tool-call history
without carrying obsolete procedure text forward.

**Available procedures:** `research`, `storyline`, `drafting`, `verification`

### Typed artifacts, not generic

The brief and article are hard-coded typed artifacts with validation
(`save_fact()` rejects empty `data_refs`, `save_storyline()` validates fact-ID
references). A generic `save_artifact(name, blob)` can't enforce these contracts.

### Artifacts as shared state

The brief and article are in-memory objects outside the conversation. Tools
read/write them directly. On procedure switch, the model calls `read_brief()` or
`read_article()` to reload compressed state. Artifacts are the checkpoint;
conversation history is ephemeral.

### Staleness tracking

The brief has a `revision` counter. Outline and storylines record
`revision_at_set`. `read_brief()` flags when the outline is stale relative to
the current revision. The model decides whether to act on the signal.

### No active compaction (yet)

Deferring context window compaction until we see real conversations. Tool call
limits (soft 40, hard 50) cap growth. The brief already compresses the main
pressure point (research → drafting: ~15-20k tokens of raw data → ~500-1000
tokens of structured facts).

### RunLog as single source of truth

Six event types: `procedure_switch`, `tool_call`, `artifact_write`, `model_text`,
`guardrail`, `completion`. Streams to disk in real-time. `procedure_history` is
derived from the log — no duplicate state.

### Runner state shape

```
ArtifactStore:  brief + article
ProcedureState: active procedure (history derived from RunLog)
RunLog:         all events
```

Tools receive only the slice of state they need — brief tools get
`ArtifactStore` + `RunLog`, datalayer tools get `FrozenLeagueData`, persistent
tools get `reporter_memory.ContextStore`.

## Tool Inventory

| Category | Tools |
|----------|-------|
| **Procedure** | `load_procedure` |
| **Brief** | `save_fact`, `save_storyline`, `set_outline`, `read_brief`, `set_style`, `set_bias` |
| **Article** | `write_section`, `read_article`, `read_section`, `rewrite_section`, `set_section_order`, `submit_article` |
| **Datalayer** (18) | `league_snapshot`, `standings`, `week_games`, `week_player_leaderboard`, `season_leaders`, `bench_analysis`, `transactions`, `team_dossier`, `team_game`, `team_schedule`, `roster_at_cutoff`, `roster_snapshot`, `team_transactions`, `player_summary`, `player_weekly_log`, `playoff_bracket`, `team_playoff_path`, `run_sql` |
| **Persistent context** | `save_persistent_storyline`, `save_team_context`, `save_league_note`, `load_persistent_storylines`, `load_team_context`, `load_league_notes` |

Persistent context is implemented in `reporter_memory/`, not `datalayer/`.
Schema `3` scopes storylines, history, persisted facts, events, triggers, and
access records by league and season. Schema `2.1` databases are migrated in
place; older schemas remain unsupported.

## Example Flow

User: `"snarky weekly recap for week 8, roast Team Taco"`

```
 1. load_procedure("storyline")
 2. load_persistent_storylines() / load_team_context()
 3. load_procedure("research")
 4. league_snapshot(week=8) / week_games(week=8) / standings()
 5. team_game("Team Taco", week=8) / week_player_leaderboard(week=8)
 6. save_fact(...) × N
 7. save_storyline("Taco Tuesday Meltdown", ...)
 8. set_outline([...]) / set_style(...) / set_bias(...)
 9. save_persistent_storyline(...)
10. load_procedure("drafting")
11. read_brief()
12. write_section("opening") / write_section("taco_meltdown") / ...
13. load_procedure("verification")
14. read_article() / read_brief()
15. rewrite_section("around_the_league", "...corrected...")
16. submit_article()
```

## Guardrails

| Guardrail | Mechanism |
|-----------|-----------|
| Tool call limit | Soft (40): system note. Hard (50): force wrap-up. |
| Turn limit | Max 60 loop iterations. |
| SELECT-only SQL | `run_sql` validates queries (inherited from datalayer). |
| No hallucination | Procedure instructions + brief-as-source-of-truth. |
| Bias as framing | Procedure instructions (same rules as v1). |
