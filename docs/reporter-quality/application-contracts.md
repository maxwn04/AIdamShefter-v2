
# Reporter Quality: Proposed Application Contracts

> Scope update: [workstreams.md](workstreams.md) owns current delivery. The
> disposable-database simulator comes first; workspace storage, in-app comparison
> and adoption contracts below are deferred future design options, not simulator
> prerequisites. Evidence and continuity requirements remain relevant.

These are acceptance requirements for discussion. Exact schemas and routes belong
to each implementation milestone.

## Evidence invariants

- Execution success and evidence outcome are distinct. Found, not found, partial,
  unavailable and invalid evidence have explicit meanings.
- Source handles resolve to the generation's tool call, frozen snapshot, selected
  fields, subject, season and coverage. Unknown handles or absent results cannot
  verify facts. Durable bindings survive conversation completion.
- Trades retain the selected franchise's sent/received assets, pick year and
  original ownership. Interpretation agrees with net draft-capital direction.
- Change claims need comparable before/after observations. Transactions establish
  when/how only when available; final rosters cannot establish this alone.
- Numeric attribution binds value, subject, units, period and precision. Formatting
  is deterministic. Superlatives require a complete relevant population.
- Regular-season rank and playoff finish are separate. Championships require
  appropriate playoff evidence; memory is a research lead.
- Unplayed games create no ties, streaks or competitive ranks. Completed zero-score
  ties remain valid; unknown completion remains unknown.
- Missing historical evidence narrows or qualifies claims; it cannot imply a
  complete comparison. Interpretation and prediction are not saved as verified facts.

Draft audits pin article and brief revisions, checks, evidence, findings and
unresolved issues. Relevant edits invalidate the audit. Start with evaluation
diagnostics and enforce reliably tested deterministic checks; semantic review
flags unsupported implication without claiming to prove every sentence.

## Operator workflow

Expose distinct actions: generate with current inputs; repeat fixed inputs;
compare a declared configuration variant; start empty or resume a checkpoint.
Fixed-input execution cannot silently refresh facts, select newer memory, or
substitute current prompt definitions when recorded assets are unavailable.
Report an actionable input error instead. Actual fallback models and resolved
provider parameters remain visible when judging comparability.

The first comparison view includes articles, input differences, factual findings,
reader preference/rationale, turns/tokens/cost and memory proposal differences.
Link to existing execution/evidence detail rather than building another debugger.

Label memory activity proposed, committed to canonical memory, committed to
workspace, or discarded according to finalization. A successful save tool call
alone is a proposal. Show the actual output revision/checkpoint and memory diff.

## Workspace and campaign invariants

- Memory input is explicit: empty state, canonical revision, or checkpoint.
  Empty state is not disguised as the canonical base revision.
- Fixed-input variants do not advance each other's memory. Rolling steps consume
  exactly the preceding successful checkpoint.
- Successful steps atomically persist the selected article, validated complete
  checkpoint and campaign advancement. Retries have at-most-once effects.
- Failed/cancelled steps retain inspectable attempts and leave memory unchanged.
  Resume skips committed steps. Pause prevents the next step starting.
- Per-step coverage and reconstruction limits are recorded. Future domain weeks
  and later memory cannot leak through SQL, curated tools, recall, references or
  initial context.
- Campaign settings include coverage, input policy, model settings, bounded
  generation execution and stopping budgets. Unknown pricing cannot count as zero
  when enforcing a monetary ceiling.
- Adoption validates scope, evidence, reference remapping and canonical-head
  concurrency. Initial adoption requires empty canonical state; concurrent changes
  reject it atomically. Nonempty import/rebuild is a separate design decision.
- Reset/discard leaves canonical history and prior article artifacts intact.

## Continuity acceptance

1. Recall and update the same item using a returned handle. Exactly resolve a
   low-ranked item among 250 memories without duplication.
2. Preserve origin, linked arcs, counterevidence and resolution across updates.
3. Keep a quiet unresolved arc, revisit when due/relevant, and record its review
   without requiring an article mention.
4. Select due callbacks despite many future/inapplicable candidates. Distinguish
   review due from condition satisfied.
5. Resolve or correct after payoff/contradiction and retain the reason.
6. Connect a renamed franchise to a relevant prior-season arc and both seasons'
   factual evidence; omit irrelevant historical arcs.
7. Bound card context while retaining origin, latest development and payoff;
   prevent duplicate arcs and unbounded trigger accumulation.

Measure eligible, retrieved/presented, used in article, reviewed and committed
memory separately. Raw mention frequency is not a continuity score.

## Verification and transition

| Layer | Required evidence |
| --- | --- |
| Data/adapters | Six recorded failure classes; valid zero-score tie; renamed identity; private metadata excluded and caveats visible |
| Reporter | Source validation, revision-bound audit, conflicting mutations, cancellation and exact recording |
| Memory/resources | Exact lookup beyond 100 items, checkpoint retrieval parity, temporal isolation, atomic rollback and adoption conflict |
| Frontend | Correct rerun labels, input comparison, proposed/committed memory, failed/resumable campaigns |
| Behavioral evaluation | Repeated real generations, evidence-reviewed claims, blind reader preference, relevant continuity and cost/variance |
| Longitudinal gate | Four-checkpoint pilot, full season, next-season preview, inspected memory trajectory and seed report |

Scripted completions prove mechanics, not model behavior. Full-season runs do not
replace focused regressions. Run affected tests only. Paid behavioral runs and
season campaigns are separate explicit execution work, not this planning review.

Preserve historical generations/manifests. Version new evidence/input/workspace
contracts and use forward-only migrations. Do not retroactively label old brief
facts verified or old proposals committed without provenance.

Settle storage/reference remapping before workspace implementation, observation
coverage before faithful replay, destination policy before adoption, and reliable
blocking checks before enforcing audit gates. Simultaneous branches, nonempty
canonical rebuilds and semantic automatic publishing gates remain deferred.
