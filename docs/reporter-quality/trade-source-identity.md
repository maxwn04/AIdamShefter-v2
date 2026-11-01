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

A prospective generation comparison remains pending. Its primary discriminator
is exact source identity reuse with preserved versions and valid evidence links.
Save, retrieve and use coverage, research loops and article quality are secondary
observations, not assumed consequences of reducing duplicate identities.
