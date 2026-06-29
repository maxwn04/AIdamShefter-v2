# Reporter V2 Runner — Implementation Plan

The design doc (`runner-design.md`) covers the "why"; this document indexes the
"how" across 9 implementation phases. Each phase doc lives in `impl/` and contains
file paths, data structures, function signatures, and test strategies.

## Conventions

- **Pydantic BaseModel** for all schemas (matching v1's reporter layer)
- **Python 3.11+ union syntax** (`X | Y`)
- **Absolute imports** from package root (`from reporter_v2.runner.schemas import ...`)
- **`__future__.annotations`** in every module
- Persistent context imports come from `reporter_memory`, not `datalayer`

## Package Structure (Final State)

```
reporter_v2/
  __init__.py
  runner/
    __init__.py
    schemas.py          # ReportBrief, Article, Fact, Storyline, etc.
    state.py            # RunnerState, ArtifactStore, ProcedureState
    run_log.py          # RunLog, RunLogEntry
    runner.py           # The core runner loop
    entrypoint.py       # generate_article() entry point
    tools/
      __init__.py
      context.py        # ToolContext
      brief_tools.py    # save_fact, save_storyline, set_outline, read_brief, etc.
      article_tools.py  # write_section, read_article, rewrite_section, etc.
      procedure_tools.py # load_procedure
      datalayer_tools.py # 18 datalayer tool adapters
      persistent_tools.py # save/load persistent context
      registry.py       # ToolRegistry: maps names to callables + tool definitions
  procedures/
    research.md
    storyline.md
    drafting.md
    verification.md
  prompts/
    system.md           # Lean system prompt
  tests/
    __init__.py
    conftest.py
    test_schemas.py
    test_run_log.py
    test_brief_tools.py
    test_article_tools.py
    test_procedure_tools.py
    test_runner.py
    test_datalayer_tools.py
    test_persistent_tools.py
    test_integration.py

reporter_memory/
  __init__.py
  context_store.py      # ContextStore, schema 3, scoped memory tables
  context_tools.py      # legacy-style memory tool specs/handlers
  tests/
    test_context_store.py
```

## Implementation Phases

| Phase | Doc | What | Dependencies |
|-------|-----|------|--------------|
| 1 | [Core Data Models](impl/phase-1-core-data-models.md) | Pydantic schemas for brief, article, runner state | None |
| 2 | [RunLog](impl/phase-2-run-log.md) | Typed log entries, streaming to disk, derived properties | None |
| 3 | [Brief Tools](impl/phase-3-brief-tools.md) | `save_fact`, `save_storyline`, `set_outline`, `read_brief`, etc. | 1, 2 |
| 4 | [Article Tools](impl/phase-4-article-tools.md) | `write_section`, `read_article`, `rewrite_section`, `submit_article`, etc. | 1, 2 |
| 5 | [Procedure Loading](impl/phase-5-procedure-loading.md) | `load_procedure` with replacement semantics | 1, 2 |
| 6 | [Runner Loop](impl/phase-6-runner-loop.md) | Core `run()` loop, ToolRegistry, guardrails | 1–5 |
| 7 | [Datalayer Tools](impl/phase-7-datalayer-tools.md) | Adapt 18 existing datalayer tools for v2 registry | 6 |
| 8 | [Persistent Context](impl/phase-8-persistent-context.md) | Read/write `reporter_memory` storylines, team context, league notes | 6 |
| 9 | [Integration & CLI](impl/phase-9-integration-cli.md) | `generate_article()` entry point, system prompt, e2e tests | All |

## Dependency Graph

```
Phase 1 (schemas, state) ─────────┐
                                   ├── Phase 3 (brief tools)
Phase 2 (RunLog) ─────────────────┤
                                   ├── Phase 4 (article tools)
                                   │
                                   ├── Phase 5 (procedure tools)
                                   │
                                   └── Phase 6 (runner loop + registry)
                                          │
                                          ├── Phase 7 (datalayer tools)
                                          │
                                          ├── Phase 8 (persistent tools)
                                          │
                                          └── Phase 9 (entrypoint + CLI)
```

Phases 1 and 2 can run in parallel. Phases 3, 4, and 5 can run in parallel
(all depend on 1+2 but not on each other). Phase 6 depends on 3–5. Phases 7
and 8 can run in parallel after 6. Phase 9 ties everything together.

## Cross-Cutting Concerns

### How tool dispatch works

1. `Runner._execute_tool(call, turn)` looks up `registry.get_handler(call.name)`
2. For brief/article/procedure tools, the handler is a closure with `ToolContext` bound
3. For datalayer tools, the handler is a closure around the `SleeperLeagueData` method
4. The handler returns a JSON string → an OpenAI-format `tool` message

### How tools access ArtifactStore

Brief and article tools receive `ToolContext` containing `artifacts: ArtifactStore`.
They mutate `artifacts.brief` and `artifacts.article` directly (pass by reference).

### How RunLog gets events

Two sources:
1. **Runner-level:** `_execute_tool` logs every `tool_call` (name, params, summary, duration)
2. **Tool-level:** brief/article tools call `log.add_artifact_write(...)` for mutations

### How procedure replacement works

1. Model calls `load_procedure("drafting")`
2. Handler reads markdown, updates `ProcedureState.active`, logs the switch
3. Runner's `_replace_procedure_message()` compacts the old procedure result and appends the new one
4. `_procedure_message_idx` tracks the position

### Potential Challenges

1. **Procedure message index tracking** — removing a message shifts subsequent indices
2. **Chat-completions message format** — tool results must retain a matching assistant tool call; obsolete procedure content is replaced with `"[procedure replaced]"`
3. **Parallel tool execution** — synchronous Pydantic mutations under Python's GIL; no real race conditions
4. **`pyproject.toml`** — `reporter_v2` package must be added to the build config
