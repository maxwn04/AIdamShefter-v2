# Storyline Procedure

You are turning verified facts into a usable article plan. Read `research/brief.md`, create storylines from its saved facts, record style and bias, and build an outline in the same Markdown artifact. Do not draft final article prose here.

## Operating Rules

- Use `read_artifact(path="research/brief.md")` first unless you just saved all relevant facts in the immediately preceding turn.
- Every storyline must be supported by existing fact IDs. If a needed fact is missing, switch back to `research` and get it.
- Storyline summaries may interpret the data, but they must not add new factual claims.
- Record the outline after the main storylines. If later research changes the facts or storylines, refresh the affected plan in the brief.
- Bias is framing only. Preserve the user's framing preferences without altering scores, records, or outcomes.
- Callback storylines must be supported by both an old-event fact or verified memory receipt and a current-event fact.
- Apply changes with `edit_artifact`, using an exact, unique replacement and the current brief revision. Preserve reusable insertion anchors when adding more material later.

## Storyline Creation

Create 3-6 storylines for a standard weekly recap and fewer for narrow requests. Record each narrative thread under the brief's storyline heading.

Priority guidance:

- `1`: lead story. Major upset, playoff swing, dominant performance, season-defining trend, or request-specific focus.
- `2`: secondary story. Close game, important streak, notable breakout, trade fallout, or standings movement.
- `3`: useful color. Routine wins, smaller stat nuggets, or supporting angles.
- `4-5`: minor mentions that should only appear if space allows.

Good storyline:

```markdown
### story_taco_statement_win

- Headline: Team Taco Turns A Win Into A Warning Shot
- Summary: Team Taco's 142.3-98.7 Week 8 win was more than a comfortable result. The margin and player-level production make it a lead candidate for the week's biggest statement.
- Supporting facts: `fact_week8_taco_win`, `fact_week8_taco_top_players`
- Priority: 1
- Tags: blowout, contender, week_8
```

## Style And Bias

Record style controls in the brief:

- `voice`: examples include `sports columnist`, `snarky columnist`, `hype broadcaster`, `beat reporter`, or a custom voice from the user.
- `pacing`: `fast`, `moderate`, or `deliberate`.
- `humor_level`: 0 for none, 1 for light, 2 for moderate, 3 for heavy.
- `formality`: `formal`, `casual`, or `irreverent`.

Record bias controls if the user asked to favor or roast teams:

- `favored_teams`: teams to frame positively.
- `disfavored_teams`: teams to frame skeptically or mockingly.
- `intensity`: 0-3.
- `framing_rules`: short reminders such as "celebrate wins, downplay losses" or "roast missed expectations, but keep all numbers exact".

## Outline Creation

Create the writing plan under the brief's outline heading. Each section should include:

- `title`: concise section heading.
- `bullet_points`: what the section must accomplish.
- `required_fact_ids`: exact facts the writer must use.
- `storyline_ids`: storylines that belong in the section.

Default weekly recap structure:

1. Opening hook: lead with the priority-1 storyline and set the week's theme.
2. Lead story: give the strongest matchup or narrative enough room.
3. Supporting storylines: cover the next 2-3 important arcs.
4. Quick hits: short notes for lower-priority items, top performers, or transactions.
5. Standings or outlook: playoff implications, next-week stakes, or season trajectory.
6. Closing: resolve the article with the strongest takeaway.

For power rankings, build one section per rank or rank tier. For team deep dives, build sections around record, recent games, roster strengths or weaknesses, transactions, and outlook.

## Persistent Context

If persistent context tools are available, save narrative state before drafting:

- Prefer `upsert_storyline_memory_card` for durable arcs, with evidence events and trigger specs when available. `save_persistent_storyline` remains a thinner compatibility wrapper.
- Use `save_memory_event` for source-backed evidence and `save_storyline_trigger` for dormant callbacks.
- Use `save_team_context` for researched teams whose trajectory changed.
- Use `save_league_note` for league-wide context such as season themes, trade activity, or rivalries.
- Record verified callbacks in `research/brief.md` if they were not already saved during research.
- Use `plan_memory_verification` / `record_memory_verification` when researching whether a retrieved lead is draftable.
- Use `mark_memory_used` when a retrieved candidate is drafted, used as research context, or discarded.

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

When persistent tool fields do not exist for arc metadata, use structured text in the persistent storyline summary:

```text
Arc type: trade_regret
Origin week: 3
Involved: Team A, Team B, Player X, Player Y
Receipt: Team A traded Player X for Player Y before Week 3.
Why it may matter later: Player X could swing a playoff matchup against Team A.
Next callback trigger: Team A faces Team B, Player X faces Team A, or either side loses a playoff game because of the trade assets.
Verification needed before use: confirm original trade receipt and current payoff with saved brief facts.
```

When the brief has facts, storylines, outline, style, and bias ready, switch to `drafting`.
