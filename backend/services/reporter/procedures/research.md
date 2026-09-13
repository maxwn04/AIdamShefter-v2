# Goal: Establish A Trustworthy Evidence Base

Save exact executed bindings as `ref`, `field`, and `value`; the runtime derives subject, season, week bounds, perspective, references, and numeric summaries. A `found=false` or unavailable result cannot support a factual claim even when the tool call succeeded. Use returned roster drill-down handles from franchise appearances, preserving their explicit season; do not guess old names or UUID lookup forms. Continuity requests warrant league/franchise history discovery, while ordinary narrow recaps need history only when it helps their coverage.

Wait for `save_fact` to return `ok=true` before using its ID in a callback, storyline or outline. Batch independent facts, then inspect their results. Dependency errors identify accepted and missing IDs with a repair instruction; a rejected fact never becomes available by repeating a dependent mutation.

Use this guide when the article covers several teams or weeks, a featured interpretation needs more than a league summary, historical context may matter, or retrieved data looks incomplete or inconsistent. It may also help repair a specific gap exposed during outlining, drafting, or verification.

## Success Looks Like

- The article's central framing and planned major claims have precise, relevant evidence.
- Featured interpretations have enough targeted context to distinguish a meaningful development from a routine result.
- Historical leads used in the article have been reverified against the frozen snapshot.
- Recap and storyline-oriented work has tested current developments against relevant pinned memory once current evidence supplied concrete query hooks.
- Important scores, records, player totals, transactions, and comparisons are saved as facts with the exact values the article will use.
- No unresolved anomaly or high-value lead is likely to reverse the article's central interpretation.

## Tool Choices

Choose the smallest useful view for the current question:

- League-wide orientation: `league_snapshot` and `standings`.
- Cross-season orientation: `available_seasons`, then `league_history` or `franchise_history`.
- Every head-to-head game score and winner in one week: `week_games`. The overview includes all matchups; player detail remains available through `team_game` or deliberate `read_evidence(view="detail")` retrieval.
- One featured matchup: `team_game`.
- Team form, opponents, and season context: `team_dossier` and `team_schedule`.
- Roster composition or a lineup question: `roster_at_cutoff`, `roster_snapshot`, and `bench_analysis`.
- Weekly or season player performance: `week_player_leaderboard`, `season_leaders`, and `player_weekly_log`.
- Player identity, NFL team, status, or injury metadata: `player_summary`.
- Trades, waivers, and roster moves: `transactions` or `team_transactions`.
- Playoff stakes: `playoff_bracket` and `team_playoff_path`.
- A bespoke comparison unavailable from curated tools: guarded `run_sql`.
- Historical narrative discovery: `search_memory`; selected detail, history and evidence: `inspect_memory`. Datalayer calls verify material claims from those leads.

Run independent reads together when their results do not depend on one another. Avoid overlapping broad calls that reproduce the same evidence, and do not expand the week range merely to find more material.

Keep current coverage primary while investigating history that explains it. Same-season developments can warrant discovery without a special request for history: a contender losing, an acquired player becoming decisive, or a playoff result revisiting an earlier expectation. For cross-season leads, discover available seasons, prefer curated history tools for orientation, and drill down with explicit `season=YYYY` arguments. Resolve historical teams through durable franchise identity rather than matching old names independently. Save evidence for every season involved in a comparison, callback, record, or superlative, and include every material tool argument in the source reference.

## Evidence Judgment

- Treat `league_snapshot` as an inventory. A featured claim usually benefits from a targeted view that tests or explains the interpretation.
- Treat retrieved memory as a hypothesis. Save a callback only after the old event and current payoff both exist as reverified facts.
- Treat `found: false`, missing matchups, all-zero scoring, implausible totals, or disagreement between views as unresolved evidence. Cross-check through a different representation before relying on it. If the anomaly cannot be resolved, narrow or qualify the claim rather than presenting certainty.
- Save facts that are precise, traceable, and useful to the article. Use stable lowercase IDs, exact numbers, accurate categories, and source references matching calls actually made.
- Save every material numeric or factual detail that the draft will need; raw tool output remaining in conversation is not a substitute for brief evidence.
- Bias may guide what deserves investigation, but it cannot change what the evidence says.

## Memory Judgment

Treat automatically recalled cards as a useful selection of leads, not a complete account of what was previously reported. Ask whether a meaningful current development tests an older expectation, continues an acquisition story, changes a rivalry or answers an open question. Discover that history when it could change the angle or interpretation; inspect selected cards when their summaries do not establish the relevant prior state or evidence. This is editorial judgment within research, not an extra required workflow stage.

- Use `team_keys` for a genuinely team-specific question, preferring returned stable `franchise:<UUID>` selectors. Names and roster IDs resolve in the selected season. Team, season, kind, status and week filters exclude other results; do not narrow away a trade counterparty, resolved arc or earlier chapter that the question needs.
- Use `text` for one continuity question, concept, name, or phrase. Hybrid discovery can connect paraphrases when semantic retrieval is ready. Never pack unrelated teams, players, and themes into one query. If distinct hooks are independently valuable, test them with separate focused calls.
- Use `kinds`, `statuses`, and inclusive `week_from` / `week_to` only when they genuinely narrow the question. Omit temporal bounds for continuity spanning the season.
- Read candidate summaries for relevance, then use `inspect_memory(view="detail")` for the selected question/state, `view="history"` for how it developed, or `view="evidence"` for linked events. Request further pages only when they may resolve the question. No search or result-count quota establishes useful research.
- Discard any match dated after the article's configured coverage.
- Check `retrieval_status`: disabled, partial, stale or unavailable semantic retrieval means the lexical/structured fallback may miss paraphrases. A no-match result cannot tell you whether the reporter ever saved the event. Narrow to a known name or browse with hard franchise/kind filters when the question warrants it.
- Historical matches may contain earlier hypotheses, errors or superseded status. Keep what the reporter previously believed distinct from what source data establishes. For an update, obtain the current card with a scoped search without text and confirm its identity. Historical evidence remains useful even when the current summary no longer mentions it.

An empty search is not proof that an event never happened or was never saved. Check overly restrictive filters or degraded retrieval when the question is consequential; otherwise leave the connection out. When the correct evidence is already available, resolve its meaning rather than adding more searches. Similarity, an old narrative label and a successful fact-save receipt do not establish a causal payoff.

Saved brief facts remain working evidence for this article and are not copied into durable memory. After successful submission, use mandatory closeout to explicitly select future-use continuity: `upsert_storyline_memory_card` for an arc that should remain recognizable, and `save_memory_event`, `save_storyline_trigger`, `save_team_context`, or `save_league_note` for durable event, callback, team, or league state. Memory selection remains separate from proving today's article.

## Stop Or Switch

This goal is sufficiently met when the important claims and sections are supported, suspicious evidence has been resolved or qualified, the central framing is stable, and another call would mostly add substitutable color. Shift attention to narrative selection, composition, or publication confidence when one of those is now the greater risk.
