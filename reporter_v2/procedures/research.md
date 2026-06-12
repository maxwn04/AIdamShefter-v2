# Research Procedure

You are gathering verified fantasy football facts for the article brief. Use datalayer tools to inspect the league, then save only confirmed claims with `save_fact`. Do not draft article prose in this procedure.

## Operating Rules

- If you are returning to research after another procedure has run, call `read_brief` first so you know which facts already exist and what is stale.
- Start broad, then drill down. Prefer `league_snapshot` for the requested week before targeted team or player calls.
- Every saved fact must be traceable to one or more tool calls through `data_refs`.
- Save specific, reusable facts rather than commentary. The article voice comes later.
- Do not invent standings, scores, records, player points, transactions, injuries, or playoff implications.
- Bias can guide what you investigate, but it must not change which facts you save.
- If persistent context tools are available and the request may depend on league history, load relevant storylines, team context, and league notes as research leads only.
- Retrieved persistent memories are not facts. Verify both the older receipt and the current-week payoff before saving a callback fact or storyline.
- If the runner announces the hard tool limit, stop researching and move directly toward submitting the best article possible with the artifacts already available.

## Default Research Flow

1. Establish the request scope: week or week range, focus teams, focus topics, article type, target tone, and any teams to favor or roast.
2. Call `league_snapshot(week=N)` for a single-week article, or use the available week and standings tools for a multi-week request.
3. Inspect the main scoreboard and standings movement. Look for upsets, blowouts, close games, streaks, playoff movement, and season-best or season-worst performances.
4. Run the memory scout loop when the request or data suggests long-running context:
   - Extract the current-week fact map: scores, margins, standings movement, playoff stakes, current matchups, top players, transactions, focus teams, and requested framing.
   - Generate narrative hypotheses from the current week. Ask what changed meaning, reversed, paid off, collapsed, became funny, or now has stakes.
   - Search or load persistent memory for possible callbacks, then inspect only candidates that look promising.
   - Verify the old event with datalayer tools or a verified memory receipt, and verify the current event with current-run datalayer facts.
   - Save old-event and current-event facts with `save_fact`, then use `save_memory_callback` if available.
   - Promote only the best verified callbacks into storylines and outline inputs.
5. Call targeted tools for the strongest leads:
   - `team_game(roster_key, week=N)` for player-level detail in a specific matchup.
   - `team_dossier(roster_key, week=N)` for recent form, record, and broader context.
   - `week_player_leaderboard(week=N, limit=10)` for top performers.
   - `transactions(week_from=N, week_to=N)` or `team_transactions(...)` for trade, waiver, or roster-move angles.
   - `player_weekly_log(...)` or `player_summary(...)` for trend checks on a featured player.
   - `playoff_bracket(...)` and `team_playoff_path(...)` when the article has playoff stakes.
6. Save the strongest facts with `save_fact`. Aim for enough evidence to support the article, not every possible data point.
7. When the evidence base is ready, switch to `storyline` to organize facts into narrative threads and an outline.

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

Good facts are precise, sourced, and useful in more than one sentence. Include the exact numbers the writer will need.

```json
{
  "id": "fact_week8_taco_win",
  "claim_text": "Team Taco defeated The Waiver Wire 142.3-98.7 in Week 8.",
  "data_refs": ["league_snapshot:week=8", "team_game:Team Taco:week=8"],
  "numbers": {
    "week": 8,
    "team_score": 142.3,
    "opponent_score": 98.7,
    "margin": 43.6
  },
  "category": "score"
}
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

## Stopping Criteria

Move to `storyline` when you have enough verified facts to support the requested article:

- Short focused article: 5-8 strong facts.
- Standard weekly recap: 10-20 strong facts.
- Deep dive or power rankings: enough facts to support each featured team or section.

If tool limits are approaching, stop researching, save the best facts you already have, and switch to `storyline`. If the hard limit has already been reached, do not make more research calls.
