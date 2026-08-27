
# Reporter Research Pipeline Design

**Status:** M1 implementation in progress

## Purpose

Restore deep, evidence-backed reporter research without reintroducing a rigid phase
machine. The work is deliberately split so the structured research substrate can
ship and be evaluated before a separate model is trusted to curate persistent
memory.

## Scope

This design owns the backend reporter's research state, research-facing tools,
article artifact boundary, and the future handoff from a completed generation to
memory curation. It refines the broader contracts in
[`../generation/README.md`](../generation/README.md) and
[`../memory/README.md`](../memory/README.md).

It does not change the datalayer, generation job lifecycle, or the legacy
`reporter_v2` package.

## Documents

| Document | Owns |
| --- | --- |
| [`architecture.md`](architecture.md) | Component boundaries, dependencies, lifecycle, and failure behavior |
| [`application-contracts.md`](application-contracts.md) | Structured brief, tools, invariants, errors, and acceptance coverage |

## Delivery Sequence

1. **Baseline prompt PR:** make procedures optional reference playbooks and allow
   research, drafting, verification, and storyline mining to interleave. This is
   the base for the implementation milestones, not M1 itself.
2. **M1 — structured research brief:** restore a runtime-owned, typed brief and
   specialized brief tools. Keep generic Markdown artifacts for the publishable
   article and expose the brief as a deterministic read-only projection for
   observability.
3. **M1 evaluation gate:** ship and test representative live runs across article
   types and supported models. Compare research depth, factual coverage, article
   accuracy, turn cost, and storyline coverage with the prompt-only baseline.
4. **M2 — memory curation pass:** only after the M1 gate is accepted, add a
   separate model pass that converts the verified brief and selected article into
   typed memory proposals.

The M1 evaluation surface restores the legacy reporter's semantic memory-tool
baseline and successful-submit brief bridge on top of the current typed buffer.
This is not the separate M2 curation pass.

## Settled Direction

- Flexible orchestration and structured research are complementary. Prompts decide
  what to investigate next; typed tools preserve what has been verified.
- The structured brief is the source of truth for research state. Generic artifact
  text must never be parsed back into authoritative facts.
- `research_brief.md` is a runtime-rendered projection. Generic artifact tools
  cannot create, edit, delete, submit, or replace it.
- The article remains a generic Markdown artifact so the writer retains freedom
  over form, tone, and revision strategy.
- M1 does not introduce a second model call or change persistent-memory
  finalization. Existing memory behavior remains available while research quality
  is evaluated independently.
- M2 consumes a bounded, typed curation packet. It produces proposals for the
  existing deterministic validator/finalizer and never writes memory directly.
- Reporter memory search remains available during research; curation is not a
  substitute for loading relevant historical context.
- Recaps and other storyline-oriented requests test current developments against
  pinned memory with a targeted search once current evidence supplies concrete
  team, player, transaction, matchup, or stakes hooks. Purely narrow factual
  requests may skip that continuity check.
- Memory retrieval exposes structured discovery keys and a lexical web-search
  field. The lexical field is not semantic search: one focused concept or explicit
  alternative set belongs in each query, while kind, status, and exact week are
  narrowing filters.
- Style and bias are initialized from `ReportConfig` and remain immutable within
  the brief; the agent does not spend turns restating them.
- Submission requires at least one verified fact. Storyline, callback, and outline
  readiness remain visible diagnostics rather than rigid workflow gates.
- Model-facing memory tools describe editorial intent. Typed create/replace
  operations and optimistic revision checks remain internal to the adapter.
- After a successful live submission, supporting facts for every final brief
  storyline are buffered automatically; unreferenced brief facts stay run-local.
  The bridge does not create or update durable storyline cards.
- Backtests preserve the legacy read-only behavior: memory reads remain available,
  while write tools and the successful-submit bridge do not buffer mutations.

## Non-Goals

- Implementing M1 or M2 in the baseline prompt PR.
- Reconstructing structured facts by parsing Markdown or model prose.
- Treating the entire raw tool-call transcript as the curator's primary input.
- Replacing frozen league-data reads, the generation service lifecycle, or the
  existing memory store.
- Forcing a fixed research → storyline → draft → verification procedure sequence.
- Migrating or modifying the legacy `reporter_v2` implementation.

## Open Questions

The following are deliberately deferred until the M1 evaluation gate. They do not
block M1, but must be settled before M2 implementation starts:

- Whether curation runs synchronously before generation finalization or as a
  retryable follow-up job.
- The curator's retry, timeout, and partial-failure contract.
- The exact canonical receipt/source-reference shape passed from M1 to M2.
- Whether writer-facing direct memory-proposal tools remain as a fallback after M2
  proves reliable.
