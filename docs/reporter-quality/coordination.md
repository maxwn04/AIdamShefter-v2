# Parallel Implementation Contracts

## Scope and ownership

Implement two independently reviewable workstreams over the same baseline.
Production edits belong in `backend/`, `frontend/`, and top-level `docs/`;
legacy packages are excluded. Mutable plans/logs are ignored local context.

| Surface | Owner |
| --- | --- |
| Season driver, prepared execution policy, exports and replay manifests | Season simulation |
| `services/generations/` and related generation/API/worker composition seams | Season simulation |
| `services/memory/generation_context.py` temporal context | Season simulation |
| `services/reporter/runner/tools/memory_recall.py` editorial clock only | Season simulation |
| Frozen curated query identity, snapshot completion derivations | Evidence and grounding |
| Reporter evidence catalog, tools, brief, checks, prompts, definition and runner wiring | Evidence and grounding |
| New `docs/season-simulation/` contracts and operator instructions | Season simulation |
| New `docs/reporter-evidence-grounding/` contracts | Evidence and grounding |
| Cross-stream plan and integration assessment | Coordinator |

New tests follow corresponding ownership. Communicate before editing another
owner's files; general reporter-loop cleanup and memory-lifecycle redesign are
outside this delivery. Simulation must call normal reporter execution and must
not depend on the evidence implementation. Evidence must not redefine generation
input/finalization policy. Needed prepared snapshot selection is simulation-owned;
changes to shared datalayer contracts require coordination with the query owner.

## Temporal seam

Keep real execution/observation/knowledge timestamps honest. Introduce an explicit
simulated editorial boundary for replay callbacks without globally replacing the
clock. Date-based callback applicability may use that boundary; ordinary runs
retain existing behavior. Historical observations fetched later remain labeled
retrospective, and future domain weeks must remain inaccessible.

## Evidence seam

Use the existing result/metadata envelope and invocation-local recording. A small
run-local catalog resolves usable handles to scoped executed evidence. Handle
assignment must not depend on concurrent completion order. The catalog remains
usable in recorder-free tests; durable call identity is a private binding when
available. Preserve meaningful period, perspective, completeness and limitations
in model-visible results. Do not add a universal fact ontology.

## Verification and release boundaries

- Use bounded deterministic and integration tests with fake/scripted completions;
  no paid generations are required for implementation verification.
- Test only changed behavior and affected neighboring contracts, not the full suite.
- Database tests use new task-specific disposable targets, never an existing app
  database. Check local port availability and use unique container/volume names.
  Outputs and snapshot assets live in each task's own ignored workspace.
- A simulator release must provide an executable preparation/dry-run path, serial
  execution, durable resume reconciliation, frozen input/code/config checks,
  exported evidence/memory/assets, and a concrete first-baseline runbook.
- Grounding release tests exercise real query-to-presentation-to-claim bindings,
  not just manually constructed facts. Preserve valid zero-score ties, reject
  unsupported comparisons, and keep semantic verification diagnostic initially.
- Historical artifact compatibility and normal non-simulation generation behavior
  remain tested at the affected seams.
- Commits are reviewable units with exact test evidence. Neither task pushes,
  merges into main, resets an existing database, or launches paid articles.

Full-season factual/editorial improvement remains an operator-run behavioral
evaluation after implementation. Code-test success must not be described as a
completed paid season baseline or proof of arbitrary prose truth.
