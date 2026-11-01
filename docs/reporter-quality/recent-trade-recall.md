# Recent trade recall: offline candidate

Generic league-wide requests have no explicit entity or text anchors, so their
automatic likely-relevant group currently skips discovery. A completed season
saved an acquisition but never exposed its event in the final article's starting
context; the article used the player's performance without the acquisition
callback. Saving and later exposure are different stages.

This candidate gives unfocused requests up to three active trade-event leads from
the current season, ordered by source week, then salience and stable item identity.
Typed-event filtering and revision/season/week eligibility apply before ranking
and limiting. Updating an older event's narrative does not make its source week
newer. One additional candidate signals truncation. This is a structured browse
and does not require an embedding request.

Explicit focus keeps its existing discovery behavior, including no broad fallback
for unresolved team names. Due callbacks, standing context and storyline review
selection are unchanged. Existing event presentation and exact-version bindings
are reused; no article mention is required and no target player is named. The
internal query mode is not exposed as a new reporter tool argument.

The three-card bound matches the existing storyline review pool's context budget;
there is no fixed age window or minimum storyline duration. Recency is only a
discovery heuristic: it may omit an older important acquisition, surface an
irrelevant recent deal, or repeat context already available through a callback.
It cannot retrieve an event that was never saved. More exposure is not evidence
of correct use or better prose.

Targeted PostgreSQL and unit tests cover typed filtering before the bound, recent
low-salience events versus older rewrites, current-season/competition scope,
original revision pins, future-introduction exclusion, explicit unresolved focus,
read-only recall, failure reporting and existing hybrid discovery. All 65 pass.
The first test iterations corrected synthetic fixture metadata, configuration
construction and expectations for existing truncation telemetry; production
ranking and filtering did not change in response to those fixture failures.

No paid comparison or publication has occurred for this candidate. A proposed
gate uses the original final-week request and the same completed prior-week
checkpoint in both arms. Evaluate source research, exact event exposure, explicit
inspection, factual acquisition/price use and article relevance separately.
Both arms discovering the callback, no comparable coverage, or delivery without
use are inconclusive. Wrong assets, unsupported causal credit or forced irrelevant
callbacks count against the treatment. Retain the first samples without rerolls.
