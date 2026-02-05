# Reporter Redesign: Iterative Research Mode

## Overview

This document describes a redesign of the Reporter Agent to replace the preset-driven, hardcoded research approach with an **iterative, agent-driven research process**. The agent will plan, explore, and build reports dynamically based on user requests—no preset templates.

---

## Problem Statement

The current implementation suffers from:

1. **Hardcoded data gathering** (`reporter_agent.py:112-166`)
   - `gather_data()` has rigid if/else logic for each article type
   - Tools are called programmatically, not by the agent
   - No intelligence in deciding what data is relevant

2. **Mechanical brief building** (`reporter_agent.py:168-304`)
   - Facts extracted by looping over data structures
   - Storylines identified via simple thresholds (e.g., `margin > 40` = blowout)
   - No creative judgment about what's actually interesting

3. **Preset-centric design**
   - Four rigid article types with predefined structures
   - "Custom" is just an afterthought (inherits from weekly_recap)
   - User creativity constrained by template system

4. **No iterative research**
   - Agent doesn't actually research—code does the research
   - No ability to follow threads, dig deeper, or explore tangents
   - Brief is a mechanical byproduct, not an editorial artifact

---

## Design Goals

1. **Agent-driven research**: The LLM decides what tools to call, in what order, based on what it learns
2. **Iterative exploration**: Agent can follow threads—if a game looks interesting, drill into player stats
3. **Dynamic storyline discovery**: Agent identifies narratives through reasoning, not thresholds
4. **No preset templates**: Every request is "custom"—user describes what they want, agent figures it out
5. **Brief as editorial artifact**: Brief reflects the agent's editorial judgment, not mechanical extraction

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User Request (CLI)                             │
│         "Snarky recap of week 8, focus on upset victories"              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Phase 0: CLARIFICATION                               │
│  • ClarificationAgent analyzes request                                  │
│  • Asks 0-2 targeted questions if needed                                │
│  • Builds ReportConfig from user input                                   │
│  • User confirms before proceeding                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ ReportConfig
┌─────────────────────────────────────────────────────────────────────────┐
│                         RUNNER / ORCHESTRATOR                            │
│  • Initialize datalayer and tool registry                               │
│  • Execute two-phase pipeline                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        ▼                                                       ▼
┌────────────────────────────────┐               ┌────────────────────────────┐
│ Phase 1: RESEARCH              │               │ Phase 2: DRAFT             │
│ (Tool-enabled agent)           │               │ (No tools)                 │
│                                │               │                            │
│ • Agent receives request       │               │ • Brief + Config → Article │
│ • Agent plans research         │               │ • Apply style/voice        │
│ • Agent calls tools iteratively│               │ • All facts from brief     │
│ • Agent identifies storylines  │ ───────────▶  │ • No tool access           │
│ • Agent builds ReportBrief     │   Brief       │                            │
│                                │               │                            │
│ Output: ReportBrief JSON       │               │ Output: Markdown article   │
└────────────────────────────────┘               └────────────────────────────┘
```

---

## CLI Interface

The reporter is accessed through an interactive CLI:

```bash
# Interactive mode - prompts for input
./reporter/scripts/reporter

# Direct mode with prompt
./reporter/scripts/reporter "weekly recap"
./reporter/scripts/reporter "snarky recap, roast Team Taco" --week 8

# With specific week
./reporter/scripts/reporter "power rankings" -w 12
```

### CLI Flow

1. **User enters prompt** (or provides via command line)
2. **Clarification Agent** asks targeted questions if needed:
   - "Which week would you like to cover?" (if ambiguous)
   - "Any teams you want to focus on?"
   - "How snarky should it be? (1-3)"
3. **User confirms** the resolved configuration
4. **Research Phase** runs with progress updates
5. **Article** is displayed and saved

---

## Key Changes

### 1. Remove Article Type Presets

**Delete:**

- `ArticleType` enum
- `WEEKLY_RECAP_PRESET`, `POWER_RANKINGS_PRESET`, etc.
- `get_preset()` function
- `StructureSpec` and `SectionSpec` (agent decides structure)

**Keep:**

- Time range configuration
- Tone controls (snark_level, hype_level)
- Bias profile
- Length target
- Evidence policy

**New:**

- `focus_hints: list[str]` - Optional topics to emphasize (e.g., "upsets", "trades", "playoff race")
- `avoid_topics: list[str]` - Topics to skip
- `custom_instructions: str` - Freeform user guidance

### 2. Simplified ReportConfig (replacing ReportSpec)

```python
@dataclass
class ReportConfig:
    """Minimal configuration for article generation."""

    # What to cover
    time_range: TimeRange                    # week N or weeks N-M
    focus_hints: list[str] = field(default_factory=list)
    avoid_topics: list[str] = field(default_factory=list)
    focus_teams: list[str] = field(default_factory=list)

    # Voice & Style
    voice: str = "sports columnist"          # "noir detective", "hype broadcaster", etc.
    tone: ToneControls = field(default_factory=ToneControls)
    profanity_policy: str = "none"

    # Bias
    bias_profile: Optional[BiasProfile] = None

    # Guardrails
    length_target: int = 1000
    evidence_policy: str = "standard"

    # Freeform
    custom_instructions: str = ""            # User's raw creative direction
```

### 3. Agent-Driven Research Phase

Instead of `gather_data()`, the Research Agent operates as a true agentic loop:

```python
class ResearchAgent:
    """Agent that iteratively researches and builds a brief."""

    def __init__(self, data: SleeperLeagueData, config: ReportConfig):
        self.adapter = SleeperToolAdapter(data)
        self.tools = create_tool_registry(self.adapter)
        self.config = config

    async def research(self) -> ReportBrief:
        """Run the research agent to produce a brief."""

        system_prompt = self._build_research_prompt()

        agent = Agent(
            name="researcher",
            instructions=system_prompt,
            model="gpt-5-mini",
            tools=self.tools,
            output_type=ReportBrief,  # Structured output
        )

        user_prompt = self._build_user_prompt()
        result = await Runner.run(agent, user_prompt)

        return result.final_output
```

**Research System Prompt (key sections):**

```markdown
# Fantasy Football Research Agent

You are a researcher for a fantasy football publication. Your job is to:

1. **Explore** the league data using the available tools
2. **Identify** interesting storylines, narratives, and facts
3. **Build** a ReportBrief artifact with your findings

## CRITICAL: Logging Your Reasoning

You MUST document your reasoning throughout the research process. Before EVERY
data retrieval tool call, use `log_reasoning` to explain WHY you're making that call.

Pattern:

1. `log_reasoning(intent="...", category="...")` - Explain your intent
2. `get_*()` or `run_sql()` - Make the data call
3. `record_finding(...)` - Document what you learned (if significant)

This creates an audit trail that helps us understand your editorial thinking.

## Research Process

1. Start with broad context (get_league_snapshot)
2. Identify what looks interesting—upsets, blowouts, streaks, big trades
3. Drill into specifics using targeted tools
4. Use `record_finding` when you discover something notable
5. Use `note_storyline_idea` when you see a narrative emerging
6. Call `mark_research_complete` when you have enough material

## What Makes a Good Storyline

- **Upsets**: Underdogs beating favorites, unexpected outcomes
- **Dominance**: Blowout victories, statement wins
- **Drama**: Close games, comeback victories, last-minute wins
- **Trends**: Winning/losing streaks, rising/falling teams
- **Personnel**: Breakout player performances, injuries impacting games
- **Transactions**: Trades that worked/failed, waiver wire finds
- **Stakes**: Playoff implications, rivalry matchups

## Research Guidelines

- Call tools iteratively—don't try to gather everything at once
- If something looks interesting, investigate further
- Build your brief as you go—add facts when you confirm them
- Aim for 10-20 high-quality facts, 3-5 strong storylines
- Your outline should reflect what YOU think is most compelling
- ALWAYS log your reasoning before data calls—this is required

## Output Format

You must produce a ReportBrief with:

- meta: Basic article metadata
- facts: Verified claims with data references
- storylines: Narratives ranked by editorial priority
- outline: Suggested article structure
- style: Voice and tone settings
- bias: Framing rules if applicable
```

### 4. Agent-Built Brief

The key difference: **the agent builds the brief through reasoning**, not code extracting data mechanically.

**Before (mechanical):**

```python
# Code loops over games and applies thresholds
for game in games:
    margin = abs(score_a - score_b)
    if margin > 40:
        storylines.append(Storyline(headline="Blowout Victory", ...))
```

**After (agent reasoning):**

```
Agent thinks: "Team A beat Team B by 47 points. That's the biggest margin
this week and Team B was previously 7-1. This is a major upset AND a
blowout—lead story material. Let me check if Team A has any key players
who went off..."

Agent calls: get_team_game_with_players(roster_key="Team A", week=8)

Agent adds fact: "Jaylen Waddle scored 38.2 points for Team A, his
season high"

Agent builds storyline: "Team A's Statement Win" - priority 1, tags:
[upset, blowout, breakout_performance]
```

### 5. Research Tools Expansion

The research phase uses an expanded toolkit that includes both data retrieval and reasoning/logging tools.

#### 5.1 Data Retrieval Tools (existing)

These tools fetch data from the Sleeper datalayer:

| Tool                          | Purpose                                       | When to Use                        |
| ----------------------------- | --------------------------------------------- | ---------------------------------- |
| `get_league_snapshot`         | Broad context: standings, games, transactions | First call—get the lay of the land |
| `get_week_games`              | All matchups with scores                      | Identify interesting games         |
| `get_week_games_with_players` | Games with player breakdowns                  | Investigate specific matchups      |
| `get_week_player_leaderboard` | Top scorers                                   | Find standout performers           |
| `get_transactions`            | Trades, waivers, FA pickups                   | Transaction storylines             |
| `get_team_dossier`            | Team profile, record, streak                  | Deep dive on a team                |
| `get_team_game`               | Single team's matchup                         | Focus on one side of a game        |
| `get_team_game_with_players`  | Team matchup with roster detail               | Player-level analysis              |
| `get_team_schedule`           | Full season results                           | Season arc, trends                 |
| `get_roster_current`          | Current roster by position                    | Roster composition analysis        |
| `get_roster_snapshot`         | Historical roster                             | What roster looked like in past    |
| `get_team_transactions`       | Team-specific moves                           | Track a team's roster activity     |
| `get_player_summary`          | Player metadata                               | Basic player info                  |
| `get_player_weekly_log`       | Season performance log                        | Player consistency/trends          |
| `get_player_weekly_log_range` | Performance in week range                     | Focused player analysis            |
| `run_sql`                     | Custom SELECT queries                         | Complex/ad-hoc queries             |

#### 5.2 Research Reasoning Tools (new)

These tools help the agent document its reasoning process:

```python
@function_tool
def log_reasoning(
    intent: str,
    category: str = "investigation"
) -> dict:
    """Log your reasoning before making a tool call.

    REQUIRED: Call this before each data retrieval tool to document WHY
    you're making that call.

    Args:
        intent: What you're trying to learn or verify (1-2 sentences)
        category: Type of reasoning
            - "investigation": Following up on something interesting
            - "exploration": Broad data gathering
            - "verification": Confirming a hypothesis
            - "deep_dive": Drilling into specifics
            - "comparison": Comparing teams/players/weeks

    Example:
        log_reasoning(
            intent="Team Taco lost by 50 points—checking if their star player underperformed",
            category="investigation"
        )
    """
    return {"logged": True, "intent": intent, "category": category}


@function_tool
def record_finding(
    finding: str,
    significance: str,
    storyline_potential: bool = False
) -> dict:
    """Record a significant finding from your research.

    Call this when you discover something noteworthy that should inform
    the article.

    Args:
        finding: What you discovered (factual statement)
        significance: Why this matters for the article
        storyline_potential: True if this could be a major storyline

    Example:
        record_finding(
            finding="Josh Allen scored 42.3 points, highest in the league this week",
            significance="Could be the headline performer for top performers section",
            storyline_potential=True
        )
    """
    return {"recorded": True, "finding": finding, "significance": significance}


@function_tool
def note_storyline_idea(
    headline: str,
    summary: str,
    evidence: list[str],
    priority: int = 2
) -> dict:
    """Capture a potential storyline as you research.

    Call this when you identify a narrative thread worth developing.

    Args:
        headline: Catchy headline for the storyline
        summary: 2-3 sentence narrative summary
        evidence: List of facts/findings supporting this storyline
        priority: 1=lead story, 2=secondary, 3=minor mention

    Example:
        note_storyline_idea(
            headline="Cinderella Story Continues",
            summary="Team Underdog extends their winning streak to 5 games...",
            evidence=["5-game winning streak", "beat #1 seed this week"],
            priority=1
        )
    """
    return {"recorded": True, "headline": headline, "priority": priority}


@function_tool
def mark_research_complete(
    facts_gathered: int,
    storylines_identified: int,
    confidence: str = "high"
) -> dict:
    """Signal that research is complete and ready to build the brief.

    Call this when you've gathered enough material. This is a checkpoint
    before producing the final ReportBrief.

    Args:
        facts_gathered: Approximate number of facts collected
        storylines_identified: Number of storylines identified
        confidence: "high", "medium", or "low" - your confidence level

    Example:
        mark_research_complete(
            facts_gathered=15,
            storylines_identified=4,
            confidence="high"
        )
    """
    return {
        "complete": True,
        "facts": facts_gathered,
        "storylines": storylines_identified,
        "confidence": confidence
    }
```

#### 5.3 Research Tool Usage Pattern

The agent should follow this pattern:

```
1. log_reasoning(intent="Getting overview of week 8", category="exploration")
2. get_league_snapshot(week=8)
3. record_finding(finding="Team A upset Team B by 30 points", ...)
4. log_reasoning(intent="Investigating the upset—who performed?", category="investigation")
5. get_team_game_with_players(roster_key="Team A", week=8)
6. record_finding(finding="Player X had season-high 35 points", ...)
7. note_storyline_idea(headline="Upset of the Year", ...)
8. ... more research ...
9. mark_research_complete(facts_gathered=12, storylines_identified=3)
10. → Produce ReportBrief
```

---

## 6. Research Log System

The Research Log captures the agent's reasoning process for debugging and observability.

### 6.1 ResearchLog Schema

```python
@dataclass
class ResearchLogEntry:
    """A single entry in the research log."""

    timestamp: str
    entry_type: str              # "reasoning", "tool_call", "finding", "storyline", "checkpoint"

    # For reasoning entries
    intent: Optional[str] = None
    category: Optional[str] = None

    # For tool_call entries
    tool_name: Optional[str] = None
    tool_params: Optional[dict] = None
    tool_result_summary: Optional[str] = None
    preceding_reasoning_id: Optional[str] = None  # Links to the reasoning that prompted this call

    # For finding entries
    finding: Optional[str] = None
    significance: Optional[str] = None

    # For storyline entries
    headline: Optional[str] = None
    priority: Optional[int] = None

    # Metadata
    entry_id: str = field(default_factory=lambda: str(uuid4())[:8])


@dataclass
class ResearchLog:
    """Complete log of the research process."""

    session_id: str
    started_at: str
    entries: list[ResearchLogEntry] = field(default_factory=list)

    # Summary stats
    tool_calls: int = 0
    reasoning_entries: int = 0
    findings_recorded: int = 0
    storylines_noted: int = 0

    def add_entry(self, entry: ResearchLogEntry) -> None:
        self.entries.append(entry)
        # Update counts
        if entry.entry_type == "tool_call":
            self.tool_calls += 1
        elif entry.entry_type == "reasoning":
            self.reasoning_entries += 1
        elif entry.entry_type == "finding":
            self.findings_recorded += 1
        elif entry.entry_type == "storyline":
            self.storylines_noted += 1

    def get_tool_calls_with_reasoning(self) -> list[dict]:
        """Get all tool calls paired with their preceding reasoning."""
        result = []
        reasoning_map = {e.entry_id: e for e in self.entries if e.entry_type == "reasoning"}

        for entry in self.entries:
            if entry.entry_type == "tool_call":
                reasoning = reasoning_map.get(entry.preceding_reasoning_id)
                result.append({
                    "tool": entry.tool_name,
                    "params": entry.tool_params,
                    "result_summary": entry.tool_result_summary,
                    "reasoning": reasoning.intent if reasoning else "No reasoning logged",
                    "reasoning_category": reasoning.category if reasoning else None,
                })
        return result

    def to_markdown(self) -> str:
        """Export log as readable markdown for debugging."""
        lines = [
            f"# Research Log: {self.session_id}",
            f"Started: {self.started_at}",
            f"",
            f"## Summary",
            f"- Tool calls: {self.tool_calls}",
            f"- Reasoning entries: {self.reasoning_entries}",
            f"- Findings: {self.findings_recorded}",
            f"- Storylines: {self.storylines_noted}",
            f"",
            f"## Timeline",
            f"",
        ]

        for entry in self.entries:
            if entry.entry_type == "reasoning":
                lines.append(f"### 💭 Reasoning [{entry.category}]")
                lines.append(f"> {entry.intent}")
                lines.append("")
            elif entry.entry_type == "tool_call":
                lines.append(f"### 🔧 Tool: `{entry.tool_name}`")
                lines.append(f"**Params:** `{entry.tool_params}`")
                lines.append(f"**Result:** {entry.tool_result_summary}")
                lines.append("")
            elif entry.entry_type == "finding":
                lines.append(f"### 📌 Finding")
                lines.append(f"**Fact:** {entry.finding}")
                lines.append(f"**Significance:** {entry.significance}")
                lines.append("")
            elif entry.entry_type == "storyline":
                lines.append(f"### 📰 Storyline Idea (Priority {entry.priority})")
                lines.append(f"**{entry.headline}**")
                lines.append("")
            elif entry.entry_type == "checkpoint":
                lines.append(f"### ✅ Research Complete")
                lines.append("")

        return "\n".join(lines)
```

### 6.2 Log-Aware Tool Adapter

The `SleeperToolAdapter` is enhanced to integrate with the research log:

```python
class ResearchToolAdapter:
    """Tool adapter that logs all calls with reasoning context."""

    def __init__(self, data: SleeperLeagueData):
        self.data = data
        self.log = ResearchLog(
            session_id=str(uuid4())[:8],
            started_at=datetime.utcnow().isoformat(),
        )
        self._pending_reasoning: Optional[ResearchLogEntry] = None
        self._handlers = self._build_handlers()

    def log_reasoning(self, intent: str, category: str) -> dict:
        """Log reasoning before a tool call."""
        entry = ResearchLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            entry_type="reasoning",
            intent=intent,
            category=category,
        )
        self.log.add_entry(entry)
        self._pending_reasoning = entry  # Track for linking to next tool call
        return {"logged": True, "entry_id": entry.entry_id}

    def call(self, tool_name: str, **kwargs) -> dict:
        """Execute a tool with logging."""
        result = self._handlers[tool_name](**kwargs)

        # Log the tool call, linked to preceding reasoning
        entry = ResearchLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            entry_type="tool_call",
            tool_name=tool_name,
            tool_params=kwargs,
            tool_result_summary=self._summarize_result(result),
            preceding_reasoning_id=self._pending_reasoning.entry_id if self._pending_reasoning else None,
        )
        self.log.add_entry(entry)
        self._pending_reasoning = None  # Clear after use

        return result

    def record_finding(self, finding: str, significance: str, storyline_potential: bool) -> dict:
        """Record a research finding."""
        entry = ResearchLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            entry_type="finding",
            finding=finding,
            significance=significance,
        )
        self.log.add_entry(entry)
        return {"recorded": True}

    def note_storyline(self, headline: str, summary: str, evidence: list[str], priority: int) -> dict:
        """Note a potential storyline."""
        entry = ResearchLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            entry_type="storyline",
            headline=headline,
            priority=priority,
        )
        self.log.add_entry(entry)
        return {"recorded": True}

    def get_log(self) -> ResearchLog:
        """Return the complete research log."""
        return self.log
```

### 6.3 Log Output Example

After a research session, the log might look like:

```markdown
# Research Log: a3f8b2c1

Started: 2024-01-15T10:30:00Z

## Summary

- Tool calls: 6
- Reasoning entries: 6
- Findings: 4
- Storylines: 2

## Timeline

### 💭 Reasoning [exploration]

> Getting broad overview of week 8 to identify interesting storylines

### 🔧 Tool: `get_league_snapshot`

**Params:** `{'week': 8}`
**Result:** 12 teams, 6 games, 3 transactions

### 📌 Finding

**Fact:** Team Underdog (3-4) beat Team Favorite (6-1) by 32 points
**Significance:** Major upset—potential lead story

### 💭 Reasoning [investigation]

> Investigating the upset—want to see which players drove the win

### 🔧 Tool: `get_team_game_with_players`

**Params:** `{'roster_key': 'Team Underdog', 'week': 8}`
**Result:** 9 players, 142.3 total points

### 📌 Finding

**Fact:** Josh Allen scored 38.7 points for Team Underdog, season high
**Significance:** Key contributor to the upset—individual performance storyline

### 📰 Storyline Idea (Priority 1)

**David Beats Goliath: Team Underdog Stuns the League**

### 💭 Reasoning [investigation]

> User mentioned the CMC trade—finding that transaction

### 🔧 Tool: `get_transactions`

**Params:** `{'week_from': 1, 'week_to': 8}`
**Result:** 47 transactions

...

### ✅ Research Complete
```

### 6.4 Integration with ArticleOutput

The research log is included in the final output:

```python
@dataclass
class ArticleOutput:
    article: str
    config: ReportConfig
    brief: ReportBrief
    research_log: ResearchLog          # NEW: Full research trace
    verification: Optional[VerificationResult] = None
    trace_id: Optional[str] = None
```

This allows:

- **Debugging**: See exactly why the agent made each tool call
- **Quality analysis**: Identify if agent is under-researching or over-researching
- **Intent tracking**: Understand the agent's editorial reasoning
- **Audit trail**: Full provenance from request → research → article

---

### 7. Draft Phase (unchanged conceptually)

The draft phase remains tool-free, writing from the brief:

```python
class DraftAgent:
    """Agent that writes the article from a brief."""

    async def draft(self, brief: ReportBrief, config: ReportConfig) -> str:
        system_prompt = self._build_draft_prompt(config)

        agent = Agent(
            name="writer",
            instructions=system_prompt,
            model="gpt-5-mini",
            tools=[],  # No tools in draft phase
        )

        user_prompt = f"""
Write the article based on this research brief:

{brief.model_dump_json(indent=2)}

Requirements:
- Voice: {config.voice}
- Length: ~{config.length_target} words
- Use ONLY the facts from the brief
- Follow the outline structure
{config.custom_instructions}
"""

        result = await Runner.run(agent, user_prompt)
        return result.final_output
```

---

## Simplified Request Flow

```python
class ReporterAgent:
    """Main agent orchestrating research and drafting."""

    async def run(self, request: str, **kwargs) -> ArticleOutput:
        # 1. Parse request into minimal config
        config = self._parse_request(request, **kwargs)

        # 2. Research phase (agent with tools)
        research_agent = ResearchAgent(self.data, config)
        brief = await research_agent.research()

        # 3. Draft phase (agent without tools)
        draft_agent = DraftAgent(config)
        article = await draft_agent.draft(brief, config)

        return ArticleOutput(
            article=article,
            config=config,
            brief=brief,
        )

    def _parse_request(self, request: str, **kwargs) -> ReportConfig:
        """Extract config from natural language request."""
        # Could be LLM-powered or simple regex/keyword extraction
        # Key fields: week, voice, focus_hints, bias
        ...
```

---

## File Changes Summary

### Delete

- `specs.py`: ArticleType enum, preset templates, StructureSpec

### Modify

- `reporter_agent.py`:
  - Remove `gather_data()` method entirely
  - Remove `build_brief()` method entirely
  - Add ResearchAgent with agentic loop
  - Simplify `run()` to just orchestrate phases

- `schemas.py`:
  - Rename ReportSpec → ReportConfig
  - Remove structure-related fields
  - Add focus_hints, avoid_topics, custom_instructions
  - Add ResearchLogEntry, ResearchLog schemas

- `workflows.py`:
  - Update convenience functions
  - Remove preset-based functions (generate_power_rankings, etc.)
  - Add simple `generate_report(request: str, week: int, **kwargs)`

- `tools/sleeper_tools.py`:
  - Replace SleeperToolAdapter → ResearchToolAdapter
  - Add ResearchLog tracking with reasoning linkage
  - Add log export methods (to_markdown, get_tool_calls_with_reasoning)

- `tools/registry.py`:
  - Add reasoning tools: log_reasoning, record_finding, note_storyline_idea, mark_research_complete
  - Keep all existing data retrieval tools

### Add

- `prompts/research_agent.md`: System prompt for research phase
- `prompts/draft_agent.md`: System prompt for draft phase
- `agent/research_log.py`: ResearchLog and ResearchLogEntry classes
- `agent/clarify.py`: ClarificationAgent for interactive requirements gathering
- `cli.py`: Interactive CLI application
- `scripts/reporter`: Shell wrapper for CLI

---

## Example Interaction

**User request:**

```
"Write a snarky recap of week 8. Focus on any upsets and that
hilarious trade where Team Taco gave up CMC for pennies."
```

**Parsed config:**

```python
ReportConfig(
    time_range=TimeRange(week_start=8, week_end=8),
    focus_hints=["upsets", "trades"],
    focus_teams=["Team Taco"],
    voice="snarky columnist",
    tone=ToneControls(snark_level=2, hype_level=1),
    custom_instructions="Mention the CMC trade as particularly bad",
)
```

**Research agent flow:**

1. `get_league_snapshot(week=8)` → sees standings, all games
2. Notices Team Underdog beat Team Favorite → investigates
3. `get_team_game_with_players("Team Underdog", week=8)` → finds the stars
4. `get_transactions(week_from=1, week_to=8)` → finds the CMC trade
5. `get_team_dossier("Team Taco")` → sees their record since the trade
6. Builds brief with storylines:
   - Priority 1: "Team Underdog Shocks the League"
   - Priority 2: "The Trade That Keeps Getting Worse"
   - Priority 3: "Playoff Picture Tightens"

**Draft agent:**

- Receives brief with facts and storylines
- Writes snarky article following the agent-determined structure
- Roasts Team Taco appropriately

---

## Migration Path

### Phase 1: Core Refactor

1. Create `ReportConfig` alongside existing `ReportSpec`
2. Implement `ResearchAgent` with agentic research loop
3. Test with simple requests

### Phase 2: Remove Presets

1. Delete preset constants and enum
2. Update any code depending on article_type
3. Simplify schemas

### Phase 3: Polish

1. Tune research agent prompts
2. Add research_note tool for observability
3. Update CLI/runner for new interface

---

## Benefits

1. **Flexibility**: Any request works, not just four article types
2. **Intelligence**: Agent finds interesting stories, not thresholds
3. **Depth**: Agent can follow threads and investigate
4. **Simplicity**: Less code—agent does the work, not if/else chains
5. **Observability**: Agent's reasoning visible in tool calls and notes
6. **Quality**: Editorial judgment, not mechanical extraction

---

## Risks and Mitigations

| Risk                                         | Mitigation                                                      |
| -------------------------------------------- | --------------------------------------------------------------- |
| Agent might not call enough tools            | Prompt engineering: "thoroughly research before building brief" |
| Agent might fabricate instead of researching | Structured output forces proper brief format with data_refs     |
| Research might be unfocused                  | Config focus_hints guide the agent                              |
| Higher latency (more LLM calls)              | Acceptable tradeoff for quality; cache tool results             |
| Cost increase                                | Use efficient prompting; consider smaller model for research    |

---

## Open Questions

1. **Structured output vs. free-form brief building**: Should the agent fill a Pydantic model directly, or output JSON that we parse?

2. **Research budget**: Should we limit tool calls or let the agent decide when it has enough?

3. **Verification phase**: Keep the verification phase, or trust the brief-first approach?

4. **Streaming**: Can we stream the draft as it's written while keeping tools disabled?
