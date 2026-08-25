# Research Procedure

Use this procedure for substantial discovery, evidence repair, and callback investigation. Gather verified fantasy football facts while continuously mining for narrative meaning. Research may begin a run or interrupt outlining, drafting, or verification; it does not have to be completed in one block.

## Artifact Editing

- Do not read the pre-created brief before initial research merely to inspect an empty workspace. When you have a useful batch of verified material, read `research/brief.md` if you do not already hold its current content and revision.
- Add material with `edit_artifact`, passing the current revision and replacing a unique insertion marker with the new Markdown plus the same marker.
- Batch related facts and callbacks into coherent edits instead of spending one turn per fact. Reuse the content and revision returned by successful artifact operations.
- If the edit reports a revision conflict or a non-unique match, read the brief again and retry from current content.
- Every fact entry should have a stable ID, precise claim, exact numbers, category, and source references naming the supporting tool calls.

## Operating Rules

- If you are repairing a gap found during drafting or verification, inspect the relevant brief and draft material, then research only what is missing.
- Start broad, then drill down. Prefer `league_snapshot` for the requested week before targeted team or player calls.
- Every recorded fact must be traceable to one or more datalayer tool calls.
- Save specific, reusable facts rather than commentary. The article voice comes later.
- Do not invent standings, scores, records, player points, transactions, injuries, or playoff implications.
- Bias can guide what you investigate, but it must not change which facts you record.
- When `search_memory` is available, perform one lightweight storyline scan after the broad current-week inventory unless the request is purely factual and narrow. Deepen the scan only when current teams, players, transactions, opponents, or stakes create a plausible callback.
- Hydrated memory is not a fact source. Verify both the older claim and the current-week payoff against frozen datalayer results before recording a callback.
- A narrow evidence gap does not require a procedure change. Make the targeted datalayer call, update the brief, and resume the work that exposed the gap.

## Adaptive Research Loop

Repeat these activities in the order the evidence demands:

1. Orient: establish the week range, focus, article type, target tone, and any teams to favor or roast.
2. Discover: use `league_snapshot(week=N)` or the relevant multi-week tools to map scores, standings movement, transactions, and obvious outliers.
3. Mine hypotheses: ask which results changed meaning, contradicted expectations, continued an arc, or created future stakes. Treat these as questions until verified.
4. Verify the strongest hypotheses with targeted team, player, transaction, standings, playoff, SQL, or memory calls.
5. Record useful evidence in the brief in batches, then reassess coverage and narrative strength.
6. If an outline or draft already exists, test new evidence against it. Preserve what still works and revise only what the evidence changed.

Run the memory scout loop when the request or data suggests long-running context:
   - Extract the current-week fact map: scores, margins, standings movement, playoff stakes, current matchups, top players, transactions, focus teams, and requested framing.
   - Generate narrative hypotheses from the current week. Ask what changed meaning, reversed, paid off, collapsed, became funny, or now has stakes.
   - Call `search_memory` with text, current team keys, tags, and typed filters. Request exact or stable expansions when linked evidence or storylines matter.
   - Inspect the fully hydrated matches, then plan the needed datalayer calls yourself.
   - Verify the old claim and current event with frozen datalayer tools.
   - Record old-event and current-event facts plus the verified callback in the brief.
   - Promote only the best verified callbacks into storylines and outline inputs.
   - Buffer durable changes with the relevant typed `propose_*` or `replace_*` tools when an arc should matter later. Use IDs returned by proposal tools for same-bundle relationships.

Useful targeted tools include:
   - `team_game(roster_key, week=N)` for player-level detail in a specific matchup.
   - `team_dossier(roster_key, week=N)` for recent form, record, and broader context.
   - `week_player_leaderboard(week=N, limit=10)` for top performers.
   - `transactions(week_from=N, week_to=N)` or `team_transactions(...)` for trade, waiver, or roster-move angles.
   - `player_weekly_log(...)` or `player_summary(...)` for trend checks on a featured player.
   - `playoff_bracket(...)` and `team_playoff_path(...)` when the article has playoff stakes.

Treat a league snapshot as an inventory, not sufficient research for a featured storyline. Each major section should have targeted context that tests its interpretation or adds relevant team, player, transaction, historical, standings, or playoff detail.

Aim for enough evidence to support the article, not every possible data point. When research is sufficient, continue with whichever activity is most useful: synthesize storylines, draft a supported section, verify an existing draft, or investigate one remaining high-value uncertainty. Load another procedure only if its detailed guidance is needed.

## Memory Scout Requirements

Run the full scout loop for:

- Trades, trade retrospectives, waivers, drops, and former-team angles.
- Playoffs, playoff paths, rematches, rivalries, and revenge games.
- Power rankings, retrospectives, full-season arcs, and season awards.
- Any focused team that has persistent context.

For standard weekly recaps, do a lightweight scan for:

- Repeated opponents, rematches, or prior close games.
- Playoff matchups with regular-season history.
- Top performers tied to old trades, waiver adds, drops, or former teams.
- Current transactions that should be re-evaluated later.

Evaluate candidate callbacks for interestingness separately from retrieval relevance. Prefer callbacks with surprise, stakes, reversal, payoff, specificity, league-reader value, comedy value, evidence strength, and fit with the requested article.

## Fact Quality

Good facts are precise, sourced, and useful in more than one sentence. Include the exact numbers the writer will need. A useful Markdown entry looks like:

```markdown
### fact_week8_taco_win

- Claim: Team Taco defeated The Waiver Wire 142.3-98.7 in Week 8.
- Sources: `league_snapshot(week=8)`, `team_game(Team Taco, week=8)`
- Numbers: week=8; team_score=142.3; opponent_score=98.7; margin=43.6
- Category: score
```

Use stable IDs that describe the fact. Prefer categories such as `score`, `standing`, `transaction`, `player`, `streak`, `playoff`, and `general`.

## What To Look For

- Upsets: lower-ranked or struggling teams beating favorites.
- Blowouts: dominant wins, especially margins around 30 points or more.
- Nail-biters: games decided by fewer than 5 points.
- Streaks: winning or losing runs, especially 3 or more games.
- Breakouts: player or team performances that stand out from recent history.
- Collapses: favorites or strong teams missing expectations.
- Transactions: trades, waivers, and roster moves that affected the week.
- Continuing arcs: previous storylines that changed, intensified, or resolved.
- Playoff pressure: seed movement, elimination risk, byes, and bracket paths.

## Sufficiency Criteria

Research is sufficient when you have enough verified facts to support the requested article and no unresolved high-value lead is likely to change its central framing:

- Short focused article: 5-8 strong facts.
- Standard weekly recap: 10-20 strong facts.
- Deep dive or power rankings: enough facts to support each featured team or section.

Fact counts are diagnostics, not stopping targets. Continue when another call could materially change the lead, correct an important claim, or unlock a strong callback. Stop when additional calls would mostly add interchangeable detail.
