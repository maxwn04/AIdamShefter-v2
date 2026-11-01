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
| E10 / E11 | Separate local candidates for recent-trade exposure and historical-claim scope; offline tests pass, no paid gate yet. | Prospective hypotheses, not promoted outcomes. |

The Flash seasons and E06 gate used high reasoning, 32,768 completion-token
headroom, a 16 MB serialized-input guard, original source cutoffs and chronological
interweek indexing. These settings differ from the earlier small-cap comparisons.
Failed attempts and uncertain billing evidence are retained privately; no failed
sample was silently replaced or interpreted as a behavioral success.

## Drafts for review

- [PR #260: preserve storyline question identity](https://github.com/maxwn04/AIdamShefter-v2/pull/260)
  contains the E04 paragraph and its sanitized memory experiment log. Based on
  `main`; 20 targeted regression tests cover compatibility, not live efficacy.
- [PR #261: reuse exact trade source identity](https://github.com/maxwn04/AIdamShefter-v2/pull/261)
  contains E06, [its detailed evidence and limitations](trade-source-identity.md),
  and this index. Based on `main`; 68 targeted tests cover identity, provenance,
  temporal boundaries, aliases, retries and concurrency. It does not include E04
  or E05 prompt changes, a verifier change, or the private budget adapter.
- [PR #262: preserve provider continuation messages](https://github.com/maxwn04/AIdamShefter-v2/pull/262)
  contains separate model compatibility work. Its base prerequisite is
  `codex/canonical-preseason-backfill`, not `main`. Validation: 47 tests passed;
  one known closeout assertion reproduced on the untouched base was excluded.
  This is transport compatibility evidence, not a new quality treatment.

- [PR #263: expose original storyline context](https://github.com/maxwn04/AIdamShefter-v2/pull/263)
  adds read-only first-version context to existing automatic review leads. Based
  on `main`; 40 targeted tests passed. The selected-week technical gate passed,
  completed-season behavior remains mixed; exact exposure is not proof of use.

- [PR #264: clarify median bonus guidance](https://github.com/maxwn04/AIdamShefter-v2/pull/264)
  contains terminology guidance and synthetic regressions; completed accuracy gate is inconclusive.

All five are drafts, with no merge or deployment. General CI does not replace
the explicitly run backend test selections. E06 now has selected-week and full-
season identity evidence, but its final-week article missed an important
acquisition callback present in the baseline. The earlier stop was a pre-dispatch
spending guard, not another upstream failure or a context/output limit. Renewal
did not erase uncertain charges or silently replace the interrupted article.
Do not reroll for preferred prose.
