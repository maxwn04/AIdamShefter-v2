# Reporter Architecture

## Two-Phase Pipeline

**Phase 1 — Research** (`ResearchAgent`): Has full tool access. Iteratively queries the datalayer, builds a `ReportBrief` containing verified `Fact` objects and `Storyline` narratives. All tool calls logged in `ResearchLog`.

**Phase 2 — Draft** (`DraftAgent`): No tool access. Writes the article purely from the `ReportBrief`, applying configured voice and style. Cannot hallucinate data because it can only reference facts from the brief.

## Key Types

**ReportConfig** (`agent/config.py`): What to write.
- `time_range` (TimeRange): week_start, week_end
- `voice` (str): "sports columnist", "snarky columnist", "hype broadcaster", etc.
- `tone` (ToneControls): snark_level 0-3, hype_level 0-3
- `bias_profile` (BiasProfile): favored_teams, disfavored_teams, intensity 0-3
- `focus_hints`, `focus_teams`, `avoid_topics`, `length_target`, `custom_instructions`

**ReportBrief** (`agent/schemas.py`): Research output, draft input.
- `facts: list[Fact]` — Atomic verified claims with `data_refs` and `numbers`
- `storylines: list[Storyline]` — Narrative threads with `supporting_fact_ids` and priority
- `outline: list[Section]` — Planned article structure
- `style: ResolvedStyle`, `bias: ResolvedBias`

**ArticleOutput** (`agent/schemas.py`): Final output.
- `article` (str): Markdown article
- `config`, `brief`, `research_log`, `verification`

## Tool System

**Tool definitions** are in `datalayer/tools.py` as `SLEEPER_TOOLS` (OpenAI function-calling format, 16 tools). `create_tool_handlers(data)` returns a `dict[str, Callable]` mapping tool names to `SleeperLeagueData` methods.

The reporter's `ResearchToolAdapter` (`tools/sleeper_tools.py`) wraps these handlers with logging. `create_tool_registry()` (`tools/registry.py`) converts them to OpenAI Agents SDK `Tool` objects.

## Prompts

All prompt templates live in `prompts/`:
- `research_agent.md`, `draft_agent.md` — Phase-specific system prompts
- `system_base.md` — Core reporter identity and rules
- `brief_building.md`, `drafting.md`, `verification.md` — Phase guidelines
- `bias/bias_rules.md` — Bias framing rules

## Programmatic Usage

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

## Design Docs

- `docs/design.md` — Original reporter design (historical reference)
- `docs/redesign_iterative_research.md` — Iterative research architecture (current)
