# Reporter experiment index

This index separates completed experiments, rejected candidates and infrastructure
failures. Private articles, participant and source identifiers, snapshots, raw
traces, financial records and artifact locations remain outside the repository.
Each live arm is a single stochastic sample; these results do not establish
universal model superiority or isolate every difference in article quality.

For hypotheses, exact runtime hashes, aggregate costs, representative sanitized
examples and decisions, see the [review ledger](experiment-ledger.md).

## Experiment record

| Experiment | Comparison and outcome | Interpretation |
| --- | --- | --- |
| E00 / E01 | Original full-season baseline missed available acquisition history. A stronger acquisition cue also missed it and stopped at the serialized-input guard before submission. | An application byte guard is distinct from a provider context-token limit. Preserve the negative sample. |
| E02 / E02b | Original-prompt Flash at 8,192 output tokens stopped at the per-response limit. A separately labeled 32,768-token follow-up completed. | Reasoning consumes completion headroom; the follow-up is not an equal-output-limit comparison. |
| E03 | Unchanged Flash baseline completed all 17 requests from empty memory. Historical acquisition information appeared through storyline recall and source verification; duplicate trade identities and question drift remained. | Storyline exposure is not proof that the original event card was retrieved. |
| E04 | A single closeout paragraph preserved the original unresolved storyline question. The matched 17-week season completed, with fewer clear question replacements but increased active-memory pressure and mixed lifecycle evidence. | Promising exploratory evidence, not a general efficacy claim. An initially criticized compound-question closure was corrected to scope-sensitive/ambiguous after source review. |
| E05 | Three-run partial-question gate: fresh control and treatment both retained the disputed question; treatment introduced an additional criterion. A later legitimate closure passed. | Gate failed to demonstrate the intended improvement. Candidate rejected; no full season and no shipping PR. Article differences preceded the changed closeout instruction. |
| E06 selected-week gate | Identical checkpoint and first-request settings; only exact trade-source identity code differed. Control created a duplicate on one repeat save; treatment reused three original items, preserving prior versions and typed assets. | Passed the narrow identity-reuse discriminator. Differing acquisition callbacks occurred before the changed save boundary and are not causal quality evidence. |
| E06 completed season | Two first-week infrastructure failures and the original accepted-but-unfinalized Week 14 are preserved. A labeled recovery from committed Week 13 completed all 17 weeks. | Fifteen source transactions retained 15 identities and 23 versions, with zero duplicate groups; baseline had five groups. All 37 original pin checks passed. Final championship acquisition callback was missed despite earlier canonical saving. Keep technical identity fix; content quality remains mixed. |
| E07 selection gate | Both selected-week arms saved the same eligible new acquisition with complete assets and unchanged prior memory. | Inconclusive under the preregistered tie rule; no full season or shipping PR. |
| E08 original context | Matched Week 7 gate completed; three origin bindings exact, 69 inherited versions unchanged. A separate empty-memory 17-week measurement completed. | Technical feasibility passed, behavior mixed: question narrowing and a misdated historical-memory claim remain. Full season preserves trade identity and produces an accurate final acquisition/price callback, but grounding failures and stale/question-shifting cards remain. No general efficacy promotion or E05/E07 paragraph. |
| E09 | Median terminology correction, draft #264; both matched arms preserved the discriminating bonus result. | Inconclusive for applied accuracy; treatment clarified median/postseason scope but introduced a separate historical memory error. No reroll or full-season promotion. |
| E10 | Bounded recent-trade exposure delivered three exact cards; both matched final-week arms recovered the complete callback. | Technical exposure passed, article-quality gate inconclusive. Ownership contradictions persisted; no full-season promotion or reroll. Draft #265. |
| E11 | Both Week 15 arms newly saved the same false whole-season no-upgrade claim, despite correct guidance delivery. | Failed primary discriminator; candidate not promoted, no full season or shipping PR. More cautious callback scheduling did not fix factual memory. |
| E12 | Due-callback original context: one recovery completed after a preserved upstream failure. Historical acquisition claim corrected with fresh source verification. | Partial/mixed: original repair/cost question still narrows, other errors remain. All 143 prior versions preserved. Reused known-failure control is not independent efficacy evidence; no automatic season promotion. Draft #266 stacks on #263. |
| E13 | Structured identity assessment produced three exact original quotations, but both arms still substituted questions; treatment acknowledged a resolved question while keeping it active. | Rejected proposal-only gate. No canonical writes, article change, shipping PR, reroll or full season. |
| E14 | A reset closeout handoff produced an inspection-only treatment. | Inconclusive; no extra turn or reroll. |
| E15 | Independent identity reviewer passed a frozen twelve-case synthetic batch. | Capability only; no writer-quality or persistence result. |
| E16 | Completed all 17 weeks after a logged final-week recovery from the last complete checkpoint. | Unique trade identities and correct final acquisition callback, alongside factual attribution and unsupported closure errors. |
| E17 | Fresh creation-coherence proposals both bundled unrelated questions. | Not promoted. |
| E18 / E24 | Scoped record context: synthetic tie, then two complete Week 4 arms. | Inconclusive quality result; treatment edits preceded changed feedback. Draft #268 remains a diagnostic correctness candidate. |
| E19 | Temporal-memory reminder at the original problematic closeout. | Inconclusive: fresh control also avoided the historical false streak. |
| E20 | Independent review of four real original-question cases. | Narrow discrimination; suggested successor remedy too permissive for automatic use. |
| E21 / E22 / E23 | Writer repair after review rejection, then selector echo and original-context receipt. | Missing selectors improved, but question substitution persisted; no runtime promotion. |
| E25 | Snapshot ownership-scope caveat, two complete Week 3 arms. | Inconclusive: control lacked inventory exposure; treatment followed the caveat. Code candidate retained, no quality promotion. |
| E26 | Recompute derived numbers before saving memory. | Failed: both proposals repeated the incorrect difference. |
| E27 | Independent relation selection plus exact decimal check. | Narrow pass on fourteen cases; no runtime guard or article-quality proof. |
| E28 / E29 | Verified arithmetic feedback in an earlier receipt, then detailed rejection feedback at the write boundary. | Earlier placement failed; detailed rejection showed no comparative advantage. No executed writes. |
| E30 | Frozen arithmetic reviewer over 546 accepted-season facts. | Seventeen supported relations, no mismatch identified; omission recall and non-arithmetic accuracy remain unmeasured. |
| E31 | Dedicated original-question field at creation. | Failed coherence discriminator: independent questions still fused into the field. |
| E32 | Expose configured roster slots in ordinary source overview. | Two complete Week 1 arms; configuration used in treatment, strict comparative criterion inconclusive. |
| E33 | Atomic independent artifact edits. | Original HTTP 503 retained; one recovered pair passes narrow atomic-edit feasibility. Full-run quality unproven. |
| E34 | Atomic edits in complete reporting. | Matched Week 4 pair preregistered; same original checkpoint and only the edit tool changed. |

The Flash seasons and E06 gate used high reasoning, 32,768 completion-token
headroom, a 16 MB serialized-input guard, original source cutoffs and chronological
interweek indexing. These settings differ from the earlier small-cap comparisons.
Failed attempts and uncertain billing evidence are retained privately; no failed
sample was silently replaced or interpreted as a behavioral success.

## Changes and review status

- **Merged:** [PR #260: preserve storyline question identity](https://github.com/maxwn04/AIdamShefter-v2/pull/260)
  contains the E04 paragraph and its sanitized memory experiment log. Merged into
  `main`; 20 targeted regression tests cover compatibility, not live efficacy.
- **Merged:** [PR #261: reuse exact trade source identity](https://github.com/maxwn04/AIdamShefter-v2/pull/261)
  contains E06, [its detailed evidence and limitations](trade-source-identity.md),
  and this index. Merged into `main`; 68 targeted tests cover identity, provenance,
  temporal boundaries, aliases, retries and concurrency. It does not include E04
  or E05 prompt changes, a verifier change, or the private budget adapter.
- [PR #262: preserve provider continuation messages](https://github.com/maxwn04/AIdamShefter-v2/pull/262)
  contains separate model compatibility work. Its base prerequisite is
  `codex/canonical-preseason-backfill`, not `main`. Validation: 47 tests passed;
  one known closeout assertion reproduced on the untouched base was excluded.
  This is transport compatibility evidence, not a new quality treatment.

- **Merged:** [PR #263: expose original storyline context](https://github.com/maxwn04/AIdamShefter-v2/pull/263)
  adds read-only first-version context to existing automatic review leads. Based
  on `main` and now merged; 40 targeted tests passed. The selected-week technical gate passed,
  completed-season behavior remains mixed; exact exposure is not proof of use.

- **Merged:** [PR #264: clarify median bonus guidance](https://github.com/maxwn04/AIdamShefter-v2/pull/264)
  contains terminology guidance and synthetic regressions; completed accuracy gate is inconclusive.

- [PR #265: offer recent trade leads](https://github.com/maxwn04/AIdamShefter-v2/pull/265)
  contains bounded read-only exposure and 65 passing targeted tests; quality gate inconclusive.

- [PR #266: original context in due callbacks](https://github.com/maxwn04/AIdamShefter-v2/pull/266)
  extends #263 with 45 passing targeted tests; completed challenge partially repairs history but not question identity.

PRs #261, #260, #263 and #264 were merged in that order on November 4 after
explicit user review. PRs #262, #265 and #266 remain drafts; there was no
deployment. General CI does not replace the explicitly run backend test selections. E06 now has selected-week and full-
season identity evidence, but its final-week article missed an important
acquisition callback present in the baseline. The earlier stop was a pre-dispatch
spending guard, not another upstream failure or a context/output limit. Renewal
did not erase uncertain charges or silently replace the interrupted article.
Do not reroll for preferred prose.


The four reviewed merges produced
`ddccadd6c51947da2c9c2c539611e69dd2f11b25`. Combined backend checks had 133 passes
and one reproduced pre-existing bracket-guidance failure; main CI passed. No
additional PR has been merged or deployed.

November 5 continued E16 to completion and evaluated E17–E31 as recorded above.
E32 is complete; its candidate has 86 passing targeted checks. E33 completed one logged infrastructure recovery after an upstream HTTP 503; E34 evaluates complete reporting. A stale tool-version
assertion was reproduced on the baseline and updated to the candidate's declared
version. The frozen reporter behavior was not changed to satisfy that assertion.

[Draft #267](https://github.com/maxwn04/AIdamShefter-v2/pull/267) maintains this
index and the [current review ledger](experiment-ledger.md#current-review--november-5).
[Draft #268](https://github.com/maxwn04/AIdamShefter-v2/pull/268) holds scoped
record diagnostics, with explicit inconclusive paid results. Private artifacts
and account-funding records remain outside this repository; publication of a
separate ownership candidate is still blocked and has not been retried.

The configured-roster-slot candidate is available on
[`codex/roster-slot-evidence`](https://github.com/maxwn04/AIdamShefter-v2/tree/codex/roster-slot-evidence),
head `8fdddfd23215a14a6bae4a74ee585651d07274f9`, with 86 targeted checks passing.
Draft-PR creation was blocked by automatic approval review; it was not retried.
There is no PR CI result for that branch. E33's batch-edit candidate remains unmerged and unpublished; its full reporting
comparison is now E34, after a narrow recovered feasibility pass.

The current ledger files supersede the older summary in PR #267's description;
the earlier metadata update did not succeed. No additional merge or deployment
has occurred.
