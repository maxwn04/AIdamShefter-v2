
# Reporter Quality and Season Continuity

Use `aida-reporter-evaluation` for selected-week backend comparisons and
`aida-season-simulation` for sequential campaigns. Their shared
[evaluation procedure](evaluation-procedure.md) covers source/article/memory
assessment and the sample gate; [campaign operations](campaign-operations.md)
covers frozen preparation, semantic indexing, bounded execution and safe resume.
Current run identities, progress, authorizations and evidence links belong in
ignored `.context/reporter-quality/`, not these durable instructions.

**Historical implementation direction:** Parallel implementation accepted for
season simulation and combined evidence/grounding; the assessment below predates
the later memory/retrieval candidates. Verify current code and PR state before
using candidate-only procedures.

## Objective and scope

Produce articles readers want to finish: specific, interesting, evidence-backed
stories that develop across weeks and seasons. Optimize factual reliability and
editorial quality first; use latency, tokens, and cost as constraints. A completed
generation, a longer brief, or more recalled memories is not proof of quality.

Implementation scope is `backend/`, `frontend/`, and top-level `docs/`. This
proposal does not depend on the legacy reporter or datalayer packages.

## Assessment of the app

The foundation is useful: frozen multi-season snapshots, durable franchise
identity, pinned canonical memory, a structured brief, immutable article versions,
buffered memory writes, atomic finalization, and detailed execution telemetry.
Keep those boundaries and the flexible single-agent loop.

The main weaknesses sit between those components:

| Observation in current code | Consequence | Relevant source |
| --- | --- | --- |
| Brief facts validate nonempty source strings, not factual support; submission requires a fact to exist | A reversed trade can become a supposedly verified fact and survive drafting | [research_brief.py](../../backend/services/reporter/runner/research_brief.py), [artifact_tools.py](../../backend/services/reporter/runner/tools/artifact_tools.py) |
| Data handlers serialize whole query responses; memory already separates result and metadata | Raw internals and useful editorial context lack a consistent boundary | [datalayer_tools.py](../../backend/services/reporter/runner/tools/datalayer_tools.py), [models.py](../../backend/services/reporter/runner/models.py) |
| Semantic memory search and likely-relevant recall constrain matches to the current season | Historical factual data is available, but ordinary search cannot discover prior-season storylines | [memory_tools.py](../../backend/services/reporter/runner/tools/memory_tools.py), [memory_recall.py](../../backend/services/reporter/runner/tools/memory_recall.py) |
| Memory presentation hides stable agent keys, while update tools require an ID; lookup scans only 100 candidates | Recall-to-update is unreliable, and longer seasons can expose duplicate/unresolved items | [memory_presentation.py](../../backend/services/reporter/runner/tools/memory_presentation.py), [memory_tools.py](../../backend/services/reporter/runner/tools/memory_tools.py) |
| Rerun clones the request and reselects inputs; backtests do not evolve memory | Current controls do not support a reproducible A/B or a rolling season simulation | [service.py](../../backend/services/generations/service.py), [finalization.py](../../backend/services/generations/finalization.py) |
| Workspace schema exists without the application workflow; newer UI docs reopen its storage design | A simulator needs an explicit memory-isolation decision | [reporting models](../../backend/database/models/reporting/generations.py), [UI contracts](../ui/application-contracts.md#deferred-writable-simulation-and-promotion) |

The recorded multi-season follow-ups also document reversed trade direction,
unusable history-to-roster identifiers, missing before/after evidence, numeric
misattribution, inconsistent superlatives, and unplayed games counted as ties.
These are recorded observations, not freshly reproduced live-run results.

## Recommended workstreams

The current recommendation is three parallel workstreams. See
[the detailed breakdown](workstreams.md) for ownership, dependencies and gates.
This replaces the initial ordering that put an experimentation system ahead of
season simulation.

| Stream | Deliverable | Dependency |
| --- | --- | --- |
| S: Season simulation | Sequential ordinary generations in disposable local Docker, exported season baseline and memory trajectory | Existing snapshot/memory lifecycle; small prepared-input and editorial-time policy |
| E: Evidence interfaces | Correct historical lookup/completion semantics, concise results and a source catalog | Small shared evidence contract |
| G: Stronger grounding | Source-bound claims, deterministic critical checks and bounded draft verification | Same contract; integrate E's actual evidence before release |

Disposable database isolation removes the need for alternative memory workspaces
in the first simulator. Run an imperfect reporter to observe failure accumulation;
fixing it first would defeat the purpose of collecting the baseline. Review and
repair accumulated memory before adopting it as trusted continuity elsewhere.

S can proceed independently. E and G can develop concurrently against shared
fixtures, with integration ordered contract -> evidence producer -> grounding
consumer. Freeze baseline code, prompts, settings and factual inputs so changes
under development cannot alter later weeks of the same season run.

Memory identity/lifecycle repairs remain a bounded follow-up informed by the
baseline. Broader context/runner cleanup follows measured bottlenecks. Neither
should silently disappear into the grounding workstream.

## How to hill-climb

Use the full-season run as the primary longitudinal baseline, with focused regression cases for ordinary recap, transaction-led story,
renamed franchise preview, missing historical roster, preseason placeholders,
regular-season/playoff distinction, numeric/superlative comparisons, quiet-week
continuity, contradiction/payoff, and dense late-season memory. Include real
recorded failures and synthetic edge cases. Keep a few cases held out from prompt
tuning; add failures to the corpus as they occur.

For each substantive variant:

1. Pin identical factual and memory inputs, request, and relevant settings.
2. Change one explainable dimension: prompt, tool presentation, retrieval, loop,
   or model configuration. Record actual provider/fallbacks and resolved reasoning
   settings; model name alone is not a controlled variable.
3. Run deterministic contract checks first, then inspect article claims and
   blind A/B editorial preference. An optional model judge can triage with source
   evidence, but cannot define truth or replace reader review.
4. Repeat promising comparisons to expose model variation; record mixed results
   rather than declaring a winner from one article.
5. Compare the original full-season baseline with the changed reporter from the
   same source-only initial state. Use selected weeks or prefixes for quicker
   diagnosis. Later memory divergence is an outcome, not an input-control error.

Score factual errors by severity, supported-claim coverage, honest treatment of
missing data, callback correctness, useful story development, redundancy, and
readability. Track retrieval eligibility/presentation separately from article use.
Measure unsupported causal assertions explicitly: a transaction and subsequent
win do not establish that the transaction caused the win. Token count and cost
accompany this scorecard rather than collapsing it into one opaque quality score.

## Useful stories from real data

Add compact deterministic discovery only where the existing curated queries do
not provide it: standings movement and changed playoff stakes; schedule-adjusted
performance using league scoring comparisons; transaction asset direction and
subsequent observed contribution; roster changes with both endpoints established.
Every discovery includes its population, period, calculation, and limitations.

The writer selects meaningful stakes, tension, and payoff from those leads. It
must distinguish observation from interpretation and prediction. It should not
invent a manager's motive, a locker-room narrative, or a causal explanation to
make a statistical change sound like a story. Measure whether a feature improves
the articles before expanding the feature catalog.

## Architectural recommendations and open decisions

Use the disposable database as the initial simulation boundary and keep ordinary
canonical memory writes. Export the database and referenced artifacts before a
reset. A prepared-only generation policy and explicit simulated editorial time
should be small additions around existing execution, not a new reporter.

Serialized checkpoints versus revision-native branches is deferred until an
in-app non-disposable experimentation workflow is needed. No storage-branch
choice is required for the first season baseline. Likewise defer comparison UI,
automatic seed promotion, separate curator agents and broad loop rewrites.

Retrospective reconstruction remains distinct from historically faithful replay.
The first can expose longitudinal reporter behavior without claiming that all
facts were observable in real time. Useful 2026 adoption is separate from simply
exporting an evaluation run; existing memory continuity defects and unsupported
claims must be assessed before trusting the output.

## Documents

- [Coordination](coordination.md): implementation ownership and cross-stream contracts.
- [Workstreams](workstreams.md): current parallel delivery plan and integration contract.
- [Architecture](architecture.md): ownership, experiment isolation, continuity,
  temporal semantics, and cleanup boundaries.
- [Application contracts](application-contracts.md): proposed observable behavior,
  evidence invariants, evaluation gates, and failure handling.

Mutable task order, verification status, and work history live in the matching
gitignored `.context/reporter-quality/` workspace. Existing design docs remain
authoritative for implemented behavior; this proposal does not silently supersede
them.
