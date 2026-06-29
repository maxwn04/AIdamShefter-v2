# Long-Running Storyline Memory: Prompting Pass

## Purpose

Improve `reporter-v2` memory behavior on top of the current `reporter_memory`
storage layer.

This pass uses the current persistent context tools and storage layer, but changes
the agent's workflow so it treats persistent memory as research leads, not truth.

## Core Decisions

- Use agentic memory search behavior, not a rigid RAG pipeline.
- Retrieved memories are leads. They are not article-ready facts.
- The agent decides which leads are interesting enough to pursue.
- Every callback used in prose needs:
  - an old-event fact or verified memory receipt;
  - a current-event fact from the current run.
- The brief remains the source of truth for drafting.

## Problem

Current persistent memory remembers summaries, team notes, and league notes. That
helps with continuity, but it fails when an event goes dormant and only matters
again later.

Examples:

- A Week 3 trade becomes a playoff regret arc.
- A traded-away player later beats their former manager.
- A close regular-season matchup becomes relevant in a playoff rematch.
- A waiver pickup turns into a playoff hammer.
- A lineup mistake matters again when the same manager repeats it.

The prompt-level goal is to make the agent ask, "Does this current-week event
change the meaning of anything we already know?"

## Current Gaps

- `load_persistent_storylines()` is broad context loading, not search.
- Existing prompts do not require callback scanning.
- Persistent summaries do not consistently include future callback hooks.
- The agent can mention continuity without proving the old event and current
  payoff.
- Vague callbacks can survive drafting because verification only checks general
  factual grounding.

## Target Workflow

Add a memory scout loop inside research:

1. Build a current-week fact map:
   - scores and margins;
   - standings and playoff stakes;
   - current matchups;
   - top players;
   - transactions;
   - user focus and requested framing.
2. Generate current-week narrative hypotheses:
   - What changed meaning?
   - What has reversal, revenge, regret, payoff, collapse, irony, or stakes?
3. Search or load memory for possible callbacks.
4. Inspect only promising candidates.
5. Verify old-event and current-event facts with datalayer tools.
6. Save verified callbacks into the brief after both facts exist.
7. Promote only the best verified callbacks into storylines and outline.

Interestingness is separate from retrieval relevance. The agent should prefer
callbacks with surprise, stakes, reversal, payoff, specificity, league-reader
value, comedy value, evidence strength, and article fit.

## Prompt Changes

### `reporter_v2/prompts/system.md`

Add rules:

- Persistent context is narrative memory, not factual truth.
- Retrieved memories are research leads, not article-ready claims.
- Dormant storylines are valuable when the current week creates a meaningful
  callback.
- Callbacks must be re-verified before drafting.

### `reporter_v2/procedures/research.md`

Add a memory scout loop after the broad current-week snapshot:

1. extract current entities and events;
2. search or load memory for possible callbacks;
3. inspect promising candidates;
4. verify old and current facts before using a callback;
5. save verified callbacks into the brief.

Require this loop for:

- trades;
- playoffs;
- rematches;
- rivalries;
- power rankings;
- retrospectives;
- full-season arcs;
- teams with persistent context.

For weekly recaps, do a lightweight scan for:

- repeated opponents or prior close games;
- playoff matchups with regular-season history;
- top performers tied to old trades, waivers, drops, or former teams;
- current transactions that should be re-evaluated later.

### `reporter_v2/procedures/storyline.md`

Add durable arc examples:

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

Persist an arc only if it has either:

- a plausible future callback condition; or
- clear season-long significance.

Persistent summaries should use structured text even before schema support:

```text
Arc type: trade_regret
Origin week: 3
Involved: Team A, Team B, Player X, Player Y
Receipt: Team A traded Player X for Player Y before Week 3.
Why it may matter later: Player X could swing a playoff matchup against Team A.
Next callback trigger: Team A faces Team B, Player X faces Team A, or either
side loses a playoff game because of the trade assets.
Verification needed before use: confirm original trade receipt and current payoff
with saved brief facts.
```

### `reporter_v2/procedures/drafting.md`

Require callback paragraphs to clearly state:

- what happened then;
- what happened now;
- why the meaning changed.

Ban vague continuity phrases unless the paragraph names the old event and the
new payoff.

### `reporter_v2/procedures/verification.md`

Add callback-specific checks:

- Every callback must map to an old-event fact or verified memory receipt.
- Every callback must map to a current-event fact.
- Unsourced narrative memory can justify research, not prose.
- Reject or soften callbacks where the old event is real but the current payoff
  is weak.

## Verified Brief Callback Layer

Add a thin `memory_callbacks` layer to the brief. This keeps the brief as the
single drafting artifact while still distinguishing cross-week callbacks from
ordinary facts and storylines.

The callback layer should only accept verified callbacks. Persistent memory can
justify research, but it should not be saved into the brief until both the old
event and current payoff have saved fact IDs.

Minimal tool:

- `save_memory_callback(id, callback_type, claim_text, old_event_fact_id,
  current_event_fact_id, why_now, interestingness_reason, memory_refs, tags)`

The tool should reject missing `old_event_fact_id` or `current_event_fact_id`
values. This prevents unverified narrative memory from becoming draftable.

## Rollout

1. Update system, research, storyline, drafting, and verification prompts.
2. Add verified brief callback tooling.
3. Add v2 post-run fact persistence if feasible in the same pass; otherwise it
   can ship with the architecture remodel.
