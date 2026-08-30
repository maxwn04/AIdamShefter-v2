
# Reporter Memory Recall and Closeout Refactor

**Status:** Proposed
**Feature key:** `reporter-memory-refactor`

## Purpose

Make reporter memory useful throughout article generation. The reporter receives concise semantic memory, automatically sees due callbacks and applicable context notes, and completes a mandatory memory-closeout procedure after submitting the article. Tool-call records preserve the exact result returned to the reporter while storing application-only metadata separately.

## Scope

- Redesign model-facing memory search inputs and results around editorial relevance.
- Introduce a generic tool execution result that separates `result` from `metadata`.
- Persist the logical result, its exact serialized model message, and application-only metadata as separate tool-call fields.
- Add an automatic recall prelude for due triggers and scoped context notes.
- Force the same reporter agent into a memory-closeout procedure after article submission.
- Retire automatic structured-brief fact persistence once closeout owns durable memory selection.
- Add harness measurements for recall, use, saving, and later reuse.

The canonical memory store remains responsible for identity, revisions, evidence receipts, and conflict detection. This feature changes how that state is presented and maintained, not the fundamental storage model.

## Documents

| Document | Owns |
| --- | --- |
| [`architecture.md`](architecture.md) | Component boundaries, generation and closeout flow, failures, and observability |
| [`application-contracts.md`](application-contracts.md) | Tool results, model-visible memory schemas, lifecycle, and acceptance coverage |

Related upstream contracts:

- [`../memory/application-contracts.md`](../memory/application-contracts.md)
- [`../memory/retrieval.md`](../memory/retrieval.md)
- [`../memory/lifecycle.md`](../memory/lifecycle.md)
- [`../reporter-research-pipeline/README.md`](../reporter-research-pipeline/README.md)
- [`../reporter-research-pipeline/application-contracts.md`](../reporter-research-pipeline/application-contracts.md)

## Settled Direction

- Model-facing memory payloads contain semantic editorial context only. They omit canonical IDs, version IDs, revision numbers, creation or recording timestamps, competition IDs, hashes, ranking scores, matched keys, and projection diagnostics.
- Handlers may return an internal `ToolExecutionResult(result, metadata)`. Only `result` is serialized into the model conversation. Plain handler return values remain supported and imply empty metadata.
- The saved `ToolCall` uses the first-class fields `arguments`, `result`, `result_text`, `metadata`, `status`, `duration_ms`, and `error`, alongside call identity and implementation fields. Tool-specific private details remain nested under `metadata`.
- Memory search accepts editorial filters such as text, teams, kinds, status, tags, temporal bounds, and limit. Canonical identifier filters are internal concerns and are removed from model-facing schemas.
- A deterministic application-owned recall prelude automatically supplies due triggers and scoped context notes before research begins. The model does not need to remember to discover them.
- The same reporter agent owns research, article writing, and memory closeout. Submission freezes the selected article revision and supplies the mandatory closeout procedure instead of terminating the runner.
- The tool list remains unchanged for the entire conversation. Procedures guide behavior; they do not grant or revoke tools.
- `complete_memory_review` terminates the run after the agent has saved useful memory or deliberately chosen a no-op.
- Submission grants six additional model turns for closeout. Exhausting them without explicit completion fails the generation and discards its buffered memory proposals.
- Live generation commits the closeout's buffered memory proposals through the existing generation finalization path. Backtests keep memory writes disabled.
- The automatic structured-brief fact bridge is retired once memory closeout is proven.

## Non-Goals

- Replacing the canonical memory database schema or revision model.
- Exposing raw search documents, vectors, or retrieval diagnostics to the writer.
- Asking models to manage database IDs, revisions, receipts, or transaction boundaries.
- Parsing Markdown articles to infer memory when a structured brief and generation artifacts already exist.
- Restoring legacy dual-write behavior.
- Dynamically changing the available tool list or adding a runner-level tool-permission system.
- Creating a separate curator model, curation packet, curation-attempt resource, or second generation service workflow.
- Allowing the closeout procedure to modify the finalized article.

## Deferred Decisions

- Whether evidence later justifies a separate curator rather than same-agent closeout.
- Whether embeddings materially improve retrieval after semantic presentation and recall coverage are fixed.
