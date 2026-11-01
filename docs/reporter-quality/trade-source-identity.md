# Trade source identity experiment

Repeatedly saving a source-verified trade under different model-generated labels
created separate canonical events for the same transaction. Exact source audit
found five duplicate groups in each of two sequential season samples. The groups
contained 12 and 14 event identities respectively, representing five transactions
per sample. This was an identity-selection problem after successful source
resolution, not a fuzzy similarity problem.

The candidate selects trade identity by provider, competition, competition season,
source league and source transaction. A model label remains a local alias for
subsequent tool calls. Later assessments retain the same item and create immutable
versions. Distinct source transactions remain separate even when their assets
match. The lookup respects the input revision, origin week and version introduction
week and does not change
editorial search ranking, model prompts, storyline behavior or the verifier.

An offline replay of the 26 recorded, already-resolved saves produced five items
per sample while retaining all 26 versions. This tests the write boundary, not
model behavior or article quality. It does not establish better retrieval,
callbacks, longer organic storylines or better prose.

Targeted tests cover local aliases, semantic retries, conflicting same-run saves,
legacy keys, distinct transactions and leagues, inactive events, existing
duplicates, rollback, revision visibility and concurrent commits. The 64-test
selection passed both on the experiment checkout and on a clean branch from the
public main baseline. Independent review added four regression cases covering
future assessments at later pins, no-change alias hydration and historical-handle
shadowing. They failed on the original candidate; all 68 targeted cases passed
after repair on the clean public branch. No provider calls were needed.

Existing duplicate identities fail closed and require explicit reconciliation;
the candidate does not silently merge or delete history. A pin-visible source
match outside the reporting window also blocks the save, rather than being
filtered away and treated as permission to create a duplicate. No-change aliases
resolve selected exact content for callbacks and storyline evidence. Read-only
historical handles cannot be used as save aliases. The guarantee applies to
the reporter save path and its existing canonical revision lock, not arbitrary
low-level database writes. Concurrent stale writers cannot both commit; the
existing writer may report either a stale revision or a missing revision after
its locked query is rechecked. That error-class inconsistency is outside this
change.

A preregistered two-run selected-week comparison is complete. Both arms started
from the same duplicate-free checkpoint, with identical source snapshots,
editorial request, first-request messages, tool definitions and inference settings.
Both retained the same reviewed storyline-identity instruction; only the six
runtime files implementing this trade-identity change differed. No rejected
partial-question instruction was included. Each arm ran once, without rerolls.

The control re-saved one existing transaction under a new label and created a
second canonical item. The treatment re-saved three existing transactions under
new labels, reused all three original items and left no duplicate source groups.
Their structured asset movements were unchanged, the new versions linked to the
updated storylines, and all 62 prior memory versions and their content remained
intact in both arms. This passes the narrow live identity-reuse discriminator;
it does not establish a general article-quality improvement.

Both articles and closeouts completed: 34 model calls in control and 25 in
treatment. The treatment included three acquisition callbacks versus one in
control, but neither used explicit memory search or inspection. Those differences
occurred before the changed save boundary was exercised and are stochastic sample
observations, not causal evidence for this fix. Both runs had research or repair
loops. One treatment trade headline reversed the draft-pick side even though its
summary and structured assets were correct; the identity fix does not validate
model-authored prose. A callback-handle error also led to another scheduled review
instead of reuse of the existing callback. These remain separate quality issues.

Settings were direct Flash with high reasoning, 32,768 completion-token headroom,
a 16 MB serialized-input guard and unchanged research/closeout turn limits. The
byte guard is distinct from the provider context-token ceiling. These settings
match the preceding Flash baseline, not the earlier smaller-limit comparison.
After gate review, the chronological follow-up started from pristine empty memory
with the same original requests, cutoffs and indexing. Two first-week attempts
failed on a connection error and an upstream HTTP 503 before submission or
canonical commit. Their traces, exports and uncertain reservations remain intact.
A final authorized recovery after a cooldown completed Weeks 1–13. Week 14
submitted an unchanged article at turn 38; its first closeout response returned,
but the next request was blocked before dispatch because the remaining
conservative authorization could not cover its reservation. The accepted article
is preserved separately; Week 14 made no canonical memory commit. Weeks 15–17
were not run. No new upstream failure occurred during the final recovery.

The completed 13-week prefix contains 15 source transactions, 15 canonical trade
items and 22 immutable versions: seven later assessments reused their original
items under new local aliases. There are zero duplicate source groups, item/source
collisions, typed-asset changes or broken storyline/callback links. All original
visibility pins across 30 exports and their prior content remain intact. Over the
same weeks, the baseline contains 13 transactions represented by 19 items, with
four duplicate groups and six excess identities. Twelve transactions occur in
both samples; different source selection and evolved memory prevent a claim that
all narrative differences were caused by the identity fix.

There is no clear efficiency improvement. Completed-prefix model calls were
402 in baseline and 397 in treatment, while treatment used more prompt and
completion tokens. Explicit memory search/inspection counts were 4/2 versus 5/0.
The treatment's final incomplete week drafted at turn 24, revised through turn
36, verified at 37, submitted at 38 and began closeout at 39; revision work remains substantial.
Failed infrastructure attempts and the incomplete week are excluded from these
matched completed-prefix counts, but retained in the private cost record.

A tracked acquisition illustrates the remaining selection/retrieval distinction.
Week 12 discovered and used it in the article but retained it only in the local
research brief, not canonical memory. Week 13 researched it again, used it and
saved the complete canonical trade. Week 14 received its history in a storyline
summary, without an exact binding to the original event card. This is useful
continuity, not proof of direct event retrieval or postseason payoff.

Lifecycle and prose remain mixed. One roster-risk question spans eleven weeks
with ten versions, but some arcs broaden into new roster or playoff questions.
A mathematically supported playoff-place closure should not be penalized merely
for ending an arc. Conversely, an answered standings question does not settle
all acquisition-value consequences. A trade memory summary contained mutually
inconsistent records while the article used the correct record; structured
identity correctness does not validate model-authored narrative claims. The
partial run cannot establish final-season lifecycle or championship callbacks.

Private recovery diagnostics and accounting passed 18 targeted tests, including
redaction, repeated carry, immutable ancestry and cap exhaustion. That operator
code is not included in this PR. All uncertain requests remain fully charged
under the unchanged authorization, and no further paid recovery was launched.
Private articles, source identifiers, raw traces and financial records remain
outside this repository. This is evidence for the narrow identity fix, not a
general article-quality claim.
