# E18: scoped record review context

A correct sentence such as “Cedar (8-0) and Birch (6-2) lead the table” produced
two attribution warnings: the verifier compared every record-like number in the
sentence against every named team's selected source record. Historical comparison
facts also triggered warnings against current records without resolving period.
A retained season trace showed edits following these warnings; that sequence is
an observation, not a measured causal efficiency result.

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
The active E16 baseline continues with the original verifier unchanged.
