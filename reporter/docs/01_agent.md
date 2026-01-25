## AI Fantasy Football Reporter — Design Document (High-Level)

### 1) Overview

You’re building an **AI reporter** for a Sleeper fantasy football league that generates engaging, data-grounded articles: weekly recaps, team deep dives, power rankings, playoff reactions, and style/tone variations (including optional “bias” toward/against teams).

This document describes a **single-agent architecture using OpenAI’s Agents SDK**, with a strong emphasis on:

* **high-quality, preprocessed JSON tools** via a Sleeper data layer
* **structured intermediate artifacts** (spec → brief → draft → verify)
* **observability/tracing** for fast iteration
* **extensibility to multi-agent** later with minimal refactor

---

### 2) Goals and Non-Goals

#### Goals

* Produce **factually grounded** articles derived from Sleeper data.
* Support both **preset** and **ad-hoc** custom report requests.
* Allow optional **bias configuration** that affects *framing* but not *facts*.
* Keep design modular so you can **upgrade to multi-agent** (researcher/writer/editor) later.

#### Non-Goals (for v1)

* Real-time web research or external news ingestion.
* Full UI productization (the initial interface can be CLI or minimal web).
* Fully automated “publisher pipeline” (scheduling, notifications, etc.)—can be added later.

---

### 3) Key Design Choices (and Why)

#### 3.1 Single Agent with Explicit Phases (Spec → Brief → Draft → Verify)

Even with one agent, you’ll enforce distinct “roles” as **phases**:

1. **Spec Synthesis** (interpret request → `ReportSpec`)
2. **Plan & Research** (tool-heavy)
3. **Generate a structured ReportBrief** (JSON, evidence-backed)
4. **Draft article** (style + bias applied; minimal/no tool calls)
5. **Verify** (cross-check numeric claims and key statements against the brief/tool evidence)

**Why**

* Provides most benefits of multi-agent (separation of concerns) without orchestration overhead.
* Makes debugging and evals simpler: you can inspect the ReportBrief to see what the agent “believes.”

#### 3.2 OpenAI Agents SDK for Orchestration + Tracing

You chose Agents SDK for:

* **built-in tracing/observability**
* structured tool use
* an easy upgrade path to handoffs/multi-agent later

**Why**

* In tool-heavy agentic apps, iteration speed depends on “why did it do that?” visibility.

#### 3.3 Tool Surface: “Context Packs” + “Deep Dives”

Your data layer will expose tools that return preprocessed JSON (e.g., week recap pack, trade aggregations, roster trends). Prefer a small number of **high-leverage tools** over dozens of tiny ones.

**Why**

* Reduces tool selection errors and prompt bloat.
* Encourages consistent output structure and easier caching.

#### 3.4 Bias as a Writing-Layer Concern Only

Bias influences adjectives, emphasis, jokes, narrative framing—but not factual claims.

**Why**

* Prevents “biased facts” and preserves trust.
* Enables user-configurable personalities without corrupting analytics.

#### 3.5 Spec-First Reporting (ReportSpec → ReportBrief)

Introduce a **ReportSpec** layer that captures format, voice, constraints, and evidence policy before any research or drafting.

**Why**

* Enables **true flexibility** without sacrificing reliability.
* Presets become **default spec templates**, not hardcoded entry points.
* The spec acts as **guardrails** for tone, structure, and factuality.

---

### 4) System Architecture

#### 4.1 Components

1. **Agent Runtime (Agents SDK)**

   * Defines the single “Reporter Agent”
   * Manages tool calls, context, and tracing

2. **Prompting & Style System**

   * System prompt template + injectable style preset + bias profile
   * Article-type templates (weekly recap, power rankings, etc.)

3. **Spec System**

   * `ReportSpec` schema (filled for presets and custom requests)
   * Optional “spec interview” step when key fields are missing
   * Evidence policy + bias boundaries baked into the spec

4. **Sleeper Data Layer**

   * Fetch + normalize Sleeper API data
   * Precompute derived stats and aggregates
   * Expose tool-friendly JSON return objects

5. **Tool Adapters**

   * Thin wrappers that adapt datalayer methods into SDK tool functions
   * Perform validation, caching, and error normalization

6. **Orchestrator**

   * The “runner” that:

     * selects article type and config
     * invokes the agent
     * enforces phase gating (where possible)
     * stores outputs and traces
     * optionally runs offline evals

7. **Evaluation Harness**

   * Snapshot league state (per week) for deterministic tests
   * Regression tests for factuality + structure + style adherence

---

### 5) Agent Design

#### 5.1 Inputs

* `article_type`: {weekly_recap, team_deep_dive, power_rankings, playoff_reaction, …}
* `time_range`: {week N, weeks N–M, “last 14 days”, etc.}
* `style_preset`: {straight_news, hype_man, snarky_columnist, poetic, ESPN-ish, …}
* `bias_profile` (optional):

  * favored_teams: [...]
  * disfavored_teams: [...]
  * intensity: 0–3
  * allowed_targets: e.g. “playful trash talk only”
* `constraints`:

  * length target
  * must-include sections
  * profanity policy
  * “do not mention injuries” etc. (optional user constraints)

#### 5.2 Spec Layer: `ReportSpec` (Structured JSON)

This drives what gets researched, how it is presented, and what is allowed.

**Suggested shape (high-level):**

* `genre_voice`: e.g. “noir detective”, “sports radio rant”, “financial analyst note”
* `tone_controls`: snark level, hype level, profanity policy, seriousness
* `structure`: section list (or “freeform”), length, POV, narration constraints
* `content_requirements`: must cover top matchups, standings implications, trades
* `bias_profile`: targets + intensity + boundaries
* `evidence_policy`: “every number must be cited from tools”, “no unverifiable injury claims”
* `audience`: league members, newcomers, commissioner, etc.

**Preset mapping**

* Each preset becomes a **filled `ReportSpec` template**
* Custom prompts synthesize a `ReportSpec` that can override a preset or stand alone

#### 5.3 Core Internal Artifact: `ReportBrief` (Structured JSON)

This is the backbone of reliability and future multi-agent handoffs.

**Suggested shape (high-level):**

* `meta`: league name, week range, generation timestamp, article type
* `facts`: list of factual claims, each with:

  * `claim_text`
  * `data_refs` (tool call references/keys)
  * `numbers` (explicit numeric fields where possible)
* `storylines`: ranked list with:

  * `headline`
  * `summary`
  * `supporting_facts` (references to `facts`)
* `outline`: ordered sections with bullet points and which facts must appear
* `style`: resolved style preset (voice, pacing, humor)
* `bias`: resolved bias framing rules (what is allowed)

**Why this matters**

* Makes outputs inspectable.
* Lets you fact-check deterministically.
* Becomes the handoff artifact for multi-agent later.

#### 5.4 Tool Use Policy

The agent is encouraged to:

* call “context pack” tools early
* identify gaps
* call targeted deep-dive tools
* build `ReportBrief` first

Then:

* draft from brief
* verify against brief

**Implementation note**
You can enforce this via:

* runner-level “phase” state
* prompt-level instructions (“Do not call tools during drafting unless missing evidence”)
* optional: separate runs (first run produces brief only; second run drafts only)

That last pattern is extremely robust: it simulates multi-agent separation while still using one agent.

---

#### 5.5 Spec Completion + Clarifying Questions (Optional)

If the request is vague, add a lightweight **spec interview** step:

* Generate a draft `ReportSpec` with defaults
* Detect missing fields that materially affect structure or tone
* Ask 1–3 targeted questions (format, time range, tone) and proceed

This keeps flexibility high without getting stuck in long back-and-forth.

---

### 6) Data Layer and Tools

#### 6.1 Data Layer Responsibilities

* Fetch from Sleeper API on startup (or on demand with caching)
* Normalize into stable schema
* Compute derived artifacts (weekly results, standings deltas, transaction summaries, player trendlines, trade impact by team/week)
* Provide JSON returns designed for LLM consumption (clear field names, consistent shapes, explicit units)

#### 6.2 Tool Adapter Responsibilities

* Validate inputs (e.g., week numbers, team identifiers)
* Normalize errors (e.g., week out of range)
* Add caching keys
* Ensure deterministic ordering of arrays where it matters (helps eval stability)

#### 6.3 Tool Surface Philosophy

* Prefer **8–12 tools total** initially.
* A few “packs”:

  * `get_week_context(week)`
  * `get_team_context(team_id, weeks)`
  * `get_transactions_context(weeks or date range)`
* A few deep dives:

  * `get_trade_impact(team_id, weeks)`
  * `get_roster_timeseries(team_id, weeks)`
  * `get_matchup_context(matchup_id)`

(You’ll fill in the exact list.)

---

### 7) File and Project Structure

A Python-first structure that cleanly separates agent, prompts, tools, and data.

```
fantasy_reporter/
  README.md
  pyproject.toml
  .env.example

  src/
    fantasy_reporter/
      __init__.py

      app/
        runner.py              # CLI/web entrypoints call into here
        config.py              # loads env vars, defaults, article presets
        logging.py             # structured logging + trace hooks
        caching.py             # cache interface (memory, sqlite, disk)

      agent/
        reporter_agent.py      # Agents SDK agent definition
        workflows.py           # “Spec->Brief->Draft->Verify” orchestration helpers
        schemas.py             # Pydantic models: ReportBrief, ArticleRequest, ArticleOutput
        policies.py            # tool use rules, bias rules, safety constraints
        specs.py               # Pydantic ReportSpec + defaults

      prompts/
        system_base.md         # core reporter instruction set
        spec_synthesis.md      # convert arbitrary request -> ReportSpec
        formats/
          weekly_recap.md
          power_rankings.md
          team_deep_dive.md
          playoff_reaction.md
        styles/
          straight_news.md
          snarky_columnist.md
          hype_man.md
        bias/
          bias_rules.md        # bias constraints + examples
        style_atoms/           # optional reusable voice fragments (future)

      tools/
        __init__.py
        registry.py            # collects tool functions for the agent
        sleeper_tools.py       # tool wrappers around datalayer
        tool_utils.py          # validation helpers, error normalization

      evals/
        __init__.py
        snapshots.py           # capture/load frozen league snapshots
        tests_factuality.py    # ensures article facts match brief/tool outputs
        tests_style.py         # length, section structure, tone constraints
        golden/                # saved snapshot fixtures by week

      web/ (optional later)
        api.py                 # minimal FastAPI endpoint wrapper
        ui.py                  # tiny UI or webhook integration

  scripts/
    run_weekly_recap.py
    snapshot_week.py
```

#### Why this structure works

* `agent/` is isolated from `datalayer/` via `tools/` adapters.
* `prompts/` is versionable and testable.
* `evals/` is first-class, enabling regression tests as behavior evolves.
* `workflows.py` becomes the seam for future multi-agent handoffs.

---

### 8) Request Flow

1. User (or cron/script) creates an `ArticleRequest`
2. Runner loads:

   * system base prompt
   * article format prompt (preset → spec template)
   * style preset prompt
   * bias rules prompt (optional)
3. **Spec synthesis**:

   * interpret request → `ReportSpec`
   * optional spec interview if missing key fields
4. Runner initializes data layer and tool registry
5. Agent executes:

   * (optional) refine `ReportSpec`
   * tool calls → build `ReportBrief`
   * draft article from brief
   * verify pass
6. Output saved:

   * article markdown
   * `ReportBrief` JSON
   * `ReportSpec` JSON
   * trace ID / trace export
   * evaluation report (optional)

---

### 9) Extensibility to Multi-Agent (Future Plan)

You’ll transition by reusing the same artifacts and tools, changing only orchestration.

#### Proposed future agents

* **Spec Planner Agent**

  * produces `ReportSpec` only
  * asks clarifying questions when needed
* **Researcher Agent**

  * allowed tools
  * outputs `ReportBrief` only
* **Writer Agent**

  * no tools (or very limited)
  * consumes `ReportBrief` + style/bias
  * outputs draft
* **Editor/Fact-checker Agent**

  * compares draft claims to brief
  * requests revisions or produces a corrected final

#### How to implement later with minimal refactor

* Keep `ReportSpec` and `ReportBrief` as stable handoff contracts in `agent/`.
* Move today’s “phase separation” into explicit Agents SDK handoffs:

  * `handoff(spec_planner) -> ReportSpec`
  * `handoff(researcher) -> ReportBrief`
  * `handoff(writer) -> Draft`
  * `handoff(editor) -> Final`

Because v1 already uses “spec-first” and “brief-first” logic, this upgrade is mostly wiring—**not a redesign**.

---

### 10) Observability and Debugging

#### Tracing strategy

* Record:

  * tool calls + inputs/outputs
  * intermediate `ReportSpec` + `ReportBrief`
  * final article
  * verification results
* Tag traces with:

  * `article_type`, `week_range`, `style_preset`, `bias_intensity`

#### Debug workflow

* When output is weak:

  1. Inspect `ReportSpec` → structure/tone/evidence constraints correct?
  2. Inspect `ReportBrief` → missing facts? wrong storyline selection?
  3. Inspect tool calls → did it call the right packs?
  4. Adjust prompts/policies → improve storyline ranking, section requirements
  5. Add/adjust a context-pack tool → reduce cognitive load

This is why the SDK tracing is valuable: you can see exactly where behavior drift happened.

---

### 11) Evaluation Plan (High-Level)

To keep quality improving over time:

* **Snapshot fixtures**: capture a week’s league data into `evals/golden/`
* **Factuality tests**:

  * All numeric claims in article appear in `ReportBrief.facts`
  * Facts reference tool outputs
* **Structure tests**:

  * Required sections exist for each article type
  * Length ranges met
* **Style tests**:

  * Tone constraints (e.g., profanity policy)
  * Bias boundaries respected (“facts neutral; framing biased”)
* **Spec tests**:

  * Required spec fields resolved before drafting
  * Evidence policy enforced during verify

---

### 12) Implementation Notes and Milestones

#### Milestone 1: Minimal end-to-end weekly recap

* Data layer loads league snapshot
* 1–2 context pack tools
* Agent generates `ReportSpec` → `ReportBrief` → recap
* Save outputs + trace

#### Milestone 2: Add 2–3 more article types

* power rankings
* team deep dive
* playoff reaction template

#### Milestone 3: Add verification + eval snapshots

* numeric claim verification
* regression tests on golden weeks

#### Milestone 4: Optional multi-agent upgrade

* introduce spec planner/researcher/writer separation via handoffs

---

## Deliverables from this design doc

* A clean, modular repo layout
* A single-agent workflow that behaves like multiple roles
* Stable intermediate artifacts (`ReportSpec`, `ReportBrief`) that enable:

  * debugging
  * verification
  * future multi-agent handoffs

If you want, I can also provide:

* a concrete `ReportBrief` Pydantic schema (fields + types),
* a prompt template set for the base system + article formats + style presets,
* and a “tool registry” pattern that keeps tool count manageable while still enabling deep reporting.
