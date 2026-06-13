# Phase 9: End-to-End Integration and CLI

**Goal:** Wire everything together. Create the entry point that takes a user
request, builds the runner, runs it, and returns the output.

**Files to create:**
- `reporter_v2/runner/entrypoint.py`
- `reporter_v2/prompts/system.md`
- `reporter_v2/tests/test_integration.py`

**Dependencies:** All previous phases

---

## `reporter_v2/runner/entrypoint.py`

```python
async def generate_article(
    data: SleeperLeagueData,
    config: ReportConfig,
    *,
    gateway: AiGateway | None = None,
    context_store: ContextStore | None = None,
    model: str | None = None,
    log_path: Path | None = None,
) -> ArticleOutput:
    """Main entry point for generating an article with the v2 runner."""

    gw = gateway or create_gateway(AiGatewayConfig(model=model))
    runner_config = RunnerConfig(model=model)

    artifacts = ArtifactStore()
    procedures = ProcedureState()
    log = RunLog()

    # Set brief meta from config
    artifacts.brief.meta.league_id = data.league_id
    artifacts.brief.meta.week_start = config.time_range.week_start
    artifacts.brief.meta.week_end = config.time_range.week_end

    # Build registry
    registry = ToolRegistry()
    ctx = ToolContext(artifacts=artifacts, procedures=procedures, log=log)
    register_brief_tools(registry, ctx)
    register_article_tools(registry, ctx)
    register_procedure_tools(registry, ctx)
    register_datalayer_tools(registry, data)
    if context_store:
        register_persistent_tools(
            registry, context_store,
            week=config.time_range.week_end,
        )

    system_prompt = _build_system_prompt(config)
    user_message = _build_user_message(config)

    runner = Runner(gw, registry, config=runner_config, log_path=log_path)
    runner.artifacts = artifacts
    runner.procedures = procedures
    runner.log = log

    return await runner.run(system_prompt, user_message)
```

`ContextStore` is imported from `reporter_memory.context_store`. The CLI creates
it at `.data/context.db` by default unless persistent context is disabled.

## System Prompt (`reporter_v2/prompts/system.md`)

A lean prompt that establishes identity and rules. Phase-specific instructions
come from procedures. Adapted from v1's `system_base.md` but shortened:

```markdown
# Fantasy Football Reporter

You are an AI reporter for a Sleeper fantasy football league. You generate
engaging, factually grounded articles.

## Core Rules
- ALL claims must derive from datalayer tool outputs. Never fabricate data.
- Bias affects framing only, never facts.
- Every numeric claim must trace to a fact in your brief.

## How You Work
1. Load a procedure to get phase-specific instructions.
2. Use tools to research, build your brief, draft, and verify.
3. Call submit_article() when done.

Only one procedure is active at a time. Loading a new procedure replaces
the previous one.
```

## Tests

- `test_end_to_end_with_fake_gateway` -- full integration test with mocked
  gateway and datalayer. The fake gateway returns a scripted sequence:
  `load_procedure -> research tools -> save_fact -> load_procedure(drafting)
  -> read_brief -> write_section -> submit_article`
- Verify the output has article text, brief with facts, and correct
  run_log_summary
