# Goal: Establish A Trustworthy Evidence Base

Use this guide when the article covers several teams or weeks, a featured interpretation needs more than a league summary, historical context may matter, or retrieved data looks incomplete or inconsistent. It may also help repair a specific gap exposed during outlining, drafting, or verification.

## Success Looks Like

- The article's central framing and planned major claims have precise, relevant evidence.
- Featured interpretations have enough targeted context to distinguish a meaningful development from a routine result.
- Historical leads used in the article have been reverified against the frozen snapshot.
- Important scores, records, player totals, transactions, and comparisons are saved as facts with the exact values the article will use.
- No unresolved anomaly or high-value lead is likely to reverse the article's central interpretation.

## Tool Choices

Choose the smallest useful view for the current question:

- League-wide orientation: `league_snapshot` and `standings`.
- Complete player-level coverage for every game in one week: `week_games`. Its result is large; use it only when that breadth materially helps.
- One featured matchup: `team_game`.
- Team form, opponents, and season context: `team_dossier` and `team_schedule`.
- Roster composition or a lineup question: `roster_at_cutoff`, `roster_snapshot`, and `bench_analysis`.
- Weekly or season player performance: `week_player_leaderboard`, `season_leaders`, and `player_weekly_log`.
- Player identity, NFL team, status, or injury metadata: `player_summary`.
- Trades, waivers, and roster moves: `transactions` or `team_transactions`.
- Playoff stakes: `playoff_bracket` and `team_playoff_path`.
- A bespoke comparison unavailable from curated tools: guarded `run_sql`.
- Historical narrative leads: `search_memory`, followed by datalayer verification of any lead worth using.

Run independent reads together when their results do not depend on one another. Avoid overlapping broad calls that reproduce the same evidence, and do not expand the week range merely to find more material.

## Evidence Judgment

- Treat `league_snapshot` as an inventory. A featured claim usually benefits from a targeted view that tests or explains the interpretation.
- Treat retrieved memory as a hypothesis. Save a callback only after the old event and current payoff both exist as reverified facts.
- Treat `found: false`, missing matchups, all-zero scoring, implausible totals, or disagreement between views as unresolved evidence. Cross-check through a different representation before relying on it. If the anomaly cannot be resolved, narrow or qualify the claim rather than presenting certainty.
- Save facts that are precise, traceable, and useful to the article. Use stable lowercase IDs, exact numbers, accurate categories, and source references matching calls actually made.
- Save every material numeric or factual detail that the draft will need; raw tool output remaining in conversation is not a substitute for brief evidence.
- Bias may guide what deserves investigation, but it cannot change what the evidence says.

## Memory Judgment

Search memory when prior context could materially improve the article: trades and waivers, rematches and rivalries, playoff reversals, repeated lineup mistakes, focused-team histories, retrospectives, rankings, or season-long awards. For an ordinary recap, a lightweight scan is useful only when current teams, players, transactions, or stakes provide a plausible retrieval hook. Stop after an empty or low-value result unless the current evidence suggests a more specific query.

Buffer durable proposals only when an event or arc has plausible future callback value. Persistence work is separate from proving today's article.

## Stop Or Switch

This goal is sufficiently met when the important claims and sections are supported, suspicious evidence has been resolved or qualified, the central framing is stable, and another call would mostly add substitutable color. Shift attention to narrative selection, composition, or publication confidence when one of those is now the greater risk.
