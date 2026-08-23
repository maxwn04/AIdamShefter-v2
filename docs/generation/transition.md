# Reporter V2 to Platform Generation Transition

## Starting Point

Reporter V2 already has the desired content engine:

- one async `generate_article` composition function;
- one single-loop `Runner`;
- a lightweight retry/fallback `CompletionClient`;
- reporter-owned `ToolRegistry` and tool handlers;
- typed in-memory brief/article state that the platform copy will replace with
  path-addressed Markdown artifacts;
- procedure replacement semantics;
- a diagnostic `RunLog`; and
- prompt/procedure files with broad test coverage.

Its legacy production composition still assumes:

- `SleeperLeagueData` owns data loading and exposes private SQLite details;
- `ContextStore` is the persistent memory authority;
- the CLI owns output files and process lifecycle;
- retries/fallbacks are invisible outside `CompletionClient`;
- tool results are logged only as truncated summaries; and
- no durable generation aggregate owns the run.

The frozen datalayer runtime is merged. A separate reporter-adapter PR proved
that the 18 model-facing handlers can delegate directly to `FrozenLeagueData`,
but that PR was closed so integration can happen in a new reporter copy. Its
implementation is prior art and compatibility evidence, not merged architecture.
Snapshot resolution and generation pinning remain outside the reporter adapter.

## Preserve, Modify, Remove, Add

### Preserve behaviorally

- `generate_article` as the reporter composition entry point;
- `Runner.run` single-loop behavior;
- parallel tool-batch execution;
- `ToolRegistry` registration and context-tool pattern;
- `CompletionSettings`, retry classification, delay, and fallback order;
- message/tool-call normalization helpers;
- `ReportConfig` and non-artifact runner models;
- procedure and other non-artifact tool names/schemas;
- prompts and procedures;
- procedure replacement versus append mode;
- explicit artifact submission as the reporter stop signal; and
- local `RunLog` for test/debug visibility.

### Modify internally

- copy code from `reporter_v2/` to `backend/services/reporter/` while keeping
  the legacy tree unchanged as a comparison baseline;
- change generator data input from `SleeperLeagueData` to
  `FrozenLeagueData`;
- change generator memory input from `ContextStore` to
  `GenerationMemoryContext`;
- add a generation-scoped execution recorder to completion, runner, and
  artifact tool contexts;
- pass turn/attempt identity through the completion adapter without exposing it
  to the provider;
- persist full tool results rather than relying on `RunLog` summaries;
- persist provider token usage per attempt;
- replace section-specific editing with generic path-addressed artifact tools;
- mirror complete Markdown mutations to immutable reporting artifact versions;
- move successful memory commit/discard out of the reporter and into
  `GenerationService`.

### Remove from the production path

- `SleeperLeagueData.load()` and source fetching during report generation;
- private `_query_conn` access for metadata or roster resolution;
- legacy `ContextStore` reads/writes and memory lifecycle helpers;
- structured brief/section state and its specialized model-facing tools;
- week-based article filenames as canonical output identity;
- production dependence on `.output` run-log JSON files; and
- CLI ownership of the durable generation lifecycle.

### Add

- per-resource reporting objects and managers;
- deterministic manifest construction and hashing;
- `GenerationService` submission/start/execute/finalize/fail workflow;
- provider-attempt token/call recording;
- full tool-call recording;
- durable versioned artifacts;
- raw Markdown `research/brief.md` and `article.md` plus `ReporterOutput`;
- reporter adapters for frozen data and typed memory;
- API polling/read surfaces; and
- a thin worker/process entry point.

## Component Reuse Map

| Current component | Target | Disposition |
| --- | --- | --- |
| `reporter_v2/runner/article_generator.py` | new `backend/services/reporter/generator.py` copy | Preserve composition shape; replace data/memory dependencies and remove production file ownership |
| `reporter_v2/runner/runner.py` | new `backend/services/reporter/runner/runner.py` copy | Preserve loop; add execution recording calls only in the new package |
| `reporter_v2/runner/completion.py` | reporter completion adapter | Preserve retry/fallback; instrument every actual attempt and normalize usage |
| `reporter_v2/runner/models.py` | reporter runner models | Move with minimal changes |
| `reporter_v2/runner/schemas.py` | reporter artifact schemas | Replace section/brief schemas with generic artifact snapshots and `ReporterOutput` in the artifact-refactor slice |
| `reporter_v2/runner/state.py` | reporter runner state | Replace specialized state with the path-addressed `ArtifactStore`; add recorder reference to tool context rather than database state |
| `reporter_v2/runner/run_log.py` | reporter diagnostics | Preserve as non-authoritative local view |
| brief/article tools | generic reporter artifact tools | Replace after copy characterization with the settled path/revision contract |
| procedure tools | reporter tools | Preserve model-facing contracts |
| datalayer tools | reporter datalayer adapter | Already adapted to `FrozenLeagueData`; move mechanically |
| persistent/memory tools | reporter memory adapter | Replace legacy backend; compatibility decided tool by tool below |
| `reporter_v2/app/runner.py` | API/worker plus temporary CLI | Decompose; no canonical output filenames or direct loading in production |
| `memory_lifecycle.py` | `GenerationService` finalization | Remove after typed-memory cutover |

## Non-Memory Tool Compatibility

### Artifact tools

The copied reporter initially preserves its legacy tools only for
characterization. The artifact-refactor slice then retires the specialized
brief tools (`save_fact`, `save_memory_callback`, `save_storyline`,
`set_outline`, `read_brief`, `set_style`, `set_bias`) and article tools
(`write_section`, `read_article`, `read_section`, `rewrite_section`,
`set_section_order`, `submit_article`). They are replaced by:

- `list_artifacts()`;
- `read_artifact(path)`;
- `create_artifact(path, content)`;
- `edit_artifact(path, old_text, new_text, expected_revision)`; and
- `submit_artifact(path, expected_revision)`.

The required run-local artifacts are raw UTF-8 Markdown at
`research/brief.md` and `article.md`. `edit_artifact` is a revision-checked
literal find-and-replace: `old_text` must occur exactly once, and there is no
`replace_all` mode. Successful creates and edits record complete immutable
snapshots. Reads do not mutate state. `submit_artifact` accepts the current
revision of `article.md`, ends the reporter loop, and produces
`ReporterOutput(submitted_path, artifacts)`; it does not independently mark the
generation succeeded or append a final copy.

### Procedure tool

Preserve `load_procedure` and the four procedure names: `research`,
`storyline`, `drafting`, and `verification`.

### Datalayer tools

Recreate the proven closed-adapter contract in the new reporter package:

- `league_snapshot`
- `week_games`
- `team_game`
- `week_player_leaderboard`
- `team_dossier`
- `team_schedule`
- `roster_at_cutoff`
- `roster_snapshot`
- `transactions`
- `team_transactions`
- `bench_analysis`
- `standings`
- `player_summary`
- `player_weekly_log`
- `season_leaders`
- `playoff_bracket`
- `team_playoff_path`
- `run_sql`

`roster_at_cutoff` is the intentional replacement for legacy
`roster_current`. The reporter receives one already-open runtime; no tool may
refresh or switch snapshots. Compatibility tests should be rebuilt on current
`main` rather than making the closed adapter branch a stack dependency.

## Memory Tool Compatibility

The typed memory redesign changes canonical meaning. A compatibility wrapper is
valid only when it can produce the same user-visible semantics without hidden
state or weakened validation.

### Rich memory tools

| V2 tool | Typed-memory capability | Decision status |
| --- | --- | --- |
| `search_story_memory` | `GenerationMemoryContext.search(MemoryRetrievalRequest)` | Preserve name if the old query fields can be narrowed explicitly; current events, trigger hints, filters, and result shape need a written mapping |
| `get_memory_candidate` | Search already returns hydrated canonical matches and optional expansions | Open: context has no exact candidate-fetch operation and old owner string IDs do not match UUID item/version identity |
| `save_memory_event` | `propose_event(EventContent)` | Change required: typed v1 accepts only trade and matchup payloads and different confidence/receipt rules |
| `upsert_storyline_memory_card` | `propose_storyline` or `replace_storyline` | Change required: typed memory uses explicit create/replace, UUID identity, exact expected revision, and typed evidence |
| `save_storyline_trigger` | `propose_trigger` or `replace_trigger` | Change required: typed trigger discriminators and target IDs are stricter than the legacy generic condition object |
| `mark_memory_used` | No canonical access-history resource in the new design | Cannot preserve as a durable write; remove, redefine as non-canonical telemetry, or add a separately approved feature |
| `plan_memory_verification` | No memory-service equivalent; verification can remain reporter-local | Open: decide whether it remains a pure brief/datalayer planning tool and define inputs over typed hydrated memory |
| `record_memory_verification` | No access-history/verification-record resource; brief callbacks remain run-local | Open: decide whether it mutates only the brief, proposes typed fact/storyline changes, or is removed |

### Legacy persistent tools

| V2 tool | Typed-memory capability | Decision status |
| --- | --- | --- |
| `save_persistent_storyline` | typed storyline create/replace | Prefer removal after migrating prompts to the richer typed tool; preserving alias/upsert semantics would hide revision conflicts |
| `save_team_context` | franchise-scoped `ContextNoteContent` | Adaptable only after an authoritative roster-key-to-franchise resolver exists |
| `save_league_note` | competition-scoped `ContextNoteContent` | Adaptable, but key/value input must map explicitly to typed identity plus narrative/status/tags |
| `load_persistent_storylines` | filter-only pinned search for storyline kind | Adaptable with a documented response-shape change |
| `load_team_context` | filter-only pinned search for context-note kind/entity | Adaptable after durable team identity resolution is available |
| `load_league_notes` | filter-only pinned search for competition context notes | Adaptable with a documented response-shape change |

No implementation should register both legacy and new write handlers against
different stores. The cutover uses typed memory as the only canonical authority.

## Minimal Runner Changes

The runner should continue to look conceptually like:

```python
while turn < max_turns and not submitted:
    response = await client.complete(...)
    if tool_calls:
        execute_batch(tool_calls)
        continue
    if text:
        record_text(text)
    break
```

Required additions are orthogonal:

- pass turn identity to the completion adapter;
- receive or resolve the successful AI-call identity for tool provenance;
- begin/finish each tool call around the existing handler;
- expose generic artifact state and recorder access through `ToolContext`; and
- emit progress updates through the recorder.

The runner must not learn about snapshots, memory revisions, SQLAlchemy,
generation status transitions, HTTP, or worker claims.

## CLI Transition

The current CLI is useful for behavior characterization but is not the target
production composition. Transition in two steps:

1. keep the legacy CLI untouched while a thin new-package test/CLI harness
   constructs an in-memory/no-op recorder during the copy;
2. switch the platform CLI/worker to submit/execute durable generations, then
   remove direct `SleeperLeagueData` and `ContextStore` composition.

Generated files may remain a developer convenience, but generation ID plus the
`article.md` artifact and selected version become the canonical address of an
article.

## Exit Criteria

The transition is complete when:

- production imports no `reporter_v2`, legacy datalayer facade, or
  `reporter_memory.ContextStore`;
- the same fixture request produces compatible reporting behavior through the
  moved reporter before the explicit artifact-contract refactor;
- the reporter can execute only against its pinned frozen snapshot and pinned
  memory context;
- every provider attempt and tool call has complete durable telemetry;
- token usage and immutable Markdown artifact versions are persisted;
- failed runs discard typed memory proposals;
- succeeded runs follow the settled finalization contract; and
- the API/worker invoke the same `GenerationService` rather than duplicating
  orchestration.
