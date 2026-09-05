# Goal: Find The Article's Meaning

Use this guide when the evidence is real but the central thesis, hierarchy of angles, callbacks, stakes, or article shape is still unclear. It may help before drafting, while testing prose, or when verification exposes weak framing.

## Success Looks Like

- The article has a clear supported idea appropriate to the request, not merely a list of results.
- Featured angles explain a meaningful change, tension, consequence, payoff, reversal, irony, or future stake.
- The strongest material receives the most attention; routine facts remain supporting color or are omitted.
- Every saved storyline is supported by facts, and every callback names reverified old and current evidence.
- Any outline reflects the current evidence and remains useful rather than ceremonial.

## Tool Choices

- Use `read_brief` when the current facts, callbacks, storylines, or outline are not already available in context.
- Use a targeted datalayer call when a promising angle has one material evidence gap. Return to broader research only when the premise itself needs substantial investigation.
- Start from any automatically recalled callbacks, standing context, and likely relevant memories. Use `search_memory` only when current evidence reveals a distinct continuity question that the prelude does not answer. Search by editorial intent with team names, focused text or tags, and inclusive week bounds when useful. Treat all semantic memory as leads, verify material claims with datalayer tools, and discard memories beyond configured coverage.
- Use `save_storyline` for developed narrative angles supported by fact IDs whose `save_fact` calls returned `ok=true`. Callbacks and outlines must likewise use accepted IDs. If a dependency is missing, follow the error's repair instruction and wait for successful saves before retrying; do not silently discard unsupported dependencies.
- Use `save_memory_callback` only after the older event and current payoff both exist as reverified facts.
- Use `set_outline` when explicit structure will improve emphasis, coverage, or drafting. An outline is optional and revisable.
- Use `upsert_storyline_memory_card` when an ongoing arc's durable headline, summary, status, or callback condition should be created or updated.
- Use `save_storyline_trigger` when that arc has a concrete future condition worth checking, such as a rematch or trade reevaluation.

## Narrative Judgment

- Name what changed or why the event matters, not only what happened.
- Distinguish retrieval relevance from reader value. A memory match or statistical outlier is not automatically a good storyline.
- Prefer angles with specific evidence, consequence, surprise, stakes, reversal, payoff, league-reader relevance, or comedy that the facts genuinely support.
- Treat unsupported framing as a hypothesis. Verify it, soften it, or drop it.
- Storyline summaries may interpret facts but may not introduce new factual claims.
- Test whether each featured angle earns its space and whether the article would lose meaning without it.
- Let the requested form determine structure. A recap, ranking, deep dive, retrospective, and playoff piece need not share the same outline.
- Use priority as a relative editorial ranking within this article, not a universal taxonomy.

## Continuity Judgment

Brief storylines and their supporting facts remain working state for the current article; neither becomes durable automatically. During mandatory closeout, use `upsert_storyline_memory_card` to preserve an arc when a future generation could usefully recognize its next payoff or reversal. Relevant examples include trade evaluations, revenge or rematch conditions, playoff reversals, recurring lineup mistakes, waiver payoffs, and rivalry escalation. Add a trigger only when a specific future condition would make the arc useful again.

## Stop Or Switch

This goal is sufficiently met when the lead and supporting angles are evidence-backed, proportionate to their importance, and coherent enough to guide prose. Shift attention when the greater risk is missing evidence, weak composition, or publication confidence. If drafting exposes a better thesis, revise the narrative plan instead of protecting the original outline.
