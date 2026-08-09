# Canonical Memory Schema

**Status:** Implemented database design

## Responsibilities

Canonical memory stores exact identity, history, content, and provenance. It is
not optimized to provide one uniform query shape across all memory kinds; that is
the responsibility of the [retrieval projection](retrieval.md).

The model has three levels:

```text
memory revision    one competition-wide atomic state transition
memory item        one stable logical memory identity
memory version     one complete state of that item
```

## Revision Tables

### `memory.memory_revisions`

One immutable canonical mutation batch per competition:

- UUID primary key;
- competition ID;
- competition-local `sequence_number bigint`;
- previous revision ID;
- optional producing generation, season, week, and knowledge cutoff;
- deterministic resulting-state hash;
- database-generated creation time.

Sequence number, rather than UUID or timestamp, defines canonical order. Sequence
zero is the empty root. A generation that makes no accepted memory changes does
not create another revision.

### `memory.current_revisions`

One mutable pointer per competition:

- competition ID;
- current revision ID;
- lock version;
- update time.

The pointer is locked while accepting a live mutation. A generation may advance
canonical memory only if its pinned input revision is still current.

## Stable Identity

### `memory.memory_items`

The stable identity envelope remains intentionally small:

- UUID primary key;
- competition ID;
- kind: `storyline`, `fact`, `event`, `trigger`, or `context_note`;
- optional agent-facing key;
- creation time.

An item does not contain mutable text, participants, evidence, or relationships.
Those values can change over history and therefore belong to its versions.

### `memory.context_notes`

Context notes retain a small typed identity table:

- memory-item ID;
- scope: competition, competition season, or franchise;
- corresponding scope target;
- stable note key.

Scope and key identify a durable narrative slot. Narrative, outlook, status, and
tags remain versioned. Keeping this identity table is clearer than placing a
polymorphic `identity_config` JSON object on every memory item.

## Version Envelope

### `memory.memory_versions`

Every complete item version has:

- UUID primary key;
- memory-item and competition IDs;
- positive item-local revision number;
- introduced canonical revision ID;
- nullable retired canonical revision ID;
- optional season, week, and exact occurrence time;
- creating generation and optional tool call;
- optional change reason;
- database-recorded time;
- application content-schema version.

The content-schema version identifies the Pydantic/storage shape used to decode
an immutable version. It is separate from the item's revision number and the
competition-wide canonical sequence.

A version is visible at pinned canonical revision `R` when:

```text
introduced_sequence <= R.sequence_number
and
(retired_sequence is null or retired_sequence > R.sequence_number)
```

Changing any owned content, participants, or references creates a complete new
version and retires the prior visible version in the same canonical transaction.

## Typed Version Tables

The precise physical split between scalar columns and JSONB is an implementation
choice guided by query frequency. Frequently filtered intrinsic values remain
ordinary columns. Nested, kind-specific structures use Pydantic-backed JSONB.

### `memory.storyline_versions`

Canonical storyline content includes:

- headline, summary, status, arc type, salience, tags;
- optional callback and resolution text;
- typed `subjects`;
- exact evidence references to fact or event versions;
- thematic references to stable storyline items.

Evidence content is not copied into the storyline. The storyline owns typed
references that are hydrated separately.

### `memory.fact_versions`

Canonical fact content includes:

- claim, category, structured numbers, confidence, status;
- typed subjects;
- optional exact originating-event version references;
- exact reporting tool-call and Sleeper request receipts where available;
- non-authoritative source hints.

### `memory.event_versions`

Canonical event content includes:

- event type, headline, summary, salience, confidence, status;
- exact reporting/API receipts and optional source hints;
- event-type-discriminated `details` JSONB.

The payload permits high-resolution event shapes. A trade can require sender,
receiver, and transferred assets, while a matchup can require winner, loser, and
matchup identity. Adding a new event type adds a new application payload model
without weakening existing event contracts.

### `memory.trigger_versions`

Canonical trigger content includes:

- trigger type, status, fire policy, and target time/week;
- explicit stable target storyline item when applicable;
- optional stable origin event item;
- a trigger-type-discriminated condition;
- optional resolution reason.

Trigger targets use stable item IDs because an operational callback normally
follows the target storyline as it evolves. If product behavior later proves
that every trigger is inseparable from one storyline, triggers may be reconsidered
as storyline-owned components; that is not assumed here.

### `memory.context_note_versions`

Canonical context-note content includes narrative text, outlook, status, and
tags. Its scope and note key remain in `context_notes` because they define stable
identity rather than mutable content.

## Reference Policy

References use UUIDs without requiring every reference to be a database foreign
key. The application manager validates existence, target kind, competition
scope, duplicates, and same-batch references before committing.

Two reference modes are intentionally distinct:

| Meaning | Target |
| --- | --- |
| “This exact claim or receipt supports me” | Exact `memory_versions.id` |
| “I remain related to this evolving narrative object” | Stable `memory_items.id` |

This prevents a storyline's supporting evidence from silently changing when a
fact is corrected, while allowing a trigger or related storyline to follow a
stable item through later versions.

## Removed Canonical Graph Tables

The target design removes these as canonical write models:

- `memory.version_entities`;
- `memory.version_relationships`.

Their useful retrieval behavior is replaced by flattened, rebuildable search
documents. Participants and references do not have independent histories; they
are owned by the complete typed source version.

## Validation Boundary

PostgreSQL retains mechanical invariants:

- primary keys and required storage fields;
- unique competition revision sequence;
- unique item-local revision number;
- current-revision concurrency control;
- immutable revision/version history;
- atomic retirement, introduction, and pointer advancement.

Application models and the memory manager own semantic invariants:

- legal event and trigger payloads;
- participant and evidence roles;
- target existence, kind, and competition scope;
- evidence-reference policy;
- content-schema conversion;
- complete resulting-state validation.
