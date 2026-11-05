# E18: scoped record review context

A correct sentence such as “Cedar (8-0) and Birch (6-2) lead the table” produced
two attribution warnings: the verifier compared every record-like number in the
sentence against every named team's selected source record. Historical comparison
facts also triggered warnings against current records without resolving period.
A retained season trace showed edits following these warnings. The inspected
next edit clarified a real sentence ambiguity, so it is not counted as wasted
work caused by the warnings. Efficiency benefit remains unmeasured.

This candidate replaces that heuristic with bounded source-record context grouped
by subject identity. Each advisory context retains the selected source reference,
fact ID, season, week interval, temporal kind, wins, losses, any ties and record
unit, units and source limitations. It includes the relevant draft paragraph and
asks the reporter to compare team and period explicitly. It does not declare a
match or mismatch based on proximity.

Only validated source-bound facts supply these contexts. Authored claim text does
not supply their values. Repeated references are deduplicated; distinct subject
IDs stay separate even when display names agree. Unknown periods remain unknown.
Paragraphs without a record-like expression add no record context. The output is capped at 12 subject contexts, four observations per subject and
6,000 excerpt characters in total, with truncation reported. Existing overall
verification limits still apply.

The change is confined to record-review presentation. Other diagnostics,
traceability errors, revision-scoped receipts and non-blocking submission behavior
remain in place. No memory write, retrieval, storyline, source snapshot or model
setting changes are included. The parent is merged main
`ddccadd6c51947da2c9c2c539611e69dd2f11b25`; E17's creation paragraph is not inherited.

## Evidence and limitations

On the synthetic correct two-team case, main produced two attribution warnings;
the candidate produced zero such warnings and two scoped contexts. Seventy-six
targeted tests passed across record contexts, draft verification, grounding and
artifact tools. They cover historical/current periods, deliberately incorrect
prose, poisoned claim text, invalid bindings, repeated references, ties, units,
limitations, unknown periods, distinct identities and bounded output.

A deliberately wrong 7-1 claim remains visible beside its source-backed 8-0
record. This preserves evidence for review; it does **not** establish that the
writer will correct it. The candidate removes an unreliable automatic mismatch
heuristic and relies on explicit source/context comparison. Its effect on true
error detection, unnecessary edits, latency and article quality needs a separately
registered live comparison. No paid E18 call or production deployment has occurred.

Decision: reviewable offline candidate, **not promoted as a quality improvement**.
E16 retained the original verifier throughout its sixteen completed weeks.

## Preregistered synthetic reviewer gate

Before any paid E18 call, the next gate was frozen as one fresh control completion
and one treatment completion over the same five independent synthetic cases:
a correct two-team sentence, an incorrect current record, a correct historical
comparison, an incorrect ties record and a period claim unsupported by its source.
Only record-attribution diagnostics versus source-record contexts differ. Article
text, source observations, other receipt fields, reviewer prompt and output tool
are identical; the answer key is not supplied to the model. Nine offline packet
and scorer checks passed.

The treatment must preserve both correct passages, correct both wrong records,
and decline the unsupported period attribution. A favorable comparison additionally
requires an unnecessary control edit on a correct case. Both arms passing is a tie,
not superiority; incomplete or ambiguous responses are inconclusive. There are no
rerolls or extra turns. Returned review tools do not execute article or memory
mutations. Even a favorable result would establish only synthetic reviewer
behavior, not an improvement in full reporting conversations. Execution is
serialized after the unchanged baseline and the creation-coherence gate, subject
to the remaining hard budget. This gate was not dispatched: the preceding baseline reached its shared
conservative spending boundary during Week 17. Both arms remain unrun, with zero
paid gate calls. This is neither a failed comparison nor an inconclusive paid
result; the frozen packets and discriminator are retained. No quality promotion
is made from the offline tests.


## November 5 paired gate

The previously frozen synthetic gate has now run once per arm. Both control and
treatment passed all five cases: preserve two correct records, correct two real
errors, and decline an unsupported time-period claim. Cost was $0.005562408;
there were no returned tool executions, retries, embeddings or uncertain requests.
The predeclared improvement discriminator was not met because control also made
all correct decisions. This is an inconclusive tie. The PR's rationale remains
the reproduced cross-comparison defect and scoped diagnostic presentation, not
evidence of reduced live revision churn or better articles. Backend code remains
unchanged from the head that passed 76 targeted tests.

## Prepared-definition compatibility

The artifact-tool implementation version is incremented for the changed
verification presentation. Previously prepared definitions must not silently
execute the new diagnostic implementation. This is a preparation/execution
compatibility marker, not an additional editorial treatment. The isolated E24
comparison retains its original frozen runtime and definition throughout both
arms; its verifier implementation is identical to this candidate.

An additional synthetic regression covers a punctuated team name, preserving
the whole paragraph and separating the subject's source record from its
opponent's. All eleven record-context tests pass on that test revision.

## E24 complete reporting comparison

One matched Week 4 generation per arm completed both article submission and
memory closeout. Control made zero unnecessary record edits, so the primary
avoided-edit discriminator was unavailable. Treatment's six edits all preceded
its first verification; it made no edit after the changed diagnostic feedback.
Control used 25 calls and treatment 28, costing $0.268010484 together. No retry or
new uncertain charge occurred. The result is inconclusive, not evidence of lower
revision cost or improved prose. Both retained original memory versions and trade
identities. Independent temporal, arithmetic and lineup-rule mistakes remained
in the outputs; source-bound facts alone did not prevent misleading derived
claims. These are documented limitations, with no post-hoc article correction.
