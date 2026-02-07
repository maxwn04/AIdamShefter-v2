# AI Fantasy Football Reporter — Master Design Document

> Status: Superseded by iterative research architecture (see redesign_iterative_research.md)

## 1. Overview

The **Reporter Agent** is an AI-powered system for generating engaging, data-grounded articles about a Sleeper fantasy football league. It produces weekly recaps, team deep dives, power rankings, playoff reactions, and custom reports with configurable tone, style, and optional bias toward or against specific teams.

### Core Principles

1. **Factual grounding**: All claims derive from the Sleeper datalayer—never fabricated
2. **Spec-driven flexibility**: Any request (preset or novel) compiles into a structured `ReportSpec`
3. **Brief-first writing**: Research produces a `ReportBrief` artifact before drafting begins
4. **Bias as framing only**: Bias affects word choice and emphasis, never facts
5. **Multi-agent ready**: Single-agent v1 uses artifacts that become handoff contracts later

---

## 2. Goals and Non-Goals

### Goals

- Produce **factually grounded** articles derived from Sleeper data
- Support both **preset** article types and **ad-hoc** custom requests
- Allow optional **bias configuration** that affects *framing* but not *facts*
- Keep design modular for **upgrade to multi-agent** orchestration later
- Maintain **full observability** via tracing for fast iteration

### Non-Goals (v1)

- Real-time web research or external news ingestion
- Full UI productization (CLI or minimal web interface is sufficient)
- Automated publishing pipeline (scheduling, notifications)
- Player news/injury scraping from external sources

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Request                                   │
│         (preset: "weekly_recap" or custom: "noir detective style")      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         RUNNER / ORCHESTRATOR                            │
│  • Load prompts (system + format + style + bias)                        │
│  • Initialize datalayer and tool registry                               │
│  • Manage phase gating                                                   │
│  • Store outputs and traces                                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌──────────────┐          ┌──────────────────┐         ┌──────────────┐
│ Phase 1:     │          │ Phase 2:         │         │ Phase 3:     │
│ SPEC         │    →     │ RESEARCH         │    →    │ DRAFT        │
│ SYNTHESIS    │          │ (Tool-heavy)     │         │ (No tools)   │
│              │          │                  │         │              │
│ Request →    │          │ Tools →          │         │ Brief + Spec │
│ ReportSpec   │          │ ReportBrief      │         │ → Article    │
└──────────────┘          └──────────────────┘         └──────────────┘
                                    │                           │
                                    │                           ▼
                                    │                  ┌──────────────┐
                                    │                  │ Phase 4:     │
                                    │                  │ VERIFY       │
                                    │                  │              │
                                    │                  │ Cross-check  │
                                    │                  │ claims vs    │
                                    │                  │ brief/tools  │
                                    └──────────────────┴──────────────┘
                                                                │
                                                                ▼
                                                    ┌─────────────────────┐
                                                    │ OUTPUTS             │
                                                    │ • Article (MD)      │
                                                    │ • ReportSpec (JSON) │
                                                    │ • ReportBrief (JSON)│
                                                    │ • Trace ID          │
                                                    └─────────────────────┘
```

---

## 4. The Spec System

The `ReportSpec` is the contract that defines what gets researched, how it is presented, and what is allowed. It enables true flexibility (any creative request) without sacrificing reliability.

### 4.1 ReportSpec Schema

```python
@dataclass
class ReportSpec:
    # Identity
    article_type: str                    # weekly_recap, power_rankings, team_deep_dive, custom
    time_range: TimeRange                # week N, weeks N-M, "since last report"

    # Voice & Style
    genre_voice: str                     # "sports radio rant", "noir detective", "financial analyst"
    tone_controls: ToneControls          # snark_level, hype_level, seriousness (0-3 each)
    profanity_policy: str                # none, mild, unrestricted

    # Structure
    structure: StructureSpec             # sections list or "freeform"
    length_target: int                   # word count target
    pov: str                             # first_person, third_person, etc.

    # Content
    content_requirements: list[str]      # must-cover topics: "top matchups", "trades", etc.
    focus_teams: list[str]               # teams to emphasize (optional)

    # Bias (writing-layer only)
    bias_profile: Optional[BiasProfile]  # favored/disfavored teams, intensity, boundaries

    # Guardrails
    evidence_policy: str                 # "all numbers from tools", "no unverifiable claims"
    audience: str                        # league members, newcomers, commissioner
```

### 4.2 How Presets Work

Presets are **default ReportSpec templates**, not hardcoded entry points:

| Preset | Base ReportSpec |
|--------|-----------------|
| `weekly_recap` | structure: intro → matchups → standings → transactions → outlook |
| `power_rankings` | structure: rankings 1-N with blurbs, tone: analytical |
| `team_deep_dive` | focus_teams: [target], structure: profile → season arc → roster |
| `playoff_reaction` | time_range: playoffs only, hype_level: high |

Custom requests inherit from a minimal base spec and override fields as needed.

### 4.3 Spec Synthesis Flow

```
User Request
     │
     ▼
┌─────────────────────────────┐
│ Classify Request            │
│ • Preset match?             │
│ • Partial match + overrides?│
│ • Novel/custom?             │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ Generate Draft Spec         │
│ • Fill from preset or base  │
│ • Parse intent for overrides│
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│ Detect Missing Fields       │
│ • Required: article_type,   │
│   time_range                │
│ • Material: tone, bias      │
└─────────────────────────────┘
     │
     ├─── Complete ───▶ Proceed to Research
     │
     ▼
┌─────────────────────────────┐
│ Spec Interview (1 turn max) │
│ • 1-3 targeted questions    │
│ • Multiple choice + defaults│
│ • Fill remaining with       │
│   sensible defaults         │
└─────────────────────────────┘
     │
     ▼
Final ReportSpec
```

### 4.4 Clarifying Question Set

When ambiguous, ask at most 3 questions from this standard set:

1. **Format**: Weekly recap / Power rankings / Team deep dive / Playoff reaction / Custom
2. **Time Range**: Week N / Weeks N-M / Since last report
3. **Tone**: Straight sportswriter / Hype & celebratory / Snarky roast-light / Savage roast
4. **Bias** (if applicable): Favor [teams] / Clown [teams] / Intensity 1-3
5. **Length**: Short (~500w) / Medium (~1000w) / Long (~1500w)

Always provide defaults inline: `"Tone: hype (default: straight)"`

---

## 5. The Brief System

The `ReportBrief` is the backbone of reliability. It captures what the agent "believes" after research, before writing.

### 5.1 ReportBrief Schema

```python
@dataclass
class ReportBrief:
    # Meta
    meta: BriefMeta                      # league_name, week_range, timestamp, article_type

    # Facts (the evidence base)
    facts: list[Fact]                    # Each has: claim_text, data_refs, numbers

    # Storylines (narrative structure)
    storylines: list[Storyline]          # Each has: headline, summary, supporting_fact_ids

    # Outline (writing plan)
    outline: list[Section]               # Each has: title, bullet_points, required_fact_ids

    # Resolved style/bias
    style: ResolvedStyle                 # voice, pacing, humor level
    bias: ResolvedBias                   # framing rules for favored/disfavored teams

@dataclass
class Fact:
    id: str
    claim_text: str                      # "Team A scored 142.3 points in Week 5"
    data_refs: list[str]                 # ["get_week_games:week=5", "game_id=abc123"]
    numbers: dict[str, float]            # {"points": 142.3, "week": 5}

@dataclass
class Storyline:
    headline: str                        # "Cinderella Run Ends in Heartbreak"
    summary: str                         # 2-3 sentence narrative
    supporting_fact_ids: list[str]       # References to Fact.id
    priority: int                        # 1 = lead story, 2 = secondary, etc.
```

### 5.2 Why Brief-First Matters

- **Inspectable**: Debug by examining what facts/storylines were selected
- **Verifiable**: Deterministically check that article claims match brief facts
- **Handoff-ready**: Becomes the contract for future Writer Agent

---

## 6. Datalayer Integration

The Reporter Agent connects to the existing Sleeper datalayer, which provides:
- Sleeper API fetching with local caching
- Normalization to canonical dataclass models
- In-memory SQLite storage
- Rich query interface with 16+ curated methods

### 6.1 Available Tools

The datalayer exposes these tools via `datalayer/sleeper_data/tools.py`:

#### League-Wide Context

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `get_league_snapshot` | Standings, games, transactions for a week | `week?` |
| `get_week_games` | All matchups with scores and winners | `week?` |
| `get_week_games_with_players` | Matchups with player-by-player breakdown | `week?` |
| `get_week_player_leaderboard` | Top scorers ranked by points | `week?`, `limit?` |
| `get_transactions` | Trades, waivers, FA pickups | `week_from`, `week_to` |

#### Team-Specific

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `get_team_dossier` | Profile, standings, recent games | `roster_key`, `week?` |
| `get_team_game` | Specific team's matchup | `roster_key`, `week?` |
| `get_team_game_with_players` | Team matchup with player details | `roster_key`, `week?` |
| `get_team_schedule` | Full season schedule with W/L/T | `roster_key` |
| `get_roster_current` | Current roster by role/position | `roster_key` |
| `get_roster_snapshot` | Historical roster for specific week | `roster_key`, `week` |
| `get_team_transactions` | Team-specific transaction history | `roster_key`, `week_from`, `week_to` |

#### Player-Specific

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `get_player_summary` | Metadata (position, team, status, injury) | `player_key` |
| `get_player_weekly_log` | Full season performance log | `player_key` |
| `get_player_weekly_log_range` | Performance for week range | `player_key`, `week_from`, `week_to` |

#### Escape Hatch

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `run_sql` | Guarded custom SQL (SELECT only) | `query`, `limit?` |

### 6.2 Tool Design Philosophy

1. **Context Packs over Atomic Queries**: `get_league_snapshot` returns standings + games + transactions in one call, reducing tool selection errors

2. **Name-Based Inputs**: All tools accept human-readable names (team name, manager name, player name) or IDs—the resolver handles ambiguity

3. **Consistent Output Contracts**: Every tool returns:
   ```python
   {
       "found": bool,
       "as_of_week": int,
       "data": {...}  # or error message if not found
   }
   ```

4. **Temporal Context**: All outputs include `as_of_week` so the agent knows data freshness

5. **Guarded SQL**: `run_sql` allows exploration but prevents writes (INSERT, UPDATE, DELETE blocked)

### 6.3 Tool Adapter Layer

The reporter wraps datalayer tools with additional concerns:

```python
# reporter/tools/sleeper_tools.py

from datalayer.sleeper_data import SleeperLeagueData, create_tool_handlers

class SleeperToolAdapter:
    """Adapts datalayer tools for the reporter agent."""

    def __init__(self, data: SleeperLeagueData):
        self.handlers = create_tool_handlers(data)
        self.call_log: list[ToolCall] = []

    def call(self, tool_name: str, **kwargs) -> dict:
        """Execute tool with logging for brief construction."""
        result = self.handlers[tool_name](**kwargs)
        self.call_log.append(ToolCall(
            tool=tool_name,
            params=kwargs,
            result_hash=hash_result(result),
            timestamp=datetime.now()
        ))
        return result

    def get_data_refs(self) -> list[str]:
        """Return refs for ReportBrief.facts.data_refs."""
        return [f"{c.tool}:{c.params}" for c in self.call_log]
```

### 6.4 Recommended Tool Usage Patterns

For each article type, the agent should follow these patterns:

**Weekly Recap**:
1. `get_league_snapshot(week=N)` — standings, all games, transactions
2. `get_week_player_leaderboard(week=N, limit=10)` — top performers
3. If needed: `get_team_game_with_players(roster_key)` for standout games

**Power Rankings**:
1. `get_league_snapshot(week=N)` — current standings
2. For each team: `get_team_dossier(roster_key)` — recent performance
3. Optionally: `get_transactions(week_from, week_to)` for roster moves context

**Team Deep Dive**:
1. `get_team_dossier(roster_key, week=N)` — profile, standings, recent games
2. `get_team_schedule(roster_key)` — full season arc
3. `get_roster_current(roster_key)` — current roster analysis
4. `get_team_transactions(roster_key, 1, N)` — all roster moves

**Playoff Reaction**:
1. `get_week_games(week=playoff_week)` — playoff matchup results
2. `get_week_games_with_players(week=playoff_week)` — who showed up
3. `get_team_dossier(winner_roster_key)` — champion profile

---

## 7. Agent Design

### 7.1 Single Agent with Phase Separation

The v1 agent operates as a single LLM call sequence, but enforces distinct phases:

```python
class ReporterAgent:
    def run(self, request: ArticleRequest) -> ArticleOutput:
        # Phase 1: Spec Synthesis
        spec = self.synthesize_spec(request)

        # Phase 1b: Spec Interview (if needed)
        if not spec.is_complete():
            spec = self.conduct_interview(spec)

        # Phase 2: Research → Brief
        brief = self.research_and_build_brief(spec)

        # Phase 3: Draft
        article = self.draft_from_brief(brief, spec)

        # Phase 4: Verify
        verified = self.verify_claims(article, brief)

        return ArticleOutput(
            article=verified,
            spec=spec,
            brief=brief,
            trace_id=self.trace_id
        )
```

### 7.2 Phase Implementation Options

**Option A: Prompt-based phases** (simpler)
- Single agent run with phase instructions in system prompt
- "Do not call tools during drafting"
- Works but relies on model compliance

**Option B: Runner-enforced phases** (more robust)
- Separate agent runs: Spec → Brief → Draft → Verify
- Tool registry changes between phases (no tools in Draft phase)
- Brief from Phase 2 is input to Phase 3

**Option C: Two-run separation** (recommended for v1)
- Run 1: Spec synthesis + Research → outputs ReportSpec + ReportBrief
- Run 2: Draft + Verify → consumes Brief, produces Article
- Simulates multi-agent without orchestration overhead

### 7.3 Tool Use Policy

During **Research** phase:
- Call context pack tools early (`get_league_snapshot`)
- Identify gaps in coverage
- Call targeted deep-dive tools as needed
- Build `ReportBrief` before exiting phase

During **Draft** phase:
- No tool calls allowed
- Write from brief only
- Apply style and bias from spec

During **Verify** phase:
- May call tools to spot-check claims
- Compare article numbers against brief facts
- Flag discrepancies for correction

---

## 8. Prompting System

### 8.1 Prompt Structure

```
prompts/
├── system_base.md           # Core reporter identity and rules
├── spec_synthesis.md        # Convert request → ReportSpec
├── brief_building.md        # Guidelines for research → brief
├── drafting.md              # Writing from brief + spec
├── verification.md          # Fact-checking instructions
│
├── formats/                 # Article-type templates
│   ├── weekly_recap.md
│   ├── power_rankings.md
│   ├── team_deep_dive.md
│   └── playoff_reaction.md
│
├── styles/                  # Voice presets
│   ├── straight_news.md
│   ├── snarky_columnist.md
│   ├── hype_man.md
│   ├── beat_reporter.md
│   └── sports_radio.md
│
└── bias/
    └── bias_rules.md        # How to apply bias ethically
```

### 8.2 System Base Prompt (Core Identity)

Key elements:
- You are a fantasy football reporter for [League Name]
- All facts must come from tool outputs
- Never fabricate statistics, scores, or player performances
- Bias affects word choice and framing, not factual claims
- Always build a ReportBrief before drafting

### 8.3 Bias Rules

Bias is a **writing-layer concern only**:

| Allowed | Not Allowed |
|---------|-------------|
| "crushed their opponent" vs "narrowly survived" | Changing actual scores |
| Emphasizing a team's wins, downplaying losses | Omitting a team's loss entirely |
| Playful trash talk toward disfavored teams | False claims about performance |
| Celebratory language for favored teams | Inventing statistics |

Bias intensity levels:
- **0**: Neutral (no bias applied)
- **1**: Subtle (word choice only)
- **2**: Noticeable (framing and emphasis)
- **3**: Heavy (active trash talk / celebration)

---

## 9. Guardrails and Evidence Policy

### 9.1 Evidence Policy Enforcement

The `ReportSpec.evidence_policy` field controls fact-checking rigor:

| Policy | Meaning |
|--------|---------|
| `strict` | Every number must have a `data_ref` in the brief |
| `standard` | Key claims must be grounded; flavor text allowed |
| `relaxed` | Major facts grounded; stylistic liberties permitted |

### 9.2 Verification Phase

After drafting, the Verify phase:
1. Extracts numeric claims from article (scores, rankings, stats)
2. Checks each against `ReportBrief.facts`
3. Flags mismatches for correction
4. Produces verification report

```python
@dataclass
class VerificationResult:
    passed: bool
    claims_checked: int
    mismatches: list[ClaimMismatch]
    corrections_made: list[str]
```

### 9.3 Fact vs Framing Separation

The system maintains a hard boundary:

```
┌─────────────────────────────────────┐
│           FACTS                      │
│  (From tools → Brief → Article)     │
│                                      │
│  • Scores: 142.3 - 98.7             │
│  • Records: 7-2                      │
│  • Rankings: 3rd place              │
│  • Transactions: Traded Player X    │
└─────────────────────────────────────┘
              ↓ (untouched by bias)

┌─────────────────────────────────────┐
│           FRAMING                    │
│  (Shaped by bias + style)           │
│                                      │
│  • "dominated" vs "edged out"       │
│  • Lead story selection             │
│  • Adjective choices                │
│  • Narrative emphasis               │
└─────────────────────────────────────┘
```

---

## 10. Observability and Debugging

### 10.1 Tracing Strategy

Using OpenAI Agents SDK tracing, capture:
- Tool calls with inputs/outputs
- Intermediate `ReportSpec` and `ReportBrief`
- Phase transitions
- Final article
- Verification results

Tag traces with: `article_type`, `week_range`, `style_preset`, `bias_intensity`

### 10.2 Debug Workflow

When output quality is poor:

1. **Inspect ReportSpec** → Were constraints understood correctly?
2. **Inspect ReportBrief** → Missing facts? Wrong storyline selection?
3. **Inspect tool calls** → Did it call the right context packs?
4. **Inspect verification** → What claims failed?

Then adjust:
- Prompts/policies for better storyline ranking
- Tool usage patterns for missing data
- Spec defaults for common misinterpretations

---

## 11. File and Project Structure

```
reporter/
├── README.md
├── pyproject.toml
├── .env.example
│
├── src/
│   └── reporter/
│       ├── __init__.py
│       │
│       ├── app/
│       │   ├── runner.py              # CLI/web entrypoints
│       │   ├── config.py              # env vars, article presets
│       │   ├── logging.py             # structured logging + trace hooks
│       │   └── caching.py             # cache interface
│       │
│       ├── agent/
│       │   ├── reporter_agent.py      # Agents SDK agent definition
│       │   ├── workflows.py           # Spec→Brief→Draft→Verify orchestration
│       │   ├── schemas.py             # Pydantic: ReportBrief, ArticleOutput
│       │   ├── specs.py               # Pydantic: ReportSpec + presets
│       │   └── policies.py            # tool use rules, bias constraints
│       │
│       ├── prompts/
│       │   ├── system_base.md
│       │   ├── spec_synthesis.md
│       │   ├── brief_building.md
│       │   ├── drafting.md
│       │   ├── verification.md
│       │   ├── formats/
│       │   ├── styles/
│       │   └── bias/
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py            # collects tools for agent
│       │   ├── sleeper_tools.py       # adapters around datalayer
│       │   └── tool_utils.py          # validation, error normalization
│       │
│       └── evals/
│           ├── __init__.py
│           ├── snapshots.py           # capture/load frozen league data
│           ├── tests_factuality.py    # article facts match brief
│           ├── tests_style.py         # length, structure, tone
│           └── golden/                # saved fixtures by week
│
├── docs/
│   ├── design.md                      # This document
│   └── ...
│
└── scripts/
    ├── run_weekly_recap.py
    └── snapshot_week.py
```

---

## 12. Request Flow (End-to-End)

```
1. User Request
   │  "Write a snarky recap of Week 8 favoring Team Taco"
   │
   ▼
2. Runner Initialization
   │  • Load system + format + style + bias prompts
   │  • Initialize SleeperLeagueData
   │  • Create tool registry via SleeperToolAdapter
   │
   ▼
3. Spec Synthesis
   │  • Classify: partial match to weekly_recap preset
   │  • Generate draft spec with overrides:
   │    - article_type: weekly_recap
   │    - time_range: week 8
   │    - tone_controls: {snark_level: 2}
   │    - bias_profile: {favored: ["Team Taco"], intensity: 2}
   │  • Check completeness → complete
   │
   ▼
4. Research Phase
   │  • get_league_snapshot(week=8)
   │  • get_week_player_leaderboard(week=8, limit=10)
   │  • get_team_dossier("Team Taco", week=8)
   │  • Build ReportBrief with 15 facts, 4 storylines
   │
   ▼
5. Draft Phase
   │  • No tool calls
   │  • Apply snarky_columnist style
   │  • Apply bias framing (favorable to Team Taco)
   │  • Generate 1000-word article
   │
   ▼
6. Verify Phase
   │  • Extract 23 numeric claims
   │  • Check against brief: 23/23 match
   │  • Verification passed
   │
   ▼
7. Output
   │  • article.md (final article)
   │  • spec.json (ReportSpec)
   │  • brief.json (ReportBrief)
   │  • trace_id for debugging
```

---

## 13. Multi-Agent Upgrade Path

The v1 single-agent design prepares for future multi-agent orchestration:

### Future Agent Roles

| Agent | Input | Output | Tools |
|-------|-------|--------|-------|
| Spec Planner | Request | ReportSpec | None (or minimal) |
| Researcher | ReportSpec | ReportBrief | All datalayer tools |
| Writer | ReportBrief + ReportSpec | Draft | None |
| Editor | Draft + ReportBrief | Final Article | Limited verification tools |

### Migration Path

1. `ReportSpec` and `ReportBrief` are already stable handoff contracts
2. Phase separation in v1 maps directly to agent boundaries
3. Upgrade means converting `workflows.py` to use SDK handoffs:

```python
# v1: Single agent with phases
brief = agent.research_phase(spec)
article = agent.draft_phase(brief, spec)

# v2: Multi-agent handoffs
brief = await handoff(researcher_agent, spec)
article = await handoff(writer_agent, (brief, spec))
```

Because v1 uses spec-first and brief-first patterns, this is **wiring, not redesign**.

---

## 14. Evaluation Plan

### 14.1 Snapshot Fixtures

Capture league state per week into `evals/golden/`:
- Standings, games, transactions, rosters
- Enables deterministic regression testing

### 14.2 Test Categories

| Category | Tests |
|----------|-------|
| **Factuality** | All numeric claims in article exist in brief; facts reference tool outputs |
| **Structure** | Required sections exist per article type; length within target range |
| **Style** | Tone constraints respected; profanity policy enforced |
| **Spec** | Required fields resolved before drafting; evidence policy enforced |
| **Bias** | Facts unchanged; framing appropriately biased |

### 14.3 Evaluation Metrics

- **Fact accuracy**: % of article claims traceable to brief
- **Structure compliance**: % of required sections present
- **Length adherence**: within 10% of target
- **Bias boundary**: 0 fact-level bias violations

---

## 15. Implementation Milestones

### Milestone 1: Minimal End-to-End Weekly Recap

- [ ] Datalayer integration with tool adapters
- [ ] ReportSpec and ReportBrief Pydantic models
- [ ] Basic prompts: system_base, weekly_recap format
- [ ] Single-agent workflow (spec → brief → draft)
- [ ] CLI runner with output saving

### Milestone 2: Full Article Type Coverage

- [ ] Power rankings format + prompt
- [ ] Team deep dive format + prompt
- [ ] Playoff reaction format + prompt
- [ ] Style presets: straight_news, snarky, hype_man

### Milestone 3: Verification + Evaluation

- [ ] Verify phase implementation
- [ ] Snapshot capture tooling
- [ ] Factuality regression tests
- [ ] Structure/style compliance tests

### Milestone 4: Bias System

- [ ] Bias profile schema
- [ ] Bias rules prompt
- [ ] Bias boundary tests

### Milestone 5: Multi-Agent (Optional)

- [ ] Extract phases into separate agents
- [ ] Implement SDK handoffs
- [ ] Validate artifact contracts work across agents

---

## Appendix A: Key Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Spec-first workflow | Yes | Enables flexibility without chaos |
| Brief as intermediate artifact | Yes | Inspectable, verifiable, handoff-ready |
| Single agent v1 | Yes | Simpler iteration; multi-agent later |
| Tool count | 16 curated | Reduce selection errors vs dozens of tiny tools |
| Bias as framing only | Yes | Preserve trust; facts remain neutral |
| Phase separation | Two-run recommended | Robust without multi-agent overhead |

## Appendix B: Open Questions

1. **Spec interview UX**: In CLI, how to present clarifying questions? Interactive prompt or JSON response?
2. **Brief size limits**: Should we cap facts/storylines to prevent context bloat?
3. **Caching strategy**: Cache tool outputs between runs? Cache entire briefs for similar requests?
4. **Custom spec persistence**: Should successful custom specs become reusable presets automatically?
