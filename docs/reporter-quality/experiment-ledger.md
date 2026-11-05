# Reporter experiment ledger

This ledger separates write-boundary correctness, memory selection/retrieval,
article quality and operating cost. Each live arm is a single stochastic sample.
A better article in one run is not proof that the changed component caused it.
Full private articles, source identifiers, prompts with league data, raw traces,
databases and account-funding records are retained outside this public repository.
The cost figures below are aggregate experiment charges, not a financial ledger
or provider invoice. DeepSeek charges use conservative peak rates; reasoning
already included in completion tokens is not charged a second time.

## Experiment status and decisions

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
| E08 season | E06 plus the E08 presentation file only | 17 completed weeks; one infrastructure failure retained | $2.3159 | Mixed: exact origin exposure and correct final acquisition callback; grounding, lifecycle and revision churn remain unresolved. |
| E09 | Clarify median bonus terminology without changing source computation | Two matched selected-week arms | $0.3135 | Inconclusive applied-accuracy gate: both arms preserved the discriminating result. No season or reroll. |
| E10 | Expose up to three recent trade cards on unfocused requests | Two matched final-week arms | $0.2450 | Exact exposure passed; both arms recovered the callback, so quality improvement is inconclusive. |
| E11 | Bound historical absence claims to the evidence window | Two matched selected-week arms | $0.1870 | Reject: both arms saved the false whole-season absence claim. No season or shipping PR. |
| E12 | Extend original context to already-selected due-callback storyline links | One completed selected challenge after a preserved infrastructure failure | $0.5232, including $0.3543 unknown | Partial/mixed: historical inversion corrected with source verification; question narrowing and other errors remain. No automatic season promotion. Known-failure control reused. |
| E13 | Structured original-scope assessment on storyline updates | Two matched proposal-only closeout calls | $0.1174 | Reject: exact quotes supplied, semantic question substitution and failure to close answered scope persist. No writes or shipping PR. |
| E14 | Start closeout with an explicit evidence-and-article handoff | Two matched proposal-only calls | $0.0270 | Inconclusive: treatment inspected instead of proposing; no additional turn or reroll. |
| E15 | Independent identity reviewer | One frozen 12-case synthetic batch | $0.0101 | Capability passed 12/12, including valid early closure and either/or outcomes. No writer-quality result. |
| E16 | Fresh empty-memory baseline after the four reviewed merges, retaining E08 runtime settings | All 17 weeks completed after explicit checkpoint recovery; both original failed attempts retained | $2.7493, including $0.3543 uncertain | Mixed baseline: unique trade identities and correct championship acquisition callback; factual errors and unsupported storyline closure remain. |
| E17 | Coherent storyline identity at creation | Two fresh matched proposal-only calls | $0.0356 | Not promoted: both proposals still mix the standings question with a separate lineup question. No season or shipping PR. |
| E18 | Subject-scoped source-record review context | Two matched synthetic reviewer calls, five cases each; 76 offline tests | $0.0056 | Tie: both arms pass 5/5. Draft #268 retains a narrow diagnostic-correctness rationale, not demonstrated editing or efficiency gains. |
| E19 | Verify ordered periods before saving temporal claims | Two fresh matched proposal calls | $0.0737 | Inconclusive: fresh control and treatment both avoid the historical false streak. No season or PR. |
| E20 | Independent review on real frozen original questions and evidence | One curated four-case advisory batch | $0.1146 | Narrow discrimination passed; suggested successor remedy remains too permissive for automatic use. |
| E21 | Give the writer independent pre-save review rejection | Two simulated tool-boundary continuations | $0.0563 | Inconclusive: treatment changes wording/status but omits both required update selectors; neither repair can execute. |
| E22 | Echo exact retry selectors in review rejection receipts | Two matched proposal calls | $0.0053 | Inconclusive: both typed-valid; original-question misstatement persists. No runtime promotion. |
| E23 | Repeat immutable original context in the rejection receipt | Two matched proposal calls | $0.0058 | Not promoted: treatment fixes selectors but still invents a title component of the original valuation question. |
| E24 | Scoped record diagnostics in complete reporting | Two complete matched Week 4 arms | $0.2680 | Inconclusive: control made no unnecessary record edit; all treatment edits preceded changed feedback. Independent factual errors remained. |
| E25 | Disclose historical limits of snapshot pick inventories | Matched Week 3 pair active; 27 offline checks pass | In progress | Source values and original snapshots remain unchanged; original Week 2 memory and embeddings validated. |

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

## E09: median terminology, accuracy gate inconclusive

E09 corrects legacy average terminology to the weekly median, with no source or
standings computation change. Official feature documentation plus the enabled
frozen setting and 168 team-week outcomes support this mapping; the arithmetic
mean disagrees on 12 outcomes. The raw setting key's mapping is an inference, and
current documentation is not an archived season-specific specification. Draft
#264 has 11 focused passing tests and one unrelated reproduced base failure
excluded. The preregistered two-arm final-regular-week gate completed for $0.31349. Both arms preserved the discriminating sweep above median but below mean; control explicitly rejected arithmetic mean in new memory, while treatment supplied correct median terminology and postseason scope. The motivating error did not reproduce: inconclusive for applied-decision accuracy, no full-season promotion or reroll. Control/treatment used 32/36 calls and 4/13 edits, with no new uncertainty. Treatment also introduced a separate false canonical absence-after-trade claim despite a later saved acquisition; correct terminology did not establish general factuality.

## E10: recent trade exposure, quality gate inconclusive

E10 adds bounded recent-trade exposure to generic requests, retaining focused
behavior and existing temporal/version boundaries. Its standalone clean feature
head is `f7d9006e522970ccaebbd380d97a19e09e79dfb6`; the operational pair's parent
was E06 with the E04 identity paragraph, without E08/E09/E11. Sixty-five targeted
tests passed. Both original post-Week16 restorations had identical 175 versions
and vectors; source/request/settings and tool definitions were matched. Only
four runtime query/presentation files differed.

The completed first-sample pair cost $0.24504, with no new uncertain calls. It
exposed zero versus three exact trade cards; existing recall groups matched after
exact handle normalization. Both arms retained prior versions and zero duplicate
source identities or broken storyline links. Both independently produced the
complete central acquisition and price callback. Neither used explicit memory
search/inspection; both verified historical source transactions.

| E10 trajectory | Control | Treatment |
| --- | ---: | ---: |
| Completion calls | 34 | 30 |
| Before draft / draft through submission / closeout | 22 / 7 / 5 | 14 / 12 / 4 |
| Article edits | 6 | 10 |
| Article words | 1,271 | 1,168 |

Decision: technical exposure works; article-quality discriminator is inconclusive
because both fresh arms succeed. The older season's miss is not the control.
Both later reversed an ownership relationship despite correct central trade
explanations; treatment also judged bracket winners wrong without establishing
the configured rule. Ordinary sports payoff framing is not itself treated as a
false counterfactual. Fewer research calls with more revisions is not evidence
of general efficiency. No full-season promotion or reroll. The optional read-only
candidate remains draft #265, with these adverse findings disclosed.

## E11: historical evidence scope, rejected

E11 is a separate historical-claim scope hypothesis on the completed E08 parent,
without E09/E10 or the rejected E05 paragraph. One evidence-presentation paragraph
says current holdings are not spending history and a returned recent transaction
window cannot establish a whole-season absence. The exact changed-file SHA256 is
`b194a84221d5a4468484a3c4c35a700dc202e5e7ba804266afafa904a55414fe`.
Thirty-two focused tests pass with one unrelated reproduced base failure excluded.
One control and one treatment Week 15 trajectory were selected, starting from the
same original post-Week 14 state and all 143 complete original vectors. Inspection
JSON abbreviates vector arrays; full coordinate equality was verified against
retained PostgreSQL dumps instead. No regenerated embeddings or future memory.

The preregistered discriminator separately assessed source coverage, article claim,
and newly saved memory. Both mostly kept article inventory claims within the
cutoff; ambiguous wording was not alone scored as definite whole-season absence.
Control nevertheless saved an unqualified season-record-plus-no-upgrade claim;
treatment saved the same claim with stronger certainty. Earlier source-backed
spending contradicts both. The paragraph appeared in three treatment tool results
and subsequent model input, so this is behavioral failure, not missing delivery.
Treatment's historical query concerned another team; its memory search concerned
bracket byes, not the disputed earlier spending.

The pair cost $0.18700: 23 control and 19 treatment completions, plus one treatment
retrieval embedding; no new uncertain charges. Both drafted on turn 14, submitted
on turns 18/16 and completed closeout in five/three further calls. Control created
two artifact versions; treatment one. Neither made edit calls, which does not
mean control never revised. All 143 prior versions and identities survived, with
no duplicate trade source or broken link; first messages/tools were identical.
No context/output/turn limit stopped either arm.

Treatment rescheduled both due callbacks while control resolved them; the linked
arcs remained active in both. This secondary lifecycle difference does not repair
the false historical premise or demonstrate causal improvement. Other factual
errors remain separate, including wrong seed-win counting, period labels and a
scoring-rank claim contradicted by two higher totals in the same output.

Decision: **failed primary discriminator; not promoted**. Retain both first
samples and offline candidate, no full season, reroll or shipping PR. E12 separately investigates original-question context omitted from some
callback-linked storylines in E08. It does not inherit this failed paragraph.

## E12: original context in existing due callbacks

E08's pool excludes storylines already supplied through due callbacks. E12 adds
the same bounded original-question context to those existing linked summaries;
callback selection, current update handles, source/save/verifier semantics and
other recall content remain unchanged. Original history is not current factual
authority or required article coverage. A lookup failure leaves the current
callback visible, with an explicit notice and partial-recall metadata.

The clean feature commit is `aa80a11ea9a813b6c83f86c1f9feaf08de65a0e4`, stacked on
PR #263 head `c925515b0c9abefe0ac4231be9fbb1c9f9194386`. Its sole runtime file hash is
`eac63694770073675835cb980c9b90d7a0f66e894a3c224d1640cc6169b11267`.
Forty-five targeted tests pass on the clean candidate and actual E08-based
operational parent; no failed E05/E11 paragraph or unrelated treatment is present.

The selected challenge explicitly reuses E11's preserved control, whose false
canonical summary is already known. This is not a newly randomized independent
pair. One treatment used the exact original pre-generation state, all 143 complete
vectors, request, source cutoff and shared Flash limits. Before paid dispatch,
two exact original-version projections were checked; all other initial messages,
tools and recall content matched the control.

The first attempt settled nine completions for $0.03527, then an upstream 503
stopped turn 10 before any article or canonical mutation. Its full $0.35432 unknown
reservation remains charged. One bounded recovery after cooldown began a clean
new generation-local transcript from the unchanged pin; it did not claim exact
transcript continuation. No further generation retry occurred.

The recovery completed the article and closeout in 30 calls for $0.13361. Both
article and newly saved storyline/team context correctly recover the earlier
acquisition and its two first-round picks. It actually queried the full historical
transaction window for that team. No explicit memory search or inspection occurred:
this is automatic original-context exposure plus fresh source verification, not
proof of direct saved-event retrieval. The narrower claim that two remaining picks
were unspent is distinct from the old false whole-season absence claim; ambiguous
midseason wording is not forced into a definite factual failure.

The original question still narrows: whether a contender can repair its roster
through lower-cost routes without its spent picks becomes whether the roster holds
up in the playoffs, despite calling the question unchanged. A bye supports waiting
for a playoff result but does not answer the broader repair/cost question. Other
errors include a misdated historical week, an acquisition-month mismatch, a new
matchup summary misclassifying an acquired receiver as a running back, and
unsupported paperwork/anomaly framing of bracket outcomes without a verified rule.

| E12 trajectory | Reused control | Recovery treatment |
| --- | ---: | ---: |
| Completion calls | 23 | 30 |
| Before draft / draft through submission / closeout | 13 / 5 / 5 | 15 / 10 / 5 |
| Create / edit calls | 2 / 0 | 1 / 7 |
| Prompt tokens | 2,379,835 | 3,587,365 |
| Completion tokens including reasoning | 48,856 | 65,701 |
| Article words | 1,093 | 1,086 |

All 143 prior versions and item bindings survive, with no duplicate trade identity
or broken storyline/callback link. Two malformed callback updates returned typed
errors, then succeeded after removing an extra argument; they were not four saved
mutations. The successful article submitted on turn 25 and closeout ended on 30.
Maximum output was 10,355 tokens, maximum serialized input 665,313 bytes; no guard
stopped it. Export-only repair copied verified identical frozen files, with no
paid replay or change to the submitted article.

Decision: **partial/mixed, not a full discriminator pass**. The positive historical
correction is substantive, but original-question continuity and general grounding
are not repaired. Total E12 cost/reservation is $0.52320, including the retained
failure; the reused control was already charged to E11. No reroll or automatic
full-season promotion. Draft #266 remains reviewable technical work with the
negative findings. The next offline investigation is the question-identity write
boundary; the subsequent E13 and E14 results are recorded below.

## E13: explicit identity assessment, rejected

The upsert tool gained an optional assessment quoting the full original summary,
classifying new evidence as continuing or answering it, and stating the basis.
Supplied scope was checked against pinned version one; an answers classification
required resolved status and a resolution summary. Legacy updates and independent
successors remained compatible. A callback trigger was not substituted for the
question. Eighty targeted tests passed on both the actual operational parent and
clean public candidate, including temporal boundaries, retries and valid closure.

The parent was measured E12, with its presentation shared by both arms; no efficacy
was assumed from stacking those mixed candidates. One fresh control and one
treatment completion used the same preserved pre-update closeout context. Only
the upsert definition differed. These were proposals only: no tool execution,
canonical mutation or new article. The runtime-file SHA256 was
`4457c599fa0e3ae971c497b70c55cb33a89a4ed297e62654fe2a3ce1d301523e`.

Treatment supplied three exact original summaries, but both arms still replaced
an unresolved repair/cost question with playoff performance. In the already-
answered seeding case, treatment explicitly said the original question resolved
in its basis, yet selected continues/active. The syntactic consistency check could
not detect that semantic contradiction. Both retained the third arc's genuinely
unanswered pick-value/ownership components; that did not repair the focal failures.

**Decision: reject.** Exact quotation did not establish question continuity.
The two calls cost $0.11741: $0.05831 control and $0.05910 treatment, with
2,344 versus 4,442 output tokens including reasoning. No new uncertainty,
embedding calls, reroll, shipping PR or full season. The candidate and failures
remain retained offline. E14 separately tests conversation anchoring using the
original tools, without this rejected contract.

## Reviewed changes and remaining drafts

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

- [#265](https://github.com/maxwn04/AIdamShefter-v2/pull/265): bounded recent-trade
  exposure, based on main; 65 targeted tests, quality gate inconclusive with adverse evidence.

- [#266](https://github.com/maxwn04/AIdamShefter-v2/pull/266): original context in due
  callbacks, stacked on #263; 45 tests, historical correction with persistent question narrowing; mixed completed challenge.

Experimental outcomes alone did not authorize merges. On November 4 the user explicitly reviewed and authorized merging #261, #260, #263 and #264; the remaining PRs stay draft. No deployment or PR approval review was performed.


## Reviewed baseline and follow-up results — November 4

The user reviewed and requested merging #261, #260, #263 and #264, in that
order. All four merged without conflicts. The resulting main is
`ddccadd6c51947da2c9c2c539611e69dd2f11b25`. No approval review was submitted.
The other experimental PRs remain unmerged.

Combined targeted backend validation: **133 passed, 1 failed**. The failure is
`test_bracket_identity_survives_public_cards_with_overlapping_matchup_numbers`:
the assertion expects guidance saying the recorded winner may differ from the
higher-scoring team. The same assertion fails on pre-merge main
`5dfeb036fd756ffed1c9b6d9a6ed84757e611525`. It is recorded as a pre-existing
failure, not silently excluded or treated as a merge regression. Both final-main
CI checks, quality and migrations, passed.

### E14: explicit closeout handoff — inconclusive

The control retained the full research conversation. Treatment began an explicitly
new conversation containing the unchanged request, current memory, complete latest
research brief, unchanged submitted article, verifier/submission receipts, saved
event arguments and receipts, and closeout guidance. This was a proposal-only
comparison: no returned tools or canonical memory mutations were executed.
Seven offline packet-integrity checks passed.

The control made three storyline proposals and retained the known question drift.
Treatment requested a standings lookup instead of proposing a memory update.
Under the preregistered inspection-only rule this is **inconclusive**, not evidence
that context reset improves identity preservation. There was no extra treatment
turn or favorable reroll. Two settled completions cost $0.026976372; no embeddings
or new uncertain request. The intervention was not promoted.

### E15: original preparation checkpoint — subsequently executed November 5

A synthetic reviewer test was prepared to distinguish question substitution,
partial answers, legitimate early closure, separate successor stories, missing
origin evidence and ambiguous outcomes. No paid call was dispatched. It remains
separate from the merged baseline and is not evidence of improved reporting.

### E16: original baseline registration and historical partial checkpoint

E16 starts with empty canonical memory and the original chronological 17-week
source/editorial plan. Reporting changes exactly match the four approved merges.
Relative to the completed E08 runtime, only the merged median-scoring guidance
changes. The existing E08 preseason snapshot support, DeepSeek continuation,
private spending controls and simulation safeguards remain runtime prerequisites;
this is not a claim that unmodified main includes those unmerged facilities.

Settings remain direct Flash with high reasoning, 32,768 output tokens,
16,000,000 serialized input bytes, 60 research plus 6 closeout turns, 600-second
transport timeout, no SDK generation retries or fallback, and chronological
3,072-dimensional embeddings. Serialized bytes are an application guard, not a
provider context-token limit. The forecast is approximately $2.30 plus embeddings;
a hard reservation guard may stop the run with partial coverage.

The audit separates acquisition discovery, saving, automatic exposure, explicit
retrieval and article use. It also measures original-question retention, valid
closure versus replacement, unsupported historical claims, duplicate trade
identities, and research versus revision work. There are no storyline-duration
quotas or target-specific hints. New interventions require their own recorded
hypothesis and comparison; rejected E05/E11/E13 and mixed E12 are not inherited.


### E17: coherent identity at creation — preregistered, unrun

E16's first new storyline exposed a different failure from update drift: its
headline and callback concerned a scoring-format trend, while its explicit live
question concerned a separate lineup decision. The card already lacked a stable
single development at creation. This observation motivates a new test; it does
not establish that guidance will fix it.

The candidate adds one paragraph to closeout: keep a new storyline's headline,
unresolved question and callback about the same coherent development. Independent
questions should not be combined merely because one article mentions them.
Related compound questions remain valid, and no-op remains allowed. No minimum
duration, card count, named target, schema, retrieval or verifier change is added.
The existing identity and callback rules remain intact.

The gate uses one fresh proposal-only control and one treatment at the first
eligible creation opportunity in the same completed E16 Week 1 conversation.
Only the encoded closeout paragraph differs; all 83 messages, the article,
source state, prior event receipt and 25 assistant reasoning fields are preserved.
Offline checks verified the exact difference and unchanged surrounding payload.
Returned tools will not execute. Both arms must actually propose a new storyline;
inspection-only, no-op and ambiguous cases are inconclusive, as are quality ties.
Only a coherent treatment versus a bundling control, without a new unsupported
claim or invented question, supports narrow proposal-level improvement. No reroll
or automatic full-season promotion is planned. The shared spending guard stopped E16 before the gate could dispatch. Both
preregistered arms remain unrun; the frozen packets are retained for later review.

Draft #267 changes documentation only, so its paths do not trigger the repository's
backend/frontend or database CI workflows. The merged main checks and local
combined backend test results above are the relevant existing validation.


### E18: scoped record-review context — offline candidate

A live E16 revision trace prompted a synthetic reproduction: a correct sentence
listing two teams at different records generated two attribution warnings because
the verifier compared every record-like number with every named team's source
record. Historical and current periods were also mixed in those comparisons.

[Draft #268](https://github.com/maxwn04/AIdamShefter-v2/pull/268) replaces that
heuristic with bounded source-record contexts grouped by subject identity. The
contexts preserve source references, periods, ties, units, limitations and the
relevant draft passage. They explicitly make no match/mismatch verdict. Other
diagnostics, traceability errors and submission behavior remain unchanged; the
active E16 verifier is untouched, and E17 is not inherited.

The final candidate passed **76 targeted tests**. The correct two-team fixture
changes from two false attribution warnings to two scoped contexts. A deliberately
wrong record remains visible beside its authoritative source; this preserves
review evidence but does not establish that the writer will correct it. Tests
also cover invalid bindings, poisoned claim text, duplicate references, distinct
identities with equal display names, unknown periods, ties, units, limitations,
ordinary prose without records and output truncation.

Decision: reviewable offline presentation candidate, **not promoted as a quality
or efficiency improvement**. No paid E18 call, full-season treatment or deployment
has occurred. The next decision requires evaluating unnecessary edits and genuine
error correction separately, without treating disappearance of warnings as success.

E16 initially completed seven weeks without an upstream failure. Its later Week 8 closeout failure is recorded below.
The early baseline saved all five observed Week 2 trades as five canonical
identities; E08 had saved two by that point. This is sample coverage, not attribution
to the median-guidance difference. Later recall, use and final season quality remain
pending. E17's one-file candidate passed 14 targeted closeout/definition tests and
remains unrun locally.


E18 evidence clarification: the inspected edit immediately following the live
record warnings clarified a real sentence ambiguity. It is not counted as wasted
work caused by those warnings. The synthetic cross-comparison reproduction
supports the narrower presentation concern; live efficiency remains unmeasured.
Draft #268's quality CI passed on current head `12389772989c95e4078889da2f78f7500b0d3a5a`. Its final change only clarifies the evidence; production code and tests are identical to the 76-test candidate.


### E16 infrastructure checkpoint and bounded recovery

Week 8's article was accepted at turn 25. The completion requested at turn 29
failed with HTTP 503 after 11.154 seconds, carrying an upstream connection-reset
message. No useful correlation ID was available; the evidence does not establish
whether the provider or environment network path originated the failure. No SDK
retry or provider fallback occurred.

The failed request executed no tools, and Week 8 committed no canonical memory.
The memory head remains exactly the complete Week 7 checkpoint. The supported
controller cannot resume that exact in-memory closeout, so one separately labeled
infrastructure retry is prepared from Week 7. The original accepted article, raw
trace, failed generation and full uncertain reservation remain preserved. A new
article from recovery will not replace the original result in the evidence record.

Twenty targeted reconciliation, budget and sanitized-diagnostic tests passed.
Runtime/source-pin/controller preflight also passed without a provider call.
Recovery waits for a 15-minute cooldown, retains the unchanged hard allowance and
may stop with partial season coverage if the next reservation cannot be covered.
A further upstream failure stops paid work, including new gates; no repeated
quality retries are permitted.

E18's separately registered synthetic reviewer gate uses two completions over
five cases: correct multi-team and historical passages, wrong current and tied
records, and unsupported period attribution. Only record diagnostics differ. Nine
packet/scorer checks passed. A tie or incomplete response remains inconclusive;
no paid E18 call has run. See draft #268 for the frozen discriminator and limits.


### E16 recovery result and interim quality evidence

The one authorized recovery completed Week 8 in 48 turns, and Week 9 also
completed in 48 turns. Verification confirmed identical request, settings, source
snapshot and input memory between the two Week 8 attempts. The failed attempt
made no canonical memory commit; recovery produced one revision. The original
accepted article's hash remains unchanged and its trace stays separate. No new
upstream failure occurred through this checkpoint. The remaining season continues
under the same guard; full coverage and the later gates are not guaranteed.

Through Week 8, 13 source trades map to 13 identities and 19 versions, with zero
duplicate groups, changed typed assets or broken links. Ten historical checkpoints
preserve their original visibility. Through Week 7, 13 of 14 available completed
trades were saved in their first available week. The unsaved move appeared in two
source responses: it is a selection/retention observation, not a discovery failure.

Qualitative findings remain mixed:

- A new card combined a scoring-format theme with a separate lineup question
  before any update drift. That motivates the unrun E17 creation test.
- A later acquisition-value card explicitly said its purchase was unvalidated,
  then changed the open question to sustaining a playoff run under the same
  identity. Its automatic exposure came through a due-callback link without the
  first version. This identifies a coverage route, not proof that E12 would fix
  semantic drift; that candidate's prior result remains mixed.
- A market summary named a pick as the price of a package that also sent two
  players. The underlying trade and another summary retained the full package.
  Typed asset correctness therefore does not certify complete narrative prices.
- One short-lived volatility/standings arc plausibly answered its explicit
  either/or question. It is not counted as premature merely because it closed
  before its nominal review week.

Across the seven matched completed weeks, E08 used 223 completions and 58 edit
calls, versus E16's 216 and 47. These are descriptive single-sample counts with
failures recorded separately, not causal evidence of efficiency or article quality.
The Week 8 retry also exposed three stale-revision conflicts from batching edits
against the same article revision; other edits made useful factual corrections.


### E16 checkpoint through Week 13

Thirteen weeks completed, with no additional upstream error after the single
Week 8 recovery. The season continues under its unchanged per-request spending
guard. E17 and E18 remain unrun, so neither has a paid quality verdict.

The completed audit through Week 11 found 20 source transactions mapped to 20
canonical items and 27 versions, with no duplicate source groups, altered typed
assets or broken links. Thirteen retained checkpoints preserved their original
visibility. Of 22 source trades available by that boundary, E16 saved 20, versus
15 for E08 and 14 for E06 at the same boundary and identical source cutoffs. All
saves in these counts occurred in the source's first available week. Coverage is
not a quality score, and omitted trades are not automatically editorial failures.

The matched eleven completed weeks used 377 completion calls and 87 article-edit
calls in E16, versus 357 and 84 in E08. The early seven-week reduction did not
persist at this boundary. Failed attempts stay in experiment costs but outside
these completed-week counts; useful factual repairs and stale-revision conflicts
are distinguished when interpreting edits. These counts do not isolate causality.

Week 12 correctly covered and saved a three-team acquisition, including the
outgoing first-round pick. Final-week recall and use remain pending. Separately,
a verified Week 11 memory summary called two double-loss weeks consecutive even
though frozen standings show two wins in the intervening week. That exact false
summary was exposed in Week 12 automatic recall, and the next article repeated
the consecutive-loss assertion. This is evidence of a saved→exposed→repeated
factual error, not proof of a unique causal path or of a regression caused by a
particular merge. It motivates a separate hypothesis about source-supported
temporal claims in memory; neither E17 nor E18 currently addresses that boundary.


### E16 November 4 budget stop — superseded by the November 5 completion below

E16 completed Weeks 1–16. Week 17 received three settled research responses, then
stopped before turn 4 was sent because the remaining conservative allowance could
not cover the next request reservation. It produced no Week 17 draft or submitted
article and committed no Week 17 memory. This was an application spending guard,
not a provider context limit, output limit, empty account or another upstream
failure. The original accepted Week 8 article and failed closeout remain separate
from the successful recovery. There was no second recovery or quality reroll.

Aggregate E16 charge is **$2.629523724**: $2.275202124 settled across providers plus
the retained $0.3543216 uncertain Week 8 request. It includes 563 dispatched
completion requests (562 settled, one uncertain) and 21 embedding requests costing
$0.008974680. The blocked request was not sent or charged. Older spending and
uncertain requests remain in the private cumulative ledger; they were not reset.

The full frozen runtime SHA256 is
`8c917447d2b187464673bc4ba678468fed48e56a8d9ad7b4c8c6667b6b12cb64`
(sorted JSON of files, packages, configuration, Python and pricing, using default
JSON separators). Its 382-file map SHA256 is
`4d3b3209da0ae8f237ddd1cc22d28fc1f128f559ee8833bf23e66e8ae69a7e4f`
(sorted compact JSON). All files and the saved pricing manifest remain unchanged.
The only runtime-file difference from E08 is the merged median-guidance file.
Observed maxima across recorded attempts were 240,670 prompt tokens, 14,546
completion tokens including reasoning, and 797,793 serialized input bytes. These
are observations, not new limits; the frozen limits remain those declared above.

Technical and behavioral findings:

- **Trade identity:** 21 source transactions, 21 canonical identities, 29 versions
  and eight repeat versions; zero duplicate groups, changed typed assets or broken
  links. All 19 retained checkpoint visibility/content checks passed.
- **Coverage:** 21 of 23 available trades were saved in their first available
  week. At the same Week 16 boundary E08 had saved 16 and E06 had saved 15. These
  are identical-source single samples, not evidence that the median guidance
  caused better selection or that every extra card was useful.
- **Acquisition path:** the acquisition was first encountered and canonically
  saved in Week 12. Weeks 13–14 mentioned it through broader recalled context,
  without an exact original-event binding. Week 16 rediscovered the transaction
  through source tools, saved grounded facts and used the full acquisition/price
  in the semifinal article. Its repeat save reused the original identity. This
  demonstrates source rediscovery and use, not direct event-card retrieval. The
  championship callback is unmeasured because Week 17 never wrote an article.
- **Original context:** all 26 selected updated leads received their exact
  immutable origin. Across 36 successful storyline updates, 27 had a first
  version somewhere in automatic context, including 20 using the added projection;
  nine did not. Later explicit retrieval can also supply context. Delivery is
  not semantic adherence.
- **Lifecycle:** all seven identities were reviewed against their original
  summaries/callbacks and subsequent question/status transitions. There are
  legitimate short-scope closures, an ambiguous multi-theme creation, clear
  acquisition-to-playoff question substitution, and scope-sensitive evolution.
  The substituted acquisition arc later explicitly hands its remaining payoff
  to a broader market story; that matters when judging its closure. The handoff
  is textual, without a structured related-storyline link. No blanket premature-
  closure count or longevity quota is applied.
- **Grounding:** the saved→exposed→repeated false streak claim remains a verified
  failure. A later article incorrectly calls one qualifying record the weakest
  despite a worse record in its own table. The semifinal closing paragraph assigns
  an eliminated top seed's record to the finalists. Correct trade assets and
  useful callbacks therefore do not certify authored summaries or conclusions.
- **Work and voice:** over sixteen matched completed weeks, E16 used 531
  completions versus E08's 507, with 110 edit calls in each. E16 used 297
  pre-draft turns, 159 draft-through-submission turns and 75 closeout turns, versus
  270, 164 and 73. Failed attempts remain separate in those counts and included
  in costs. The articles range from 856–1,307 words with 5–9 headings, using short
  numerical openings, matchup sections, tables and pointed concluding lines.
  The style is readable in places, but emphatic comparisons and conclusions can
  outrun the evidence. These observations are not a causal quality score.

**Decision:** retain the merged baseline and its partial result; do not claim a
new general quality improvement. E17 and E18 are **unrun due to budget**, not
failed comparisons or favorable ties. Their frozen inputs and offline test
evidence remain available. No new treatment was promoted, merged or deployed.
The most concrete next unresolved question is how to validate temporal and
comparative claims in saved narrative without suppressing useful synthesis.
The known retrospective pick-ownership input limitation still applies.


### November 5 continuation

The user renewed authorization to use the remaining provider balance. Historical
charges and all five uncertain requests remain in the private cumulative ledger;
the new spendable ceiling subtracts those reservations and does not add the old
unused allowance a second time. Embedding authority remains separate. Accounting
checks include repeated recovery and repeated funding renewal without resetting
historical calls.

After the cloud environment restarted, the disposable database had to be restored
from its verified terminal export. The original campaign and export are retained.
A separately recorded infrastructure migration changes only the isolated target
identity and local asset paths, with the matching campaign receipt hash. The
campaign UUID, all previous generations, all source and memory pins, and the
frozen runtime remain unchanged. Full controller reconciliation passed; Week 17
has no prior article or canonical writes. Its recovery uses the controller's
explicit failed-attempt retry from the complete Week 16 memory boundary, not an
in-memory transcript continuation. No earlier week is regenerated.

The Week 17 recovery completed. E17 and E18 retain their original frozen
paired tests and decision rules; the earlier unrun budget outcome remains part
of their history. Results below will distinguish source discovery, saved memory,
recall exposure, article use and factual grounding. No additional PR merge or
production change is authorized or performed by this continuation.


### E16 completed season — November 5

The restored Week 17 attempt succeeded in 34 turns: 21 research turns, a first
draft at turn 22, submission at turn 31, and three closeout turns. The accepted
article is unchanged. Recovery added $0.119739606 in settled generation cost and
no uncertainty or embedding charge. Full E16 cost is $2.749263330, comprising
$2.394941730 settled plus the earlier $0.3543216 unknown request. All 597
dispatched completion requests and 21 embedding requests are accounted for; the
old budget-blocked dispatch is not counted as a billed request.

The final article leads with a championship acquisition callback and reconstructs
the multi-party trade, including the future first-round pick and each player's
direction. The trace distinguishes the stages: original canonical save in Week
12; broader storyline exposure in Week 17 without an exact original-event binding;
fresh transaction research in turns 3–4; a bound trade fact at turn 11; a trade-
payoff callback at turn 21; and article use at submission. There was no explicit
memory search or inspection. This is contextual exposure plus source rediscovery
and use, not proof that direct event retrieval caused the callback.

The repeat trade save reused its original identity. Final totals are 21 source
transactions, 21 canonical trade items, 30 versions and nine repeat versions,
with zero duplicate groups, source collisions, changed typed assets or broken
links. Twenty retained checkpoint visibility/content checks passed.

Lifecycle remains a material failure. The final two active storylines were marked
resolved; one summary explicitly admits that the second half of the original
question is unanswered, and another replaces an original pick-valuation question
with a title question while saying valuation remains open. All seven current arcs
are now resolved and all twelve current callbacks satisfied. The text is retained
in history, but no active follow-up preserves those unresolved components. This
is a scope/status contradiction, not a rule that stories should live longer.

The final article correctly separates the finalists' regular-season records and
acknowledges unknown eventual pick value. Earlier factual errors remain part of
the season result. Its temporary-ownership metaphor is not established by the
transaction record, and emphatic title-causality language exceeds a fully tested
counterfactual. Successful discovery does not certify all prose or memory claims.
The retrospective source-ownership limitation remains unchanged.

Across all seventeen completed weeks, E16 used 565 completions and 120 artifact
edits, versus E08's 537 and 124. Research/drafting/closeout turns were 318/169/78
versus 285/175/77. Failed attempts are separate from those work counts and included
in total spending. These are descriptive single-season comparisons, not a causal
claim for the merged guidance or an efficiency score.

### E17 paid gate — not promoted

Both fresh arms proposed a new storyline at the same original creation boundary.
Control combined a median-driven standings question with a second-quarterback
selection question. Treatment retained that same mixture in its headline,
summary and callback despite the added coherence instruction. Both exercised
the boundary, so this is observed non-improvement rather than an inspection-only
result. Under a more permissive interpretation of related scope, it still fails
the preregistered control-fails/treatment-improves discriminator.

The two calls cost $0.035560248. No proposed tool executed, article changed,
canonical memory mutated, uncertain request appeared or favorable reroll ran.
The candidate and raw responses are retained; no E17 full season or shipping PR
is justified by this result.


### E18 paid gate — inconclusive tie

Both control and treatment preserved the correct current and historical records,
corrected the two genuine record errors, and declined unsupported period attribution.
Both passed all five predeclared cases, including exact corrected text and relevant
source references. The control did not make the unnecessary edit required by the
primary discriminator, so the result is an inconclusive tie, not treatment success.
Two calls cost $0.005562408, with no tool execution, embedding, uncertainty or
reroll. Draft #268 retains its separate offline evidence that the old diagnostic
cross-compares unrelated records. This gate does not establish better real editing
decisions, fewer revisions or better articles; no season is promoted from it.

### E19 — temporal claims in durable summaries

The next proposal-only comparison uses the original pre-write Week 11 context.
Its single added paragraph asks the writer to verify the ordered periods behind
a temporal claim, distinguishing recurrence from a consecutive sequence. All
original facts, accepted article, tools and assistant reasoning are identical;
E17 and E18 are not incorporated. Both arms must exercise the selected update,
and treatment must remove a source-contradicted temporal claim made by the fresh
control without adding another factual or identity regression. Both correct,
inspection-only, ambiguous or missing proposals are inconclusive, with no rerolls.
The original observed failure is a correct list of separated bad weeks compressed
into an unsupported consecutive streak, later exposed and repeated in an article.


### E19 paid gate — no fresh control failure

Both fresh arms exercised the selected existing storyline update. Control
explicitly separated the earlier double loss, an intervening sweep, and the later
third double loss; treatment also retained the correct separated-week sequence.
The historical error remains verified, but the fresh control did not reproduce
it. The primary discriminator therefore failed, and this $0.073723008 pair is
inconclusive. There were no executed tools, canonical changes, retries or new
uncertainty. No E19 season or shipping PR is promoted.

### E15 and E20 — independent review has limited positive evidence

The original, unchanged E15 synthetic packet ran once after nine scorer tests
passed. It correctly handled all twelve cases for $0.0100902: six valid
continuations/closures, four clear substitutions or unsupported closures, missing
origin evidence, and an ambiguous payoff criterion. In particular it accepted a
supported early closure, a negative answer, an explicit either/or outcome and a
separate successor after the original was answered. This measures reviewer
capability, not an effect on reporting.

E20 then reviewed four curated real frozen updates, with original and prior cards,
complete source-tool observations before the proposal, source-bound brief facts,
and the unchanged submitted article. Each case retained its own cutoff and source
snapshot. Expected verdicts were withheld. The reviewer flagged both final-week
scope/status contradictions, accepted the supported final-period comparison,
and accepted the scope-sensitive early either/or closure without imposing an
arbitrary duration requirement. The one batch cost $0.1145943.

This is narrow positive advisory evidence. The review sometimes suggests moving
an unanswered component into a successor without sufficiently preserving the
original question's identity. Its reasons are not an automatic safe fix. No
writer feedback, memory mutation or article change occurred in E20. Full evidence
packets also have a material token cost; no efficiency benefit is assumed.

### E21 — repair wording is not an executable repair

The paired probe continued the exact original final-week post-proposal context.
Control retained ordinary successful receipts; treatment replaced two receipts
with explicitly simulated pre-save rejections containing the unchanged E20
reviewer reasons. Every other message, original assistant tool argument and
reasoning field, source observation, tool definition and submitted article was
unchanged. No real tool result or archived database was edited.

Control called the completion tool without repair. Treatment proposed active
summaries that retained unresolved valuation, but omitted both `id` and
`update_handle` from each update. The existing typed input validator rejects
both calls: a creation key or existing update selector is required. Under the
predeclared malformed/incomplete-proposal rule this is **inconclusive**, not
successful memory repair. The pair cost $0.056257068; no extra turn, reroll or
canonical write followed.

E22 separately tests the interface issue by adding an explicit retry object that
echoes each original update selector and the existing tool contract. Reviewer
advice and all substantive reporting context stay unchanged. Typed validity is
checked before semantic quality. This is a new receipt-format comparison, not a
continuation or favorable reroll of E21, and no production review hook is installed.

### E22 — valid selectors, no demonstrated receipt-format benefit

Both fresh arms supplied the two exact existing update handles and passed the
real typed argument validator. Both kept the valuation questions active. This is
an actionability tie, so the added selector echo does not pass the primary
control-fails/treatment-improves discriminator. More importantly, the treatment
still rewrote an original valuation question as a question about winning the
championship. Correct selectors and active status do not establish correct
question identity. Two calls cost $0.005262288; no tools executed or canonical
state changed. No season or shipping change is promoted from this result.

E23 separately tests adding the exact immutable original card to each rejection
receipt. The selector-bearing receipt is an interface choice shared by both
arms, not an E22 efficacy claim. Reviewer reasons, source context, submitted
article, tool definitions and all previous assistant reasoning remain unchanged.
The discriminator requires supported original-scope repairs in treatment and a
semantic failure in fresh control; equivalent repairs remain inconclusive.

### E23 — original text exposure still does not establish faithful repair

Control again omitted both required selectors and explicitly rewrote the original
valuation question as a title question. Treatment returned valid handles and kept
valuation open, but still asserted a title component of that valuation-only
original. It also centered the other original production/standings-payoff question
on the championship result. This does not pass complete original-scope repair.
The pair cost $0.005794656; no tool executed or memory changed. The reviewer
intervention is not promoted to a live write hook or a longitudinal run.

### E24 — complete reporting test of scoped record diagnostics

This comparison returns to the independently reproduced record-diagnostic defect
in draft #268. One fresh control and one treatment will each write the original
Week 4 request from the identical completed Week 3 database, source cutoff and
pre-Week 4 embeddings. Only the record-verification implementation differs.
Seventy-six targeted tests also pass on the actual E16 operational parent with
the candidate applied. No rejected storyline paragraph or review intervention is
incorporated.

The review will classify each record diagnostic and following edit against the
correct subject and period. A behavioral improvement requires an unnecessary
control record edit avoided by treatment without a missed real error. Warning
counts, different prose and fewer total revisions alone are insufficient. If the
arms do not expose comparable opportunities, the result remains inconclusive.
Both complete articles, all attempts and memory changes will be preserved.

Preflight required two recoveries before any E24 paid call: full original embedding
coordinates were read from the preserved database because the JSON export displays
abbreviated vectors, and unused restored containers were removed after verifying
no new generations or committed changes. Both arms will run sequentially to keep
room for verified exports. Original vector IDs, metadata, source-content hashes
and timestamps before the original Week 4 generation match; no future memory or
new embeddings are substituted. The pair has a conservative $0.45 forecast and a
$1.10 aggregate cap, within the existing shared hard allowance.

### E24 control checkpoint

Control submitted on turn 21 and completed closeout on turn 25 for $0.130382364.
It received 38 record warnings across two verification calls (19 repeated in each),
recognized the cross-comparison noise, and made no unnecessary record edit. One
edit corrected a real trade-asset direction; three adjusted wording. The primary
efficiency discriminator therefore cannot pass on this sample. Treatment still
runs for the preregistered factual and completion audit. A temporal description
remains wrong: evidence from the preceding week is described as several weeks
old. This is distinct from an incorrect raw standings value.

A synthetic regression now covers a team name ending in a period: paragraph
context keeps that subject and its opponent's records separate. Eleven tests in
the changed module pass on the published head; the implementation remains the
same file used by the running treatment.

### E25: disclose snapshot ownership limitations

A separate offline candidate targets an audited source limitation. The frozen
pick-inventory view overlays a selected endpoint snapshot; it does not reconstruct
ownership from each week's dated transfers. Some recorded transfer chains disagree
with the earlier ownership view. Other apparent discrepancies precede the first
recorded transfer and cannot alone rule out missing or preseason history.

The change qualifies inventory summaries and pick rows, including empty lists,
without altering raw values, identities, dates or source snapshots. Dated trade
assets and unrelated player records remain unaffected. The snapshot is described
as selected for the reporting cutoff, not proof of historical observation. The
tool implementation version also changes to identify the presentation revision.
Twenty-seven targeted checks pass on both the public candidate and actual E16
operational parent. No record-verifier or rejected memory treatment is inherited.

The preregistered pair uses the original Week 3 request and the identical Week 2
checkpoint with all 22 original pre-generation embeddings. Treatment must qualify
or avoid an unsupported historical inventory/resource constraint made by fresh
control while preserving correct dated transfers. Both arms must encounter
inventory evidence; no exposure, equivalent qualification, missing analogous
opportunity or ambiguous scope remains inconclusive. Arbitrary SQL is outside
this narrow curated-roster presentation change. No ownership reconstruction,
source regeneration, favorable reroll or production rollout is authorized by the
experiment itself. Its conservative forecast is $0.40 with a $1.10 pair cap inside
the existing shared allowance; paid launch follows E24's terminal audit.

### E24 terminal comparison: inconclusive

Both Week 4 arms completed submission and memory closeout. Control used 25 calls
and four edits; treatment used 28 calls and six edits. Total cost was $0.268010484,
with no new uncertain request or embedding call. Control made no unnecessary
record edit, so the preregistered avoided-edit discriminator cannot pass. Treatment
received eleven contextual record advisories, with no edit after verification.
All six of its edits happened before its first changed diagnostic feedback; their
count and the different article cannot be attributed to that feedback.

Both arms preserved all 29 prior memory versions, original content and valid
evidence bindings. Repeated trade saves retained their original identities.
Grounding remains imperfect: control misstated a historical interval; treatment
miscomputed a points gap and described a flexible lineup slot as mandatory for
one position. The arithmetic error reached a saved fact and a canonical storyline
resolution. These are retained failures, not corrected experiment outputs.

Decision: no article-quality or revision-efficiency promotion. The diagnostic
candidate remains reviewable for its offline correctness rationale. The next
separately scoped test is E25's ownership-evidence limitation; it inherits the
unchanged E16 baseline, not this verifier candidate.
