# Reporter Quality: Three Parallel Workstreams

**Status:** Implementation direction: season simulation and a combined evidence
interfaces/grounding workstream. Disposable-local-database isolation supersedes
the initial requirement for memory workspaces. Paid generations and resets of
existing databases remain separate operator-approved actions.

See [coordination contracts](coordination.md) for parallel ownership and release
verification. Interfaces and grounding share one implementation owner; their
internal development can overlap after the evidence contract is defined.

## Why this decomposition works

Full-season simulation is both an evaluation instrument and a product capability.
For the initial local workflow, an isolated disposable PostgreSQL database can
provide the isolation that the earlier proposal placed inside application memory.
Sequential ordinary live generations already pin the current canonical revision
and commit memory with the article atomically. Use those paths without building
alternative memory storage, promotion, branch merging or a comparison dashboard.

An imperfect reporter is a valid baseline: its duplicated memories, abandoned
arcs and accumulated factual errors are outcomes to observe. Grounding and memory
repair are not prerequisites to running it. They are prerequisites to treating
its accumulated narrative as a trusted seed elsewhere.

The three workstreams can develop together, but their dependency is asymmetric:
simulation is mostly independent; grounding consumes the evidence interfaces.
Agree a small source contract first, then implement producer and consumer against
the same fixtures. Full integration of grounding follows the interface landing.

## S — Disposable season simulation and evaluation

**Owns:** a backend command/controller around the normal generation service,
small explicit execution-input policy, local campaign/export manifest, operator
instructions and evaluation report. Use the existing frontend for inspection.

**First deliverable:** set up an isolated local database with one competition,
mapped seasons and source observations but empty reporter memory; run weekly
articles sequentially; retain every article, brief, tool trace, memory revision
and usage record. A short smoke test verifies mechanics, then the full season
becomes the main behavioral baseline.

### Implementation slices

1. Prepare the disposable target, source coverage and ordered week/request plan.
   Capture the source-only starting state for repeatable fresh campaigns. Verify
   reset targets explicitly; do not offer a broad delete-canonical-memory endpoint.
2. Execute one ordinary memory-writing generation per step, waiting for successful
   finalization before proceeding. Use stable campaign/step/generation identities.
   On uncertainty, inspect the persisted generation before retrying; do not double
   submit. Resume only against matching database state and campaign inputs.
3. Add the smallest explicit execution policy needed for prepared snapshot reuse
   and simulated editorial time. Existing LIVE behavior couples memory writes to
   refresh and wall-clock knowledge time. READINESS_ONLY is not prepared-only:
   missing scopes can still trigger preparation fetches. A frozen campaign must
   reuse validated prepared inputs or fail visibly when missing.
4. Export a season index, articles, briefs, complete evidence traces, per-week
   memory states/diffs or restorable database backup, usage and manifest to storage
   outside the disposable container. Include referenced frozen snapshot files;
   a database dump alone may not preserve external artifacts. Export before reset.
5. Read the season as a reader and inspect selected arcs from origin through
   payoff/abandonment. Record critical factual errors, unsupported interpretations,
   repetition, callback relevance, duplicate/stale memory and cost. The initial
   report can be Markdown/JSON with the existing UI; no ratings platform is needed.

Keep one code/prompt/tool/config version for the entire baseline. Parallel code
development must not change assets loaded by later weeks of the running campaign.
Use a frozen image/checkout and preserve its identity. Different campaigns should
start with the same source observations/mappings and empty-memory state; their
later memories are expected to diverge as a consequence of reporter behavior.

Retrospective facts may have been fetched after their historical week. Record
actual observation/execution time honestly, and distinguish it from the simulated
week-end editorial clock used for date-based callback eligibility. Do not make
later-observed facts appear historically observed merely by changing a timestamp.
Audit week- and date-based triggers; today-as-editorial-time can fire historical
callbacks prematurely. Both snapshot and memory reads must respect domain coverage.

**Exit gate:** full season completes or stops with an actionable failed step;
restart does not duplicate committed memory; a quiet week may legitimately produce
no new revision; exports survive container reset; no future-week results or
premature scheduled callbacks contaminate research. A subsequent campaign can
start from the same prepared source baseline without touching a retained database.

**Excluded initially:** hosted simulator UI, memory branches, serialized memory
workspaces, automated promotion/import, parallel generations within one season,
and perfect historical observation fidelity. Pause/resume is at generation
boundaries; hard mid-call spend enforcement is not promised.

## E — Correct and concise evidence interfaces

**Owns:** frozen curated queries/derivations, reporter data adapters, read-side
evidence catalog and focused contract tests. It does not own drafting policy.

### Implementation slices

1. Repair canonical history-to-roster lookup and completed-game semantics, including
   genuine completed zero-score ties. Keep exact historical name rules.
2. Apply existing `ToolExecutionResult(result, metadata)` to data tools. Return
   bounded facts, usable lookup/source handles, season/cutoff, subject, units,
   transaction perspective, completeness and limitations. Persist full evidence
   and internal identity/diagnostics outside model context. Offer drill-down.
3. Populate the shared evidence catalog with actual executed results, separating
   successful execution from found/partial/unavailable evidence. Normalize trade
   direction and typed numeric fields for grounding consumers.

**Exit gate:** renamed-franchise history drills into both seasons without guessed
names or SQL; unplayed games do not create standings outcomes; visible handles
resolve to precise evidence; presentation removes internal noise while preserving
interpretive warnings and referenceability.

These changes have strong mechanical justification, but aggressive field removal
is not automatically beneficial. Compare omitted context against task needs and
measure failed drill-downs, factual errors and result size together.

## G — Stronger grounding in research and writing

**Owns:** structured brief claims, evidence validation, research/verification
instructions and bounded revision-aware draft checks. It consumes the catalog
through a narrow read interface, independently of how data queries are implemented.

### Implementation slices

1. Build regression cases from the recorded trade reversal, numeric attribution,
   superlative, missing-before/after and playoff-evidence failures. Use shared
   fixture catalog entries while E's real adapter is being implemented.
2. Bind claims to real source handles and reject nonexistent/not-found support.
   Preserve subject, value, period, trade side and claim category. Check the
   deterministic relationships for values/direction/comparison scope. A valid
   handle proves traceability, not that arbitrary prose is entailed by the source.
3. Strengthen targeted verification: compare both sides of claimed changes,
   distinguish historical/current observation from interpretation/prediction,
   and narrow claims when evidence is unavailable. Keep checks close to current
   brief and submission behavior; avoid a large generic claim ontology.
4. Add bounded draft checking tied to actual article/brief revisions. Detect
   unsupported material claims in the actual draft, not only those the writer
   voluntarily lists. Start uncertain semantic checks as diagnostics and evaluate
   a correction pass before adding unconditional extra model calls or hard gates.

**Exit gate:** deterministic critical cases fail with actionable repair guidance;
editing the draft invalidates applicable checks; ordinary supported articles can
still complete; the combined season run reduces factual failures without making
writing mechanical or encouraging omission of every interesting interpretation.

This stream is less certain than interface repair. A generic validator cannot
prove arbitrary prose; excessive gates can increase loops, cost and blandness.
Make a small high-confidence first release and inspect its season-level effects.

## Shared contract and integration

Agree this conceptual contract before E and G diverge; it does not require a new
database framework or exposing database UUIDs to the writer:

| Element | Required meaning |
| --- | --- |
| Source handle | Run-local, unambiguous and resolvable to durable tool execution evidence |
| Scope | Snapshot, season, domain cutoff/period, subject identity and perspective |
| Outcome | Found/partial/not found/unavailable, completeness and visible limitations |
| Selected evidence | Typed values/units/assets or a bounded selected record, with source field provenance |
| Catalog read | Grounding can resolve support or receive a typed missing/invalid result |

E owns catalog production/presentation; G owns claim-to-evidence validation. Assign
one owner to small shared runner context/wiring edits and merge that contract
first. S owns generation execution input policy, not the reporter tool internals.
Schema/protocol changes are versioned so saved baselines remain interpretable.

```text
S: simulator scaffold -> smoke -> frozen original-code season baseline -----+
                                                                          |
Shared evidence contract -> E: queries + presentation + real catalog ------+-> combined season run
                         -> G: fixture-backed checks -> integrate E -------+
```

Parallel development does not mean executing historical weeks concurrently or
changing the reporter halfway through one baseline. Merge independent query fixes
as ready; compare a frozen baseline with a frozen combined candidate. This measures
the package's effect. If attribution matters, rerun a revealing week/prefix on
an exported prior state or do an extra campaign with one stream toggled; a general
experimentation product is unnecessary.

## Memory continuity remains explicit follow-up work

Grounding prevents unsupported memory but does not fix inability to update a
recalled item, top-100 identity lookup, erased storyline fields, or current-season
search restrictions. Keep these as a separate bounded continuity follow-up after
the first baseline, or add an owner later. Do not hide them inside G or make S
wait for them. Initial 2026 seeding may fail to produce useful callbacks until
those issues are addressed; the baseline should expose that outcome.

Use a short local smoke test and targeted regressions alongside the full-season
baseline. A season is an excellent longitudinal test but may never contain a
legitimate zero-score tie or the exact renamed-team failure. Keep those focused
fixtures without building an elaborate evaluation service.
