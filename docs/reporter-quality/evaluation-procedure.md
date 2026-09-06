# Backend reporter evaluation

## Establish the case

Read repository instructions, then inspect Git status, worktrees and open PR heads.
The backend under review may be an unmerged stack. Use its isolated checkout;
never edit a frozen runtime. Reconcile local `.context/reporter-quality/status.md`,
`implementation-plan.md`, `log.md` and their evidence links with current code.
Handoffs provide direction and historical context, not proof of current behavior.
Record changing heads, run IDs, targets and evidence links in a task-owned ignored
context directory, not in skills. If context is absent in a fresh checkout, locate
the coordinating worktree read-only; report missing evidence instead of inventing it.

The current backend route is `DatabaseCampaignBackend.submit/execute` →
`build_generation_dependencies` → `GenerationService` → backend reporter runner
and atomic finalization. See [backend adapter](../../backend/season_simulation/backend.py)
and [generation service](../../backend/services/generations/service.py).
Legacy `reporter-v2`, `sleeperdl` article workflows and hand-authored memory updates
do not exercise this product. For execution, read [campaign operations](campaign-operations.md).

Define the question before generation: selected-week quality, a declared variant,
retrieval relevance or longitudinal continuity. Pin request text, primary/actual
models and fallbacks, resolved report/runner settings, prompts/procedures, code,
installed dependencies, source observation membership, snapshot hashes, editorial
cutoffs and input memory revision/hash. Keep retrieval configuration and index
coverage visible. Identical inputs do not make provider output deterministic.

Matched comparisons keep requests and settings equal except the declared variant;
do not rotate tone or silently change focus. Compare raw observation membership
and input revisions, not only snapshot UUIDs: separately materialized snapshots
may have different identities. If derivations change, retain the no-fetch rebuild
audit and declare it. Each independent candidate begins at an equivalent empty
root or explicitly matched revision; rolling chains may then diverge as an outcome.
Retrospective sources remain retrospective: a Friday editorial cutoff does not
make later-fetched roster state contemporaneous historical knowledge.

## Inspect an evidence bundle

Resolve `exports/latest.json` once to a concrete immutable export and verify it.
Use `season-index.json` to select the submitted article version and input/output
memory heads. In `tables/`, inspect `reporting.generations.json` for request/settings
and input manifest, `reporting.artifact_versions.json` for briefs and revisions,
`reporting.tool_calls.json` for arguments/results/metadata/errors, and
`reporting.ai_calls.json` for model traces. Decode JSON-string results where needed.
Trace handles back to executed calls and their frozen snapshot; generated articles
and saved summaries are claims being assessed, never factual authorities.

Read relevant `memory.*.json` rows at both pins: items, versions, revisions,
subjects, events, facts, context notes and triggers. Distinguish buffered proposals
from committed versions. A successful quiet closeout can retain its input head;
failed generations must not advance it. Use frozen `data/` snapshots read-only to
check actual source values and coverage. Keep private full traces and negative
examples; do not copy large generated artifacts into tracked docs.

Separate these four assessments:

| Assessment | Evidence and decision |
| --- | --- |
| Deterministic correctness | Targeted tests, snapshot/pin integrity, source validation, commit/recovery behavior; does not certify prose |
| Retrieval relevance | Eligible memories versus returned rank/content, selected inspection, useful history, misses and distractors; distinguish absent written memory from failure to retrieve it |
| Article quality | Coherent angle, strong lead, readable structure suited to the request, useful specificity and coverage, factual accuracy, supported interpretation and meaningful continuity |
| Persisted memory quality | Actual identity/state/subject/evidence changes and useful future leads; correct persistence can still store an unsupported story |

Check movement direction and complete asset flow, including every participant in
multi-party trades, pick years/rounds/original owners, and drops versus additions.
Player score attribution needs team, period and lineup role. Distinguish H2H games
from bonus standings decisions, terminal regular-season records from playoff form,
and recorded bracket advancement from higher score. A transaction timestamp does
not establish manager motive or scoring payoff; bench totals alone do not prove
a legal better lineup or a bad pregame decision. Superlatives need the relevant
complete population. Bias affects framing, never numbers or source meaning.

Meaningful source validation rejects missing references, values and identities.
Article verification remains advisory: inspect whether correct evidence cards
actually led to correct prose. Do not substitute new prose regex gates for review.

## Discovery, continuity and callbacks

The discovery/inspection and callback-action behavior below belongs to the newer
implementation candidate. It is not supplied by this skills PR. Before evaluation,
verify the selected checkout contains those tools; if absent, assess its existing
recall behavior and record the unavailable capability instead of implying it ran.

The reporter automatically receives compact useful current context. Broader
discovery belongs to `search_memory`, with `inspect_memory` for selected detail,
history and evidence; see the [query/callback implementation PR](https://github.com/maxwn04/AIdamShefter-v2/pull/249)
and its `docs/reporter-quality/query-representation-contracts.md` in that candidate.
Inspect actual calls/results, not just tool availability or call counts.
Optional season/team/kind/status/week filters narrow discovery; stable
`franchise:<UUID>` selectors support renamed teams. Enforce competition scope,
reporting-week boundaries, pinned revisions, cross-season provenance and
read-only historical handles. Similarity is a lead, not current source proof.

Trace an arc from origin through developments to payoff, correction, quiet deferral
or abandonment. Preserve canonical storyline identity, prior state, relationships
and evidence on routine updates; intentional subject replacement is explicit.
Assess whether the new development actually bears on the old question. Do not
force article mentions, a fixed number of arcs or weekly rewrites of quiet stories.

Track eligible, presented, inspected, article-used, reviewed and committed outcomes
separately. `update_memory_callback` resolve/reschedule/defer operates on selected
handles. Defer means uninvestigated/open and creates no canonical mutation;
reschedule preserves origin and needs a future week. Neither parent resolution nor
mere exposure closes a callback. Completion does not require dispositions for
every due handle or a duplicate bookkeeping receipt.

## Sample acceptance and season review

The established revealing sample is chronological weeks 1, 2 and 15 from empty
memory, followed by a **fresh** full campaign covering weeks 1–17. In the sample,
week 15 sees week 2 memory; weeks 3–14 were not simulated. Honor explicitly
requested alternatives and league-specific coverage. Older design documents'
four-checkpoint/transition pilot is a proposal, not this accepted comparison gate.

Review every sample article, its executed sources and saved memory alongside the
matched retained baseline. The historical repair gate tested correct trade
direction, useful coverage, fewer repair loops and a same-storyline update. It
passed while material free-agent errors remained: that narrow acceptance was not
publication certification. The later accepted procedure broadens review to source,
article, retrieval and memory quality before a full season.

Record a practical **pass / hold** decision with evidence and rationale:

- Blocking: incomplete/uncertain generation, invalid inputs or revision chain,
  material factual or memory defects requiring a repair, or an unassessed material
  regression. Hold if the sample cannot support the intended full-season question.
- Advisory: style preferences, useful selective omissions, contextual limitations
  and efficiency observations that do not invalidate the question. A known factual
  defect is never relabeled stylistic; any deliberately retained limitation needs
  an explicit bounded acceptance rationale in the review.
- For each result, record claims checked and source locations, coverage/omissions,
  story quality, memory delta, retrieval misses/noise, callback outcomes, repairs,
  abandoned work, transport failures and completion. No arbitrary score, token
  ceiling, storyline count or mandatory search count defines acceptance.

If repair requires code/config changes, preserve the candidate and start a new
frozen candidate. Do not patch its completed articles to represent new output.
After acceptance, review individual weeks/checkpoints and final memory lineage,
including quiet intervals and actual follow-ups; a sample pass does not guarantee
the same outcome later. Tokens, bytes, latency and estimated cost are secondary;
reduce context only when it preserves or improves quality. Mark incomplete usage
and distinguish cost estimates from invoices.

## Retained negative cases

Find the retained comparisons through current context links (comparison update,
matched-input proof, weekly reviews, review sheets and final continuity audit).
Preserve these cases when evaluating later implementations:

- The short trade case reported Juwan movement correctly, but the full-season
  version reversed it; other free-agent drops were described as additions.
- A saved Taylor trade summary omitted draft capital; a valid three-party trade
  failed the earlier two-party event representation.
- Correct opposing-player totals were assigned to the wrong team; regular-season
  standings were treated as current playoff developments.
- A single canonical arc developed across 17 versions and ended with the champion,
  yet all 11 callbacks remained open. Several themes in one summary are not several
  independently persisted storylines. Zero explicit searches limited discovery.
- The retained semantic corpus comparison improved some paraphrases, but had
  Shakir ranking noise, a literal title miss and an unsaved-alias miss. Missing
  canonical facts or an unwritten rebuild arc cannot be recovered by indexing.

These are regression examples, not templates to imitate or assertions about a
new candidate. Retrieval-only improvements and passing tests do not establish
better generated articles or cross-season quality on a one-season corpus.
