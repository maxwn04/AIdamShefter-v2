# Reporter experiment ledger

This ledger separates write-boundary correctness, memory selection/retrieval,
article quality and operating cost. Each live arm is a single stochastic sample.
A better article in one run is not proof that the changed component caused it.
Full private articles, source identifiers, prompts with league data, raw traces,
databases and account-funding records are retained outside this public repository.
The cost figures below are aggregate experiment charges, not a financial ledger
or provider invoice. DeepSeek charges use conservative peak rates; reasoning
already included in completion tokens is not charged a second time.

## Completed experiments and decisions

| Arm | Hypothesis / one changed factor | Coverage | Conservative cost | Decision |
| --- | --- | --- | ---: | --- |
| E00 / E01 | Original model baseline; then a stronger acquisition-research cue | Full season, then selected final week | $2.5184 combined, separate legacy authorization | Preserve baseline and negative prompt sample; source availability alone did not produce the historical callback. |
| E02 | Original final-week prompt on Flash, equal 8,192 output limit | Failed selected week | $0.0617 | Limit failure, not a finished quality comparison. |
| E02b | Increase completion headroom to 32,768; retain high reasoning | One completed selected week | $0.1112 | Use adequate headroom for later Flash work; comparison is not equal-output-limit. |
| E03 | Flash with original prompts and empty canonical memory | 17 chronological weeks | $2.2396 | Establish baseline; useful historical callbacks alongside duplicate events and question drift. |
| E04 | Preserve a storyline's original unresolved question during closeout | 17 chronological weeks | $2.5401, including $0.3543 unresolved request | Keep as promising, mixed draft: fewer clear identity replacements, more active-card pressure, no general lifecycle guarantee. |
| E05 | Explicitly retain unanswered parts of compound questions | Three selected-week arms | $0.3836 | Reject: fresh control already retained the disputed question; treatment introduced an extra criterion. No full season or shipping PR. |
| E06 gate | Select trade identity by exact source transaction rather than generated label | Two matched selected-week arms | $0.2347 | Keep narrow correctness fix: one duplicate in control, three reused identities in treatment, original pins and assets preserved. |
| E06 season | E04 plus the repaired E06 identity boundary | 17 completed weeks; original interrupted Week 14 retained | $3.0955, including $0.7086 unresolved requests | Keep narrow identity fix: zero duplicates; final championship acquisition callback missed. No general content-quality promotion. |
| E07 candidate | Consider durable acquisition-event selection separately from storyline updating | Two-arm gate running from the same post-Week 11 checkpoint | Pending | Pending. No quality rerolls; already-full coverage or incomparable opportunities count as inconclusive. |

E04's cost includes one fully retained uncertain request. E06's original season
attempts include two additional uncertain requests, each at the same full
reservation. A later account top-up does not erase historical costs or uncertainty.
The original budget-stop attempt and its accepted-but-unfinalized article remain
separate from its explicitly authorized recovery.

## Shared settings and comparability

The chronological Flash arms use direct `deepseek-flash`, high thinking enabled,
32,768 completion tokens, a 16,000,000-byte serialized-input guard, 60 research
turns plus six closeout turns, no provider fallback and no SDK retries. The byte
guard is distinct from provider context-token capacity. Semantic indexing uses
`text-embedding-3-large` with 3,072 dimensions between successful weeks. Original
editorial requests and weekly cutoffs run from 2025-09-12 12:00 UTC through
2026-01-02 12:00 UTC. Frozen retrospective source snapshots are reused; later
retrieved roster state must not be described as contemporaneous historical proof.

Each season starts with empty canonical memory. Selected-week arms identify their
inherited checkpoint explicitly and are not substituted for an empty-memory
season. Infrastructure timeouts, uncertainty, safe retries and headroom changes
are recorded separately from editorial treatments. No artificial minimum turn
count, storyline duration or named-player target is supplied to the reporter.

| Arm | Exact parent / change | Runtime file-manifest SHA256 | Closeout SHA256 |
| --- | --- | --- | --- |
| E03 | Original Flash season baseline | `abe783c4c345a9575d33405ce669beeab8596b98c52766331f3de303ee25c323` | `7add51085aa448fe9a4f9ef90807f2adc54f31c9ab8df633084fa0dcf529d9b1` |
| E04 | E03 plus one question-identity paragraph | `51eeb2ca0731c7823fb25d90c7766f744a05a2e230da3beb71fb8ee10c341c7d` | `09895bd48de62beff93bcdbf95819888b8427a8ac982296570326bec0e72186f` |
| E06 | E04 plus six exact-source-identity runtime files, repaired candidate `5ba681071343e64de824da53ef15162d0221a9bc` | `c75025926b820ed4154f19d6f2a242b9448b47be55e1d312eaf83a1bb830e3e3` | Same as E04 |
| E07 candidate | E06 plus one acquisition-event selection paragraph | Recorded in isolated arm manifests | `219437fc6150831054ec0908af506159ce7e98311b28ca198f45dedf991d527c` |

Runtime manifest hashes above are SHA256 of the sorted compact JSON mapping of
frozen file paths to file hashes. Private checkpoint receipts retain exact memory
heads, source membership hashes, cutoffs, requests and all failed generations.

## Evidence that shapes the next experiment

**Keep exact source identity.** Re-saving a verified transaction with a different
label should produce a later version of the same item, not a second event. The
narrow gate exercised this behavior and preserved historical visibility. This
does not merge legacy duplicates or certify model-authored summaries.

**Do not equate discovery with retention.** In one chronological sample a material
acquisition was researched and used in an article, left only in its temporary
brief, then researched again and saved the following week. Later weeks received
that history through storyline summaries without an exact event-card binding.
The final article used the acquired player's championship score but missed the
acquisition and its price; neither the event card nor that acquisition appeared
in final-week automatic context. The E04 final article did make that connection.
This is an unfavorable content observation, not proof the E06 code caused it.
The E07 gate tests event selection at closeout; it does not claim to fix retrieval.

**Question identity remains mixed.** A synthetic illustration of the failure is
replacing “Does this acquisition improve the team's weekly floor?” with “Can the
team hold its seed?” under one identity. A supported standings answer need not
settle acquisition value. Conversely, a mathematically clinched playoff place is
a legitimate resolution; arc longevity is not a score by itself. E05 is not being
reintroduced under another label.

**Factual memory needs independent review.** One saved summary contained two
incompatible records for the same team while the published article used the
correct record. Typed trade-asset validation cannot validate every surrounding
narrative claim. This is retained as a separate hypothesis, not bundled into E07.

**Revision cost needs context.** A long sequence of edits corrected an erroneous
article-wide tiebreak premise in multiple passages. Those repairs were useful,
even though preparing one coherent correction earlier might cost fewer calls.
No minimum/maximum editorial effort rule is inferred from call count alone.

**Keep rule interpretation grounded.** A shelved bonus-decision hypothesis came
from observed top-half results matching team-weeks. That empirical equivalence
alone does not establish the league's configured rule. No speculative rule fix
is included in the current candidates.

## Completed E06 season: evidence for and against

| Measure | E04 baseline | E06 |
| --- | ---: | ---: |
| Source trades / canonical identities | 13 / 22 | 15 / 15 |
| Immutable trade versions | 22 | 23 |
| Duplicate source groups / excess identities | 5 / 9 | 0 / 0 |
| Completed-week model calls | 535 | 512 |
| Prompt tokens | 61,471,545 | 61,053,883 |
| Completion tokens including reasoning | 1,005,046 | 1,004,689 |
| Research / drafting-through-submission / closeout turns | 294 / 164 / 77 | 275 / 157 / 80 |
| Explicit memory searches / inspections | 5 / 2 | 7 / 0 |

Twelve source trades overlap. All 37 original visibility/content checks passed;
there were no item/source collisions, changed typed assets or broken evidence
links. Eight later assessments reused existing items under new aliases. The
counts support deterministic identity correctness. Similar token use and mixed
callbacks do not establish general efficiency or quality superiority.

E06 ended with ten storyline identities: eight resolved and two active. Some
long-running questions broadened or narrowed under one identity. Those scope
judgments are retained alongside legitimate mathematically supported closures;
neither lifespan nor resolved-card count is a quality score. One final article
called consistently inverted consolation outcomes a filing error. The observed
mismatch is supported, but its cause requires checking the rules; no speculative
rules fix was introduced.

The original interrupted Week 14 accepted its article but did not commit memory.
Exact closeout-state resumption was unsupported, so an explicitly labeled recovery
started at the committed Week 13 boundary after renewed spending authorization.
The original article and attempt remain unchanged. All 17 weeks then completed,
with no new upstream failure. Completed-week metrics exclude failed attempts;
the aggregate cost includes them. The preserved season has 574 completion
dispatches, including two uncertain, and 22 embedding requests. Settled charges
are $2.3869; full uncertain reservations add $0.7086. No uncertain cost was erased.

## Reviewable drafts

- [#260](https://github.com/maxwn04/AIdamShefter-v2/pull/260): E04 question identity,
  based on main; mixed live result, not proven by its compatibility tests.
- [#261](https://github.com/maxwn04/AIdamShefter-v2/pull/261): E06 exact trade identity,
  based on main; deterministic correctness and live quality evidence separated.
- [#262](https://github.com/maxwn04/AIdamShefter-v2/pull/262): model message
  compatibility, based on `codex/canonical-preseason-backfill`; 47 targeted tests
  passed and one pre-existing closeout assertion reproduced on the untouched base
  was excluded. This is infrastructure compatibility, not a quality treatment.

No merge, PR approval or deployment is authorized by these experiment outcomes.
