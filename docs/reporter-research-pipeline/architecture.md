# Reporter Research Pipeline Architecture

## Context and Goals

The current reporter exposes generic path-addressed Markdown artifacts for both
research and finished writing. That maximizes flexibility, but it also makes
research completeness, evidence relationships, and storyline extraction optional
properties of prose. Prompt-driven procedure calls can improve behavior, but they
cannot provide durable structure or deterministic validation.

The target keeps one adaptive agent loop while separating three kinds of state:

1. frozen league data and reporter-memory context used as evidence;
2. a typed, runtime-owned research brief used as verified working state; and
3. generic Markdown article artifacts used for authored output.

M2 later adds a separate memory curator, but only after the M1 research substrate
has been evaluated in live runs.

## System Boundary

### Reporter runner

Owns orchestration, model/tool turns, the structured brief, generic article
artifacts, and final submission. It may interleave research, storyline mining,
drafting, and verification in any order.

### Frozen league data

Remains the authoritative per-run source for current league facts. Existing data
tools and guarded SQL remain unchanged.

### Reporter memory

Remains the authoritative source for historical narrative context and the target
for validated memory mutations. M1 does not change its schema or finalizer.

### Generation service

Continues to own run creation, persistence, lifecycle, and output selection. It
must not learn brief internals beyond the reporter's existing output contract.

### Forbidden coupling

- Generic artifact handlers must not mutate structured brief state.
- Brief state must not depend on parsing rendered Markdown.
- The future curator must not write the memory database directly.
- Procedure progress/logging must not become a phase gate for tool availability.

## Component Model

### `ResearchBriefStore` (M1)

Holds typed facts, callbacks, storylines, outline, style, bias, and readiness state
for one reporter run. It validates cross-references and assigns stable IDs.

### Brief tools (M1)

Expose narrow model actions such as saving a verified fact, connecting current and
historical facts, saving a storyline, setting an outline, and reading current
brief state. Tool handlers are the only model-facing mutation boundary.

### `ResearchBriefRenderer` (M1)

Deterministically renders current structured state to `research/brief.md`. The
projection is included in reporter output and logs for observability, but is not an
independent writable artifact.

### `ArtifactStore` (existing)

Continues to own generic Markdown artifacts, especially candidate and selected
articles. It reserves `research/brief.md` for the renderer.

### `MemoryCurator` (M2)

Receives a bounded typed packet containing the verified brief, selected article,
relevant pinned memory, and an evidence/receipt catalog. It returns typed memory
proposals for deterministic validation and finalization.

## Data and Control Flow

### Baseline prompt PR

The agent loads only the procedure playbooks relevant to its current uncertainty.
It may move directly among data tools, memory search, brief/artifact work, and
verification. Procedure state remains observability metadata, not a runner-enforced
workflow state machine.

### M1 generation

1. The generation service creates frozen league data and current reporter-memory
   context as it does today.
2. The runner creates an empty in-memory `ResearchBriefStore` and reserves the
   rendered brief path. It does not create an empty generic artifact that the
   model must load and read.
3. The agent explores data and memory adaptively. Verified findings are captured
   through brief tools at the point they become useful.
4. Every successful brief mutation validates references, updates readiness or
   staleness, renders the projection, and records the mutation in the research log.
5. The agent creates and revises one or more generic article artifacts. Drafting
   can begin before research is complete; new findings can update both brief and
   draft later.
6. Submission validates that a non-empty publishable article is selected and
   records brief readiness diagnostics. The reporter returns the article plus the
   rendered brief through its compatible output shape.
7. Existing generation-memory finalization behavior remains unchanged in M1.

The structured mutation and its rendered projection are one logical operation. A
projection failure fails the tool call and leaves neither side advanced.

### M2 curation

After the M1 evaluation gate is accepted, the completed run builds a typed curation
packet. The curator may mine storylines and other durable context from the verified
brief and article, but its output is only a proposal bundle. Existing deterministic
validation, idempotency, and finalization boundaries decide what is persisted.

The precise synchronous/asynchronous placement is intentionally deferred. Either
choice must preserve a successful article when curation fails.

## Failure and Recovery Semantics

### M1

- Invalid or missing brief references return a typed tool error and do not mutate
  state.
- Repeating an idempotent tool mutation must not duplicate the same logical item.
- A projection/render failure makes the originating brief mutation fail
  atomically.
- Generic artifact operations targeting the reserved brief path fail clearly.
- Missing brief readiness is visible at submission. The exact hard/soft submission
  policy is contract-tested rather than inferred from procedure order.
- Reporter failure and retry continue to follow the generation service's existing
  lifecycle.

### M2

- Curator failure cannot invalidate or discard an otherwise successful article.
- Curator output is untrusted until the existing validator accepts it.
- Retries must be idempotent by generation/run identity and proposal identity.
- Timeout and retry policy must be settled before M2 implementation.

## Observability

M1 records brief mutations and readiness alongside the existing research log. Live
evaluation should report at least:

- data, memory-search, brief-tool, artifact, and procedure call counts;
- number of verified facts, supported storylines, callbacks, and outline sections;
- unsupported-reference validation failures;
- turns to first useful fact, first storyline, first draft, and submission;
- factual-correction count during verification; and
- total turns, latency, and token usage.

M2 adds curator outcome, duration, proposal counts, validation rejections, retries,
and persisted mutation counts.

## Security and Privacy

All model output is untrusted at the tool boundary. Existing league/season scoping,
SQL guards, memory authorization, and data masking remain authoritative. The
curation packet contains only run-scoped data already available to the reporter;
it must not include secrets or unbounded internal logs.

## Architecture Decisions

- Use one adaptive writer/researcher loop rather than a runner-enforced phase
  machine.
- Restore typed research state instead of trying to solve missing structure with
  stronger prompt sequencing.
- Keep article artifacts generic and reserve the brief projection path.
- Evaluate M1 independently before adding M2 cost, latency, and failure modes.
- Give a future curator verified state and evidence metadata, not a transcript to
  rediscover the run from scratch.

## Open Questions

Only M2 placement, retries, receipt shape, and fallback writer-proposal behavior
remain open. They are owned by the M2 design checkpoint after M1 evaluation.
