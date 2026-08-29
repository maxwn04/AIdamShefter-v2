
# Reporter Memory Recall and Closeout Refactor Architecture

## Context and Goals

One reporter run owns research, drafting, verification, submission, and memory closeout. Memory retrieval returns concise semantic material to the reporter while canonical identity, revisions, ranking, and diagnostics remain application-only metadata. Due triggers and applicable context notes are placed in the reporter's starting context so their use does not depend on a voluntary search.

Article submission is a phase transition inside the same runner conversation. It freezes the selected artifact revision and gives the reporter a mandatory memory-closeout procedure. The reporter then uses the existing memory tools and completes the run with `complete_memory_review`.

## System Boundary

The refactor spans reporter tool execution and recording, memory presentation, generation-start recall, the post-submit closeout lifecycle, and the generation harness. It uses the existing canonical memory context and generation finalization path.

The tool registry is built once and remains stable for every model turn. Procedures guide the reporter but do not change tool availability. The canonical memory service remains responsible for scope, identity, revisions, evidence receipts, validation, and final mutation. The reporting subsystem records what the reporter received and what only the application knew, but does not become another memory store.

## Component Model

- **Generation-start recall** deterministically selects due triggers, scoped context notes, and a bounded set of likely relevant memories from generation scope and current canonical state.
- **`MemoryPresentationAdapter`** converts hydrated memory records into concise, kind-specific editorial context and produces a hidden binding map for the records it presented.
- **`ToolExecutionResult`** is the internal runner boundary containing the logical `result` returned to the reporter and application-only `metadata`.
- **Runner and generation recorder** serialize only `result` into the model conversation and persist `result`, `result_text`, and `metadata` as distinct tool-call fields.
- **Reporter agent** researches current league facts, uses recalled memory for continuity, owns the structured brief and final article, and selects durable memory during closeout.
- **`memory_closeout` procedure** tells the reporter how to review verified artifacts and save useful facts, events, storylines, triggers, and context notes without requiring any write.
- **`complete_memory_review` tool** explicitly records completion or no-op and terminates the runner after an article has been submitted.
- **Generation memory context** buffers semantic memory proposals throughout the run and supplies the existing finalization bundle.

## Data and Control Flow

1. Generation pins its Sleeper snapshot and current memory revision. Generation-start recall evaluates due triggers and selects scope-relevant context notes and bounded relevant memory.
2. The reporter receives that semantic prelude and may call memory search during research. Each tool result contains only editorially useful content; the saved tool call separately records hidden bindings and retrieval diagnostics.
3. The reporter builds the verified brief, drafts and verifies the article, then calls `submit_artifact`.
4. Successful submission freezes the selected artifact revision. Its tool result also supplies the mandatory `memory_closeout` procedure, and the runner continues with the same messages, model, tool schemas, and memory context.
5. The reporter reviews the finalized article and verified brief, searches memory when useful for reconciliation, and calls existing semantic memory tools for durable items. It may intentionally save nothing.
6. The reporter calls `complete_memory_review`. The runner terminates only after both article submission and memory-review completion.
7. Live generation finalization commits the submitted artifact and buffered memory proposals through the existing transaction. Backtest finalization receives no memory proposals because memory writes remain disabled.

The runner always sends the same ordered tool definitions to the model. It does not remove research, artifact, or memory tools during closeout. ArtifactStore immutability prevents edits to the submitted artifact. The automatic structured-brief fact bridge is removed after the closeout path satisfies its acceptance gate.

## Failure and Recovery Semantics

- Generation-start recall failures degrade to an explicit empty or partial prelude and are recorded; they do not fabricate context.
- Presentation failures fail that tool call because the exact model-visible result cannot be trusted.
- `result`, `result_text`, and `metadata` for a tool execution are recorded coherently under the same call identity.
- `complete_memory_review` returns an error before successful article submission and does not terminate the runner.
- A successful `submit_artifact` does not terminate the runner. The runner guarantees a bounded closeout opportunity even when submission consumes the normal writing-turn budget.
- If the reporter reaches the closeout limit without completing review, the run reports that explicit condition; it does not invent memory operations.
- Trigger state changes only through a valid buffered memory proposal. Merely recalling or mentioning a trigger does not fire or resolve it.
- Canonical revision conflicts continue to use the generation finalizer's existing failure behavior; this feature does not add a second retry or transaction layer.

## Observability

Every tool call records arguments, logical result, exact serialized result text, application-only metadata, status, timing, and any error. This makes it possible to reproduce what the reporter saw without leaking retrieval internals into its prompt.

Generation telemetry records the submission turn, closeout start and completion turns, whether closeout completed or was a no-op, and proposed memory counts by kind and operation.

The harness measures the complete memory funnel:

`available -> recalled -> reverified -> used in article -> saved during closeout -> accepted -> recalled later`

Coverage is segmented by memory kind, generation mode, league, season, and week. This distinguishes a retrieval failure from a presentation failure, reporter non-use, closeout omission, canonical rejection, or later recall failure.

## Security and Privacy

Model context is scoped to the active league and season and contains only semantic fields needed for the current editorial task. Tool metadata is trusted application data and never accepted back from the model as authority. Secrets and provider credentials are excluded from both the result and metadata.

Hiding identifiers is a context-quality and trust-boundary improvement, not an authorization mechanism. League/season scoping, mutation validation, and revision checks remain mandatory server-side.

## Architecture Decisions

- **Semantic presentation model:** presentation DTOs are distinct from canonical records so storage evolution does not enlarge prompts.
- **Generic result split:** `ToolExecutionResult(result, metadata)` belongs at the runner boundary because any tool may need private execution detail.
- **Deterministic trigger evaluation:** due-ness is application behavior, not a prompt-following obligation.
- **Ambient context notes:** applicable notes enter the recall prelude automatically because they describe standing editorial context rather than optional search hits.
- **Same-agent closeout:** the reporter already owns the verified brief, article, and conversation context, so it performs memory selection without a second model workflow.
- **Stable tool surface:** tools remain available and ordered identically on every completion request, preserving provider cache behavior and valid conversation history.
- **Submission freezes content:** existing artifact immutability protects the article without a tool-permission layer.
- **Explicit completion:** `complete_memory_review` gives the runner a reliable terminal signal and permits a deliberate no-op.
- **One automatic write path:** after cutover, closeout replaces automatic brief-to-fact persistence.

## Deferred Decisions

- Initial recall budgets per memory kind.
- Whether closeout needs more than the initial bounded turn allowance.
- Whether measured closeout quality eventually warrants a separate curator workflow.
