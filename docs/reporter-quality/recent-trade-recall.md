# Recent trade recall: technical exposure, inconclusive quality gate

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

The preregistered two-arm final-week gate is complete. Both arms used the same
original prior-week checkpoint, frozen request, Flash high reasoning, 32,768-token
output ceiling, 16 MB serialized-input guard, and 60 research plus six closeout
turns. The operational parent included the reviewed source-identity and storyline
identity changes; this candidate was the only difference. Neither arm included the
rejected compound-question treatment or later origin-context changes.

| Observation | Control | Recent-trade treatment |
| --- | --- | --- |
| Exact trade cards in starting context | 0 | 3 |
| Complete acquisition and price callback | Yes | Yes |
| Completion calls | 34 | 30 |
| Calls before first draft | 22 | 14 |
| Revision edits | 6 | 10 |
| Closeout calls | 5 | 4 |
| Article words | 1,271 | 1,168 |

Both first samples were retained without retries. The pair cost approximately
$0.245, with no new uncertain calls. Existing recall groups matched after resolving
local handles to exact versions; other initial messages and tool definitions were
identical. Both arms preserved all 175 prior versions and had no duplicate source
identities or broken storyline links. The treatment exposed three eligible exact
trade versions, then researched source transactions; the control independently
researched earlier transactions and recovered the same central callback. Neither
used explicit memory search or inspection.

The technical exposure discriminator passed, but the article-quality discriminator
is **inconclusive** because both fresh arms recovered the acquisition and price.
The older season's miss is not a replacement control. Fewer research calls and
more revisions in one sample do not establish an efficiency improvement.

Adverse evidence remains: each article correctly explains the central trade but
later reverses an ownership relationship in its prose. The treatment also calls
recorded consolation winners incorrect without verifying the configured bracket
rule. Ordinary sports payoff language is not itself counted as a false
counterfactual; concrete ownership contradictions and unverified rule judgments
are separate grounding failures.

Decision: retain this optional read-only exposure change for draft review, with no
quality efficacy claim and no full-season promotion or reroll. This does not fix
unsaved acquisitions, historical research scope, factual verification, or prose
consistency. Those require separate hypotheses and comparisons.
