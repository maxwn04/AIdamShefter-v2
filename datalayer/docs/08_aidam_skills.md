# Design Doc: AIdam Shefter Skills for Claude Code

## Summary

Replace the OpenAI Agents SDK reporter pipeline with Claude Code skills backed by the datalayer CLI. A single `/aidam-report` skill orchestrates the full pipeline — curation, research, and drafting — using `sleeperdl` CLI commands for data access and the Agent tool for parallel research subagents that preserve the main context window.

---

## Goals

* **Single invocation**: `/aidam-report "snarky weekly recap"` produces a complete article.
* **Context-efficient**: Subagents handle raw JSON from queries; main agent works with summarized facts.
* **Same data grounding**: Facts-first research, brief-as-contract, bias-is-framing-only — all principles carry over.
* **Persistent storylines**: Same ContextStore (`.data/context.db`), accessed via new CLI commands.
* **Re-runnable phases**: Standalone `/aidam-draft` skill allows re-drafting from an existing brief without re-researching.

## Non-goals

* MCP server (future optimization — CLI is sufficient for now).
* Changing the datalayer internals or query logic.
* Replacing the existing OpenAI-based reporter (both can coexist).

---

## Architecture

```
User: /aidam-report "snarky recap, roast Team Taco" --week 8

Claude (main agent):
  Phase 0: Parse & Load
    sleeperdl load                                    # cache data
    sleeperdl context storylines                      # read existing storylines

  Phase 1: Curate
    [Reason] which storylines are relevant to this article
    [Reason] suggest new storyline hypotheses

  Phase 2: Research (via subagents)
    Agent("research broad context")                   # league_snapshot, standings
    Agent("investigate Team A upset")                 # team_game, team_dossier
    Agent("investigate trade impacts")                # transactions, player_weekly_log
    ... (parallel subagents, each returns summarized facts)

  Phase 3: Synthesize
    Collect facts from subagents
    Build storylines, rank by priority
    Write brief → .output/brief_week8.json

  Phase 4: Draft
    Read brief from file
    Write article following voice/tone/bias config
    Save → .output/article_week8.md

  Phase 5: Persist
    sleeperdl context save-storyline ...
    sleeperdl context save-team ...
```

---

## Part 1: CLI Changes

### 1.1 `sleeperdl load` — Cache data to disk

**New subcommand** that fetches from Sleeper API and saves to a SQLite file for subsequent queries.

```bash
sleeperdl load                          # → .cache/sleeper/<league_id>.sqlite
sleeperdl load --refresh                # force re-fetch even if cache exists
sleeperdl load --league-id 12345        # override league
```

**Behavior:**
- If `.cache/sleeper/<league_id>.sqlite` exists and is less than 1 hour old, skip fetch (print "Using cached data").
- If `--refresh` passed or cache is stale, fetch fresh and overwrite.
- Uses the existing `SleeperLeagueData.load()` + `save_to_file()` path.

**Why:** Every `sleeperdl query` call needs data. Without caching, each call does a full API fetch (~5-10s). With caching, the first call fetches and subsequent calls load from disk (~100ms).

### 1.2 `sleeperdl query <tool> [args...]` — One-shot queries

**New subcommand** that runs a single tool/query and prints JSON to stdout.

```bash
sleeperdl query league_snapshot week=8
sleeperdl query team_dossier roster_key=Schefter week=8
sleeperdl query player_weekly_log player_key="Patrick Mahomes"
sleeperdl query run_sql query="SELECT team_name, wins FROM standings WHERE week=8"
sleeperdl query standings
```

**Behavior:**
1. Load from cached SQLite file (run `sleeperdl load` implicitly if no cache exists).
2. Parse tool name and arguments (reuse existing `_parse_tool_args` logic).
3. Execute via `create_tool_handlers(data)`.
4. Print JSON to stdout.
5. Exit with code 0 (success) or 1 (error).

**Argument syntax:** Same as the interactive `app` — positional or `key=value`, with `shlex`-style quoting for strings with spaces.

### 1.3 `sleeperdl context` — Context store CLI

**New subcommand group** for reading/writing the persistent context store.

#### Read commands

```bash
sleeperdl context storylines                     # active + stale storylines (JSON)
sleeperdl context storylines --include-resolved   # include resolved
sleeperdl context enriched story_001 story_002    # enriched with history + facts
sleeperdl context teams                           # all team context notes
sleeperdl context team "Team Taco"                # one team's context
sleeperdl context league                          # league-wide notes
sleeperdl context full                            # combined context (storylines + teams + league)
```

#### Write commands

```bash
sleeperdl context save-storyline \
  --id story_w8_upset \
  --headline "Cinderella Run Continues" \
  --summary "Team Underdog extends win streak to 4" \
  --status active \
  --priority 1 \
  --tags upset,streak \
  --teams "Team Underdog,Team Favorite" \
  --week 8

sleeperdl context save-team \
  --roster-key "Team Taco" \
  --narrative "3-game win streak, strong at WR, contending for playoffs" \
  --outlook surging \
  --week 8

sleeperdl context save-league-note \
  --key season_theme \
  --value "Parity season — no dominant team through week 8" \
  --week 8
```

**Implementation:** Wire up to existing `ContextStore` methods. The `--week` parameter is required for write commands. Read commands create a `ContextStore` instance scoped to the league_id and season from the cached data.

---

## Part 2: Skills

### 2.1 `/aidam-report` — Main orchestrator skill

**File:** `.claude/skills/aidam-report/SKILL.md`

This is the primary skill. It contains the full pipeline instructions organized into phases. The skill prompt is structured as:

```
Phase 0: Parse & Load
Phase 1: Curate Storylines
Phase 2: Research (with subagent strategy)
Phase 3: Synthesize Brief
Phase 4: Draft Article
Phase 5: Persist Context
```

#### Phase 0: Parse & Load

Instructions for Claude to:
- Interpret the user's natural language request into config parameters (week, voice, tone, bias, focus teams, etc.).
- Run `sleeperdl load` to ensure cached data.
- Read the current week from `sleeperdl query standings` if not specified.
- If the request is ambiguous, ask the user for clarification before proceeding.

**Config parameters to extract:**
| Parameter | Default | Examples |
|-----------|---------|----------|
| week | current | "week 8", "last week" |
| voice | sports columnist | "snarky", "hype", "noir detective" |
| snark_level | 1 | "roast" → 3, "playful" → 2 |
| hype_level | 1 | "hype" → 3, "measured" → 0 |
| focus_teams | [] | "focus on Team Taco" |
| favored_teams | [] | "hype up Team Taco" |
| disfavored_teams | [] | "roast Team Taco" |
| bias_intensity | 2 | implicit from language |
| length_target | 1000 | "short" → 500, "deep dive" → 2000 |
| focus_hints | [] | "upsets", "trades", "standings" |

#### Phase 1: Curate Storylines

Instructions for Claude to:
1. Run `sleeperdl context storylines` to get active/stale storylines.
2. If storylines exist, reason about which are relevant to this article request.
3. For broad requests (weekly recap), include most active storylines.
4. For narrow requests (team deep dive), only include directly relevant ones.
5. Note 1-3 new storyline hypotheses to investigate during research.

This replaces the `StorylineCurator` agent — it's just Claude reasoning, no separate LLM call needed.

#### Phase 2: Research (Subagent Strategy)

This is the core of the skill. The instructions tell Claude to:

1. **Broad research first (main agent):**
   - Run `sleeperdl query league_snapshot week=N` in the main context.
   - Scan results to identify 3-5 research threads (upsets, close games, streaks, trades, etc.).

2. **Dispatch subagents for deep research:**
   Each subagent gets a focused prompt and returns summarized facts.

   ```
   Launch subagents in parallel using the Agent tool:

   For each research thread you identified, launch a subagent with:
   - A clear research question ("Investigate Team X's upset victory in week 8")
   - The specific sleeperdl query commands to run
   - Instructions to return a JSON list of facts in this format:
     {"id": "fact_001", "claim_text": "...", "data_refs": ["..."], "numbers": {...}, "category": "score|standing|transaction|player|general"}
   - Instructions to also return any storyline observations

   Example subagent prompts:
   - "Research the matchup between Team A and Team B in week 8. Run: sleeperdl query team_game roster_key='Team A' week=8, sleeperdl query team_dossier roster_key='Team A' week=8, sleeperdl query team_dossier roster_key='Team B' week=8. Return facts about scores, key players, standings implications."
   - "Research all transactions in week 8. Run: sleeperdl query transactions week_from=8 week_to=8. Return facts about trades, pickups, and their impact."
   - "Research top performers in week 8. Run: sleeperdl query week_player_leaderboard week=8 limit=10, then for the top 3, run sleeperdl query player_weekly_log player_key='...' to check if this was a breakout. Return facts about standout performances."
   ```

3. **Subagent guidelines:**
   - Each subagent should make 2-5 `sleeperdl query` calls.
   - Return structured facts, not raw JSON blobs.
   - Flag interesting storyline angles.
   - Total across all subagents: aim for 10-20 high-quality facts.

4. **Why subagents:**
   - Raw query JSON stays in subagent contexts (hundreds of lines of JSON per query).
   - Main agent only receives distilled facts (a few lines each).
   - Multiple research threads run in parallel.
   - Main context stays clean for synthesis and drafting.

5. **Fallback:** For simple requests (single team deep dive), skip subagents and research directly in the main context. Subagents are for multi-faceted articles (weekly recaps, power rankings).

#### Phase 3: Synthesize Brief

Instructions for Claude to:
1. Collect all facts returned by subagents.
2. Deduplicate and verify consistency (same score shouldn't appear twice with different numbers).
3. Group facts into storylines, ranked by priority:
   - **Priority 1:** Major upsets, dominant performances, playoff implications.
   - **Priority 2:** Close games, streaks, breakout players.
   - **Priority 3:** Routine results, minor transactions, stat nuggets.
4. Build an article outline with sections mapped to storylines and facts.
5. Resolve style (voice, pacing, humor_level, formality) and bias (framing rules) from config.
6. Write the complete brief as JSON to `.output/brief_week{N}.json`.

**Brief schema** (matches existing `ReportBrief`):
```json
{
  "meta": {"league_name", "league_id", "week_start", "week_end", "article_type"},
  "facts": [{"id", "claim_text", "data_refs", "numbers", "category"}],
  "storylines": [{"id", "headline", "summary", "supporting_fact_ids", "priority", "tags"}],
  "outline": [{"title", "bullet_points", "required_fact_ids", "storyline_ids"}],
  "style": {"voice", "pacing", "humor_level", "formality"},
  "bias": {"favored_teams", "disfavored_teams", "intensity", "framing_rules"}
}
```

#### Phase 4: Draft Article

Instructions for Claude to write the article from the brief. This section embeds the core content from `draft_agent.md` and `bias_rules.md`:

**Critical rules:**
- **Facts are sacred** — use ONLY facts from the brief, exact numbers, no invention.
- **Storylines guide structure** — lead with priority 1, weave in priority 2, priority 3 as color.
- **Bias is framing only** — word choice and emphasis, never facts.

**Voice catalog:**
| Voice | Style |
|-------|-------|
| Sports Columnist | Professional, informed, authoritative |
| Snarky Columnist | Witty, irreverent, playful jabs |
| Hype Broadcaster | High energy, exclamation-ready |
| Beat Reporter | Factual, measured, analytical |
| Noir Detective | Moody, atmospheric, dramatic |

**Bias intensity levels:**
| Level | Favored team | Disfavored team |
|-------|-------------|-----------------|
| 0 | Neutral | Neutral |
| 1 | Positive adjectives | Neutral language |
| 2 | Emphasize wins, enthusiasm | Frame struggles as expected |
| 3 | Celebrate, superlatives | Playful roasting |

**Article structure:**
1. Opening hook (lead with biggest story)
2. Main storylines (priority 1 gets most space)
3. Secondary stories (priority 2)
4. Quick hits (priority 3 as brief mentions)
5. Standings/context (if relevant)
6. Closing (energy, not whimper)

**Self-verification:** Before finalizing, check that every number in the article matches a fact in the brief.

**Output:** Write the article in Markdown to `.output/article_week{N}.md`.

#### Phase 5: Persist Context

Instructions for Claude to save context for future runs:
1. For each significant storyline, run `sleeperdl context save-storyline` with id, headline, summary, status, priority, tags, teams, and week.
2. For each team researched, run `sleeperdl context save-team` with narrative and outlook.
3. For league-wide themes, run `sleeperdl context save-league-note`.

### 2.2 `/aidam-draft` — Re-draft from existing brief

**File:** `.claude/skills/aidam-draft/SKILL.md`

Standalone skill for re-drafting an article from an existing brief with different parameters.

**Usage:** `/aidam-draft` — Claude will:
1. Find the most recent brief in `.output/` (or ask which one).
2. Ask for new voice/tone/bias parameters (or accept from the user's message).
3. Draft the article following the same rules as Phase 4 of `/aidam-report`.
4. Save to `.output/article_week{N}.md` (with confirmation before overwriting).

This is a focused subset of the report skill — just the drafting instructions and voice/bias catalogs.

---

## Part 3: Subagent Design Details

### When to use subagents vs. direct research

| Article type | Strategy |
|-------------|----------|
| Weekly recap | 3-4 subagents: broad context, top games, transactions, player highlights |
| Power rankings | 1 subagent per division/tier, or 2-3 subagents by team grouping |
| Team deep dive | No subagents — direct research in main context (focused enough) |
| Trade analysis | 1-2 subagents: trade details, player impact analysis |
| Playoff recap | 2-3 subagents: each bracket matchup |

### Subagent prompt template

Each research subagent receives a prompt like:

```
You are a fantasy football research assistant. Your job is to investigate
a specific research question using the sleeperdl CLI and return structured
facts.

## Research Question
{question}

## Context
Week: {week}
League cached at: .cache/sleeper/{league_id}.sqlite

## Commands to Run
Run these sleeperdl query commands and analyze the results:
{commands}

## Output Format
Return a JSON object with:
{
  "facts": [
    {
      "id": "fact_NNN",
      "claim_text": "One atomic factual claim",
      "data_refs": ["command that produced this"],
      "numbers": {"key": value},
      "category": "score|standing|transaction|player|general"
    }
  ],
  "storyline_notes": [
    "Any narrative observations worth highlighting"
  ]
}

## Rules
- Only report facts you can see in the query output
- Use exact numbers from the data
- Each fact should be atomic (one claim per fact)
- Aim for 3-8 high-quality facts
- Note anything surprising or storyline-worthy
```

### Subagent result handling

The main agent collects subagent results and:
1. Assigns globally unique fact IDs (re-prefix if needed).
2. Merges facts, deduplicating by claim content.
3. Incorporates storyline notes into the synthesis phase.

---

## Part 4: File Conventions

### Output directory: `.output/`

| File | Purpose |
|------|---------|
| `.output/brief_week{N}.json` | Research brief (JSON) |
| `.output/article_week{N}.md` | Final article (Markdown) |

### Cache directory: `.cache/sleeper/`

| File | Purpose |
|------|---------|
| `.cache/sleeper/{league_id}.sqlite` | Cached league data |

### Context database: `.data/context.db`

Same as existing — storylines, team context, league notes. No changes.

---

## Part 5: Implementation Order

### Step 1: `sleeperdl load` + `sleeperdl query` (CLI)

**Files:** `datalayer/cli/main.py`

- Add `load` subcommand (fetch + cache to `.cache/sleeper/`).
- Add `query` subcommand (load from cache + run tool + print JSON).
- Add cache staleness check (1-hour TTL, `--refresh` flag).
- Reuse existing `_parse_tool_args`, `create_tool_handlers`.
- Add `--from-cache` path override for loading from a specific file.

**Tests:** `datalayer/tests/integration/test_cli_query.py`
- Test `query` with each tool.
- Test cache creation and reuse.
- Test `--refresh` flag.

### Step 2: `sleeperdl context` (CLI)

**Files:** `datalayer/cli/main.py` (or new `datalayer/cli/context.py`)

- Add `context` subcommand group with read/write commands.
- Wire to `ContextStore` methods.
- Handle `--week` parameter for writes.
- Auto-resolve league_id and season from cached data.

**Tests:** `datalayer/tests/integration/test_cli_context.py`
- Test read/write round-trips.
- Test storyline lifecycle (create, update, resolve).

### Step 3: `/aidam-report` skill

**File:** `.claude/skills/aidam-report/SKILL.md`

- Write the comprehensive skill with all 5 phases.
- Embed voice catalog, bias rules, brief schema, subagent templates.
- Include the research guidelines and fact-building instructions.
- Include the drafting rules and self-verification checklist.

### Step 4: `/aidam-draft` skill

**File:** `.claude/skills/aidam-draft/SKILL.md`

- Extract Phase 4 from the report skill into a standalone skill.
- Add brief discovery logic (find latest in `.output/`).
- Include voice/bias catalogs.

### Step 5: Integration testing

- Run `/aidam-report` end-to-end with fixture data.
- Verify brief and article are saved correctly.
- Verify context persistence works across runs.
- Test subagent dispatch and fact collection.

---

## Appendix: Comparison with Current Reporter

| Aspect | OpenAI Agents SDK Reporter | Claude Code Skills |
|--------|---------------------------|-------------------|
| LLM | GPT (configurable) | Claude (native) |
| Orchestration | Python (ReporterAgent) | Skill prompt + subagents |
| Data access | Tool calls (in-process) | CLI commands (subprocess) |
| Clarification | ClarificationAgent | Claude asks directly |
| Curation | StorylineCurator (LLM call) | Claude reasons inline |
| Research | ResearchAgent (streamed) | Subagents (parallel) |
| Draft | DraftAgent (no tools) | Claude writes from brief |
| Context window | Each agent has own context | Subagents protect main context |
| Persistence | ContextStore (Python API) | ContextStore (CLI) |
| Output | ArticleOutput dataclass | Files in .output/ |
