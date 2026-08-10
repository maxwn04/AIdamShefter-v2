# Typed Memory and Retrieval Design

**Decision status:** Accepted

**Implementation status:** Database schema implemented in the current PR stack;
application contracts and retrieval services remain follow-up work

**Scope:** Canonical memory storage, application contracts, retrieval, and the
generation lifecycle

## Purpose

This directory records the detailed design behind the memory schema summarized
in [`docs/database/memory.md`](../database/memory.md). The database migration and
ORM models implement the canonical typed fields and search-document table. The
Pydantic contracts, mutation manager, search builders, and reporter tools are
specified here for the application stack that follows.

The redesign keeps the valuable parts of that baseline:

- one linear canonical revision history per competition;
- stable memory-item identities;
- immutable, item-local content versions;
- exact historical visibility through introduced and retired revisions;
- distinct storyline, fact, event, trigger, and context-note concepts.

It changes how a typed memory version owns participants and links. Instead of
using `version_entities` and `version_relationships` as generic canonical graph
tables, each typed version has an explicit application-level content contract.
A rebuildable search projection flattens those different contracts into one
uniform retrieval index.

## Design in One View

```mermaid
flowchart LR
    Revision["Pinned canonical revision"] --> Search["Search projection"]
    Search --> Candidate["Candidate version IDs"]
    Candidate --> Hydrate["Hydrate typed canonical versions"]
    Hydrate --> Agent["Reporter agent"]
    Agent --> Proposal["Typed memory mutation proposal"]
    Proposal --> Validate["Application validation"]
    Validate --> Next["Next canonical revision"]
    Next --> Project["Build new search documents"]
```

The canonical representation answers, “What exactly is this memory?” The search
projection answers, “Which memories may be relevant?” Search results are always
hydrated from canonical typed versions before they are returned to the agent.

## Settled Principles

1. **Typed versions are canonical.** A storyline, fact, event, trigger, or
   context note has a complete, kind-specific content shape.
2. **Stable items are identity envelopes.** Mutable content, participants, and
   links do not live on `memory_items`.
3. **Semantic validation belongs at the application boundary.** Pydantic models,
   typed resource managers, and the mutation service validate event shapes,
   roles, target kinds, competition scope, and evidence policy.
4. **PostgreSQL still protects mechanical history.** Primary keys, revision
   sequence uniqueness, item-version uniqueness, current-pointer concurrency,
   and atomic revision advancement remain database responsibilities.
5. **References express intent.** Evidence targets exact memory versions;
   thematic or operational relationships may target stable items.
6. **Retrieval is a derived projection.** Full-text, entity, relationship, and
   later vector search use persistent, rebuildable documents keyed by exact
   memory-version ID.
7. **Historical visibility is never derived from search alone.** Every search is
   filtered through the introduced/retired bounds of the generation's pinned
   canonical revision.

## Why This Direction

The generic association tables provide uniform reverse queries and strong
foreign keys, but their open-ended roles and relationship kinds do not describe
the legal shape of a storyline, fact, event, or trigger. That indirection makes
mutation behavior harder to understand and extend.

Putting all canonical memory into one generic JSON document would have the
opposite problem: easy storage but no clear kind-specific mutation contract.
This design separates the two concerns:

| Concern | Representation |
| --- | --- |
| Authoring, validation, and history | Kind-specific typed canonical versions |
| Cross-kind candidate discovery | Generic derived search documents |
| Full returned context | Hydrated typed canonical versions and exact references |

This preserves high-resolution event payloads, such as different trade and
matchup structures, while still supporting uniform queries such as “find active
storylines involving this franchise.”

## Documents

- [`canonical-schema.md`](canonical-schema.md) — canonical PostgreSQL model,
  version boundaries, and reference rules.
- [`application-contracts.md`](application-contracts.md) — Pydantic content
  models, validation ownership, and mutation APIs.
- [`retrieval.md`](retrieval.md) — persistent search documents, full-text search,
  vector search, filtering, and hydration.
- [`lifecycle.md`](lifecycle.md) — end-to-end generation, search, mutation, and
  projection-maintenance pipeline.
- [`transition.md`](transition.md) — concrete changes from the implemented
  baseline and recommended implementation order.

## Non-Goals

- Branching or merging canonical memory history.
- Making search documents a second source of truth.
- Exposing raw JSON or generic relationship bags directly to the reporter.
- Adding embeddings before exact filtering and full-text retrieval are working.
- Collapsing all memory kinds into one undifferentiated domain object.
