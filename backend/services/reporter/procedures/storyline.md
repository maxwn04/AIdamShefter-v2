# Storyline Procedure

Use this procedure for deliberate storyline mining and narrative synthesis. Storyline work may happen after a broad scan, between targeted research calls, while reshaping a draft, or during verification. It is not a mandatory bridge between research and drafting.

## Operating Rules

- Call `read_brief` when you do not already hold the current structured state.
- Every storyline recorded as verified must be supported by existing fact IDs. A promising unsupported angle is a research hypothesis: make the narrow calls needed to prove or reject it before recording it.
- Storyline summaries may interpret the data, but they must not add new factual claims.
- Save developed angles with `save_storyline`, then use `set_outline` if a formal plan will help. Refresh stale dependent items when later research changes their evidence.
- Bias is framing only. Preserve the user's framing preferences without altering scores, records, or outcomes.
- A callback used in the article must point to two saved brief facts: one old-event fact reverified against frozen data and one current-event fact. Retrieved memory is only the lead that prompted the investigation.
- Successful brief-tool results include revision and readiness; do not reread solely to confirm them.
- A small evidence gap does not require loading the research procedure. Investigate it directly, update the brief, and continue mining the angle. Load `research` only when the gap opens a substantial new investigation.
- Inspecting or drafting a paragraph can be a useful test of whether a storyline has enough specificity. If prose exposes a weak premise, strengthen or drop the angle rather than forcing it into the outline.

## Storyline Mining Loop

For a standard weekly recap, 3-6 developed angles is a useful range rather than a quota; use fewer for narrow requests. Prefer fewer well-supported storylines over filling slots. Save each developed narrative thread with `save_storyline`.

For each candidate angle:

1. Name the change or tension, not merely the result.
2. Identify the supporting facts already present and the exact evidence gaps.
3. Check current-week data and memory for reversal, payoff, continuity, irony, or future stakes.
4. Verify high-value gaps and reject angles that remain vague or incidental.
5. Rank surviving storylines by reader value and article fit, then update the outline or draft as appropriate.

Priority guidance:

- `1`: lead story. Major upset, playoff swing, dominant performance, season-defining trend, or request-specific focus.
- `2`: secondary story. Close game, important streak, notable breakout, trade fallout, or standings movement.
- `3`: useful color. Routine wins, smaller stat nuggets, or supporting angles.
- `4-5`: minor mentions that should only appear if space allows.

Good `save_storyline` input:

```json
{
  "id": "story_taco_statement_win",
  "headline": "Team Taco Turns A Win Into A Warning Shot",
  "summary": "The margin and player production make the Week 8 win a statement.",
  "supporting_fact_ids": ["fact_week8_taco_win", "fact_week8_taco_top_players"],
  "priority": 1,
  "tags": ["blowout", "contender", "week_8"]
}
```

## Style And Bias

Style and bias are immutable request context already present in the brief. Apply
them as framing constraints; do not spend tool calls restating or changing them.

## Outline Creation

Use `set_outline` when a formal writing plan will help. Each section should include:

- `title`: concise section heading.
- `bullet_points`: what the section must accomplish.
- `required_fact_ids`: exact facts the writer must use.
- `storyline_ids`: storylines that belong in the section.

A possible weekly recap structure:

1. Opening hook: lead with the priority-1 storyline and set the week's theme.
2. Lead story: give the strongest matchup or narrative enough room.
3. Supporting storylines: cover the next 2-3 important arcs.
4. Quick hits: short notes for lower-priority items, top performers, or transactions.
5. Standings or outlook: playoff implications, next-week stakes, or season trajectory.
6. Closing: resolve the article with the strongest takeaway.

For power rankings, one section per rank or tier may work. For team deep dives, useful sections often include record, recent games, roster strengths or weaknesses, transactions, and outlook. Build only as much outline as the article needs, and revise it when new evidence changes the article's shape.

## Typed Memory Proposals

If typed memory proposal tools are available, buffer durable narrative state when it becomes clear; do not wait for a separate pre-drafting checkpoint:

- Use `propose_storyline` for new durable arcs and `replace_storyline` only for canonical items returned by `search_memory` with an exact expected revision.
- Use `propose_event` for inferred matchup or trade evidence and `propose_trigger` for typed rematch or trade-evaluation callbacks.
- Use `propose_context_note` for franchise, season, or competition context.
- Use `propose_fact` for reusable claims. Fact and event proposals are `unverified` or `inferred`; source-backed receipts are not available in this tool version.
- Save verified callbacks with `save_memory_callback` if they were not already saved during research.
- Proposal results may be referenced by later proposals in the same bundle, but buffered proposals do not appear in `search_memory` and cannot be replaced during the same run.

Persist an arc only if it has either a plausible future callback condition or clear season-long significance. Useful durable arc types include:

- `trade_payoff`
- `trade_regret`
- `trade_flop`
- `revenge_game`
- `regular_season_sweep`
- `playoff_reversal`
- `close_game_callback`
- `waiver_hero`
- `rivalry_escalation`
- `lineup_mistake_repeat`

Keep complete typed arc metadata in the proposal content. Use a concise structured summary when narrative context needs more explanation:

```text
Arc type: trade_regret
Origin week: 3
Involved: Team A, Team B, Player X, Player Y
Receipt: Team A traded Player X for Player Y before Week 3.
Why it may matter later: Player X could swing a playoff matchup against Team A.
Next callback trigger: Team A faces Team B, Player X faces Team A, or either side loses a playoff game because of the trade assets.
Verification needed before use: confirm original trade receipt and current payoff with saved brief facts.
```

When the narrative plan is useful, continue with the action that most improves the article. That may be drafting, targeted research, verification, or further storyline mining. Do not load `drafting` solely to announce a phase transition.
