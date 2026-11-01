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
| E07 | Consider durable acquisition-event selection separately from storyline updating | Two matched selected-week arms | $0.2667 | Inconclusive, not promoted: both arms retained the one eligible acquisition completely. No full season or shipping PR. |
| E08 gate | Show immutable original context beside existing automatic storyline leads | Two matched Week 7 arms | $0.2747 | Technical feasibility passed; quality mixed. Three exact origin bindings, continued scope shifts and a misdated historical memory claim. No efficacy promotion. |
| E08 season | E06 plus the E08 presentation file only | Fresh empty-memory 17-week measurement running | Pending terminal accounting | Preregistered all-arc lifecycle and grounding audit; no E05 or E07 paragraph. |

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

A concrete source discrepancy is now confirmed: an early frozen ownership view
already assigns a draft pick to the receiver of its only recorded transfer in a
later week's transaction history. The early transaction view correctly lacks that
later transfer. This is an inconsistency between retrospective source views shared
by the baselines, not a changed memory revision or evidence of a new retrieval
bypassing the pin. Historical pick-inventory claims and questions built on them
need qualification. The frozen inputs remain unchanged for the ongoing comparison;
these runs are not a clean historical forecasting simulation. Deterministic
identity/pin tests remain informative, but source-grounded prose is not necessarily
historically correct merely because a field was present in the snapshot.

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
| E07 | E06 plus one acquisition-event selection paragraph, not promoted | Recorded in isolated arm manifests | `219437fc6150831054ec0908af506159ce7e98311b28ca198f45dedf991d527c` |
| E08 | E06 plus original-context projection in one presentation file | `42fea624a123830e0e1c81be32909edeb2835f1f9cd24d02e94382fd52f0ab1c` | Same as E04 |

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
The E07 gate tested event selection at closeout and tied; it did not test a retrieval fix.

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

## E07 gate: preserve the inconclusive result

The fresh control already saved the material acquisition that the earlier sample
had left only in its brief. Both new arms retained 1/1 eligible events with the
complete asset flow. Both preserved 129 inherited versions and had zero duplicate
source groups. Other article callbacks referred to already-canonical trades and
were excluded from this new-event denominator. First-request messages and tools
matched exactly; the only treatment difference was the closeout paragraph.

Control used 38 calls, 12 edits and 54,038 completion tokens; treatment used 35 calls,
eight edits and 60,347 completion tokens. Both needed five closeout calls. Costs
were $0.13075 and $0.13591, including a small embedding request in treatment.
There were no new uncertain charges. Treatment's article differences preceded
its changed closeout instruction, so they are not evidence for that paragraph.
The tie is inconclusive under the preregistration. Do not replace the fresh
control with the older missing-retention sample to manufacture an improvement.
No full-season E07 or shipping PR will follow this gate.

## E08: original context is technically correct, behavior remains mixed

Automatic review leads currently show only the current storyline summary and
callback question. History can be inspected explicitly, but E06 made no such
inspection in its 17 completed articles. Its 37 automatic review leads included
30 updated versions. A bounded original context could make question replacement
visible without prescribing an answer, minimum lifetime or compulsory article
coverage.

The candidate adds the exact first-version summary/question alongside the same
at-most-three selected leads. Current card selection and update handles stay
unchanged. The historical context has no update selector, is labeled as prior
narrative, and uses the existing pinned history boundary. Missing/filtered original
history is not replaced with a later version. The limits are 200 headline, 2,000
summary and 400 callback characters; the largest observed original summary was
1,016, so recorded original questions fit. Clipping is explicit and full history
remains inspectable through the current lead.

One runtime file changes: `backend/services/reporter/runner/tools/memory_recall.py`,
SHA256 `70c293ac350e8c7d311866d369514506fb0a26c0676209efcd97d61db6519fa7`.
The E04 closeout paragraph and E06 identity baseline remain; E05 and E07 are absent.
Forty targeted tests pass, including PostgreSQL old-pin stability, introduction-
week exclusion, original/current separation and clipping. The Week 7 feasibility
gate completed both articles and closeouts. Control used 34 calls and treatment
31; costs were $0.13566 and $0.13901. All three added origin bindings were exact,
other first-request messages/tools matched, and all 69 prior versions were
unchanged. No duplicate source identities or broken evidence links appeared.

The behavioral result is mixed. A roster-risk question still narrows toward
seeding despite seeing its origin. One updated card overstates what a single
acquisition return answers, although it stays active. A treatment summary moves
an older scoring lead into the wrong week. The same old fact was already present
in current context, so added-origin causality is unresolved. Control also has a
confirmed prior-record error. Both errors and unchanged articles are preserved.

The empty-memory season completed all 17 weeks. The runtime and original inputs
remained frozen. It delivered 32/32 exact origin projections, including two in a
preserved failed attempt. Added origin context covered 17/37 successful storyline
updates; six more had first-version context already, and 14 did not. The changed
pool does not cover every due-callback presentation path.

All 16 source trades retained 16 identities and 24 immutable versions, with zero
duplicate identities, changed typed assets or broken links; 19 pin checks passed.
The final championship article connected an acquired player's decisive score to
the multi-party transaction and full pick price. E06 omitted that callback. E08
also researched historical source transactions again: no exact automatic event
binding appeared, so successful coverage is not demonstrated saved-event recall.

Seven arcs ended with five resolved and two active. Supported closures coexist
with question accumulation, one stale seeding card, and a near-term churn payoff
closing a card whose future-pick component remains unobserved. A memory headline
inverted known prior pick spending into no spending; a subsequent article repeated
a whole-season absence claim. Its resource question later reopened. Technical
identity and origin correctness do not certify narrative grounding or lifecycle.

| Completed trajectory | E06 | E08 |
| --- | ---: | ---: |
| Completion calls | 512 | 537 |
| Prompt tokens | 61,053,883 | 65,968,358 |
| Output tokens including reasoning | 1,004,689 | 1,064,630 |
| Before first draft / draft through submission / closeout | 275 / 157 / 80 | 285 / 175 / 77 |
| Article edit calls | 88 | 124 |
| Explicit memory searches / inspections | 7 / 0 | 3 / 0 |
| Mean article words | 1,062.5 | 1,069.8 |

E08's total cost was $2.31586 including embeddings and the preserved failed
attempt. Its 549 settled completion calls include 12 before a read-only balance
GET failed prior to a new completion dispatch; there was no new uncertain charge.
A labeled recovery used the same committed checkpoint and original request.
The largest response used 20,247 output tokens including reasoning; ten weeks
exceeded the old 8,192 allowance. No context/output-limit failure occurred.

Decision: mixed, no general efficacy promotion. Reduced revision churn is not
established. One accurate final callback cannot isolate the origin projection's
causal contribution in a stochastic season. All unchanged articles, failures and
full accounting remain private.

The source audit found identical draft-pick ownership views across all 17 frozen
snapshots, with three pick identities producing ten week-level disagreements
against recorded completed transfers. This is a shared input limitation, not a
memory-pin failure. A separate audit of 269 visible trade observations found no
final status update after its editorial cutoff; weekly lineup ownership alone
still cannot invalidate a completed transaction. No original source was changed.

## Next isolated hypotheses

E09 corrects legacy average terminology to the weekly median, with no source or
standings computation change. Official feature documentation plus the enabled
frozen setting and 168 team-week outcomes support this mapping; the arithmetic
mean disagrees on 12 outcomes. The raw setting key's mapping is an inference, and
current documentation is not an archived season-specific specification. Draft
#264 has 11 focused passing tests and one unrelated reproduced base failure
excluded. The preregistered two-arm final-regular-week gate completed for $0.31349. Both arms preserved the discriminating sweep above median but below mean; control explicitly rejected arithmetic mean in new memory, while treatment supplied correct median terminology and postseason scope. The motivating error did not reproduce: inconclusive for applied-decision accuracy, no full-season promotion or reroll. Control/treatment used32/36calls and4/13edits, with no new uncertainty. Treatment also introduced a separate false canonical absence-after-trade claim despite a later saved acquisition; correct terminology did not establish general factuality.

E10 is an unpaid local candidate for bounded recent-trade exposure on generic
requests. Sixty-five tests cover selection, temporal boundaries and unchanged
focused behavior. It does not solve unsaved acquisitions or certify summaries.
E11 is a separate unpaid local candidate limiting negative historical claims to
verified transaction windows and distinguishing inventory from spending history;
32 focused tests pass with one unrelated reproduced base failure excluded.
Neither is combined with E09 or inherited by E08. Gate outcomes must be assessed
before deciding on more season spending; ties stay inconclusive without rerolls.

## Reviewable drafts

- [#260](https://github.com/maxwn04/AIdamShefter-v2/pull/260): E04 question identity,
  based on main; mixed live result, not proven by its compatibility tests.
- [#261](https://github.com/maxwn04/AIdamShefter-v2/pull/261): E06 exact trade identity,
  based on main; deterministic correctness and live quality evidence separated.
- [#262](https://github.com/maxwn04/AIdamShefter-v2/pull/262): model message
  compatibility, based on `codex/canonical-preseason-backfill`; 47 targeted tests
  passed and one pre-existing closeout assertion reproduced on the untouched base
  was excluded. This is infrastructure compatibility, not a quality treatment.

- [#263](https://github.com/maxwn04/AIdamShefter-v2/pull/263): original storyline
  context, based on main; 40 targeted tests, technically correct selected-week
  projection, mixed behavior, completed season mixed; accurate callback alongside unresolved grounding/lifecycle failures.

- [#264](https://github.com/maxwn04/AIdamShefter-v2/pull/264): median bonus guidance,
  independently based on main; completed accuracy gate inconclusive; terminology evidence is independent.

No merge, PR approval or deployment is authorized by these experiment outcomes.
