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
- Historical narrative leads: `search_memory`, followed by datalayer verification of any lead worth using.

Run independent reads together when their results do not depend on one another. Avoid overlapping broad calls that reproduce the same evidence, and do not expand the week range merely to find more material.

History is opt-in. Use it only when the request, recalled memory, or current facts create a meaningful cross-season lead; an ordinary weekly recap remains primary-season first. For a historical lead, discover the available seasons, prefer the curated history tools for orientation, and drill down with explicit `season=YYYY` arguments. Resolve historical teams through durable franchise identity rather than matching old names independently. Save evidence for every season involved in a comparison, callback, record, or superlative, and include every material tool argument in the source reference.

## Evidence Judgment

- Treat `league_snapshot` as an inventory. A featured claim usually benefits from a targeted view that tests or explains the interpretation.
- Treat retrieved memory as a hypothesis. Save a callback only after the old event and current payoff both exist as reverified facts.
- Treat `found: false`, missing matchups, all-zero scoring, implausible totals, or disagreement between views as unresolved evidence. Cross-check through a different representation before relying on it. If the anomaly cannot be resolved, narrow or qualify the claim rather than presenting certainty.
- Save facts that are precise, traceable, and useful to the article. Use stable lowercase IDs, exact numbers, accurate categories, and source references matching calls actually made.
- Save every material numeric or factual detail that the draft will need; raw tool output remaining in conversation is not a substitute for brief evidence.
- Bias may guide what deserves investigation, but it cannot change what the evidence says.

## Memory Judgment

Begin with any automatically recalled due callbacks, standing context, and likely relevant memories already supplied in the conversation. They can satisfy the initial continuity check, but they remain unverified narrative leads. After the current-week inventory, use `search_memory` only when a concrete team, player, transaction, matchup, or stakes question remains unanswered by that prelude. Build any supplemental search from current evidence:

- Prefer `team_keys` for current team names or roster IDs, and combine them with tags or a focused text concept when that sharpens the editorial question. Canonical memory identifiers are intentionally unavailable.
- Use `text` for one continuity question, concept, name, or phrase. Hybrid discovery can connect paraphrases when semantic retrieval is ready. Never pack unrelated teams, players, and themes into one query. If distinct hooks are independently valuable, test them with separate focused calls.
- Use `kinds`, `statuses`, and inclusive `week_from` / `week_to` only when they genuinely narrow the question. Omit temporal bounds for continuity spanning the season.
- Prefer 5-8 focused semantic results. Include evidence or related summaries when they help evaluate continuity, but remember that memory is a lead rather than proof. Do not perform an unfiltered browse merely because memory exists.
- Discard any match dated after the article's configured coverage.
- Check `retrieval_status`: disabled, partial, stale or unavailable semantic retrieval means the lexical/structured fallback may miss paraphrases. A no-match result cannot tell you whether the reporter ever saved the event. Narrow to a known name or browse with hard franchise/kind filters when the question warrants it.
- Historical matches may contain earlier hypotheses or superseded status. Use `inspect_memory` for their selected detail/history/evidence; historical handles stay read-only. Search without text for a current card before updating an arc. Similarity is a relevance signal, not source support or a callback answer.

This is optional targeted retrieval, not a fixed research phase. Do not repeat the automatic prelude as a tool call. Stop after an empty or low-value result unless a more specific question is justified.

Saved brief facts remain working evidence for this article and are not copied into durable memory. After successful submission, use mandatory closeout to explicitly select future-use continuity: `upsert_storyline_memory_card` for an arc that should remain recognizable, and `save_memory_event`, `save_storyline_trigger`, `save_team_context`, or `save_league_note` for durable event, callback, team, or league state. Memory selection remains separate from proving today's article.

## Stop Or Switch

This goal is sufficiently met when the important claims and sections are supported, suspicious evidence has been resolved or qualified, the central framing is stable, and another call would mostly add substitutable color. Shift attention to narrative selection, composition, or publication confidence when one of those is now the greater risk.
