# Application Memory Contracts

**Status:** Typed v1 contracts implemented; resource managers pending

## Goal

Callers should know the complete legal shape of a mutation without understanding
ORM association rows. Routes, tools, services, and the reporter operate on typed
resource objects. Typed resource managers translate their own objects, while
the mutation service and revision manager coordinate an atomic bundle.

The shapes below describe the implemented v1 Pydantic contracts. Contract model
fields cannot be reassigned after validation, and unknown fields are rejected.

## Shared Reference Primitives

Entity references are discriminated unions:

```python
class FranchiseRef(BaseModel):
    kind: Literal["franchise"]
    id: UUID
    role: str
    display_name: str | None = None


class PlayerRef(BaseModel):
    kind: Literal["player"]
    id: str
    role: str
    display_name: str | None = None


EntityRef = Annotated[
    FranchiseRef | PlayerRef | SeasonRosterRef | SeasonRef | SleeperUserRef,
    Field(discriminator="kind"),
]
```

Each owning content type narrows the roles it accepts. A fact accepts `subject`,
while a storyline accepts `focus` and `counterparty`. Event-specific participant
meaning lives in its typed payload instead of a generic role bag. Sharing the
low-level reference primitive does not imply sharing generic semantic roles.

The initial storyline roles are `focus` and `counterparty`; the initial fact role
is `subject`. Franchise, player, season-roster, season, and Sleeper-user references
are legal for both resources. Empty subject lists remain legal for
competition-wide memory, but a non-empty storyline subject list must contain a
focus. Repeated targets are invalid even when their roles differ.

Human-readable strings are trimmed and must be nonblank. Tags are normalized to
case-folded, first-seen order; blank and repeated tags are removed. Complete
collection fields remain required even when their legal value is an empty list.

Evidence references identify exact immutable content:

```python
class EvidenceRef(BaseModel):
    kind: Literal["fact", "event"]
    version_id: UUID
    role: Literal["origin", "support", "update", "payoff"]
```

Thematic references identify stable items:

```python
class RelatedStorylineRef(BaseModel):
    item_id: UUID
    role: Literal["related_arc", "continuation", "counterpoint"]
```

## Typed Content

### Storyline

```python
class StorylineContent(BaseModel):
    schema_version: Literal[1]
    headline: str
    summary: str
    status: StorylineStatus
    arc_type: str | None = None
    salience: int
    tags: list[str]
    subjects: list[StorylineEntityRef]
    evidence: list[EvidenceRef]
    related_storylines: list[RelatedStorylineRef]
    callback_condition: str | None = None
    resolution_summary: str | None = None
```

### Fact

```python
class FactContent(BaseModel):
    schema_version: Literal[1]
    claim: str
    category: str
    numbers: dict[str, JsonValue]
    confidence: FactConfidence
    status: FactStatus
    subjects: list[FactEntityRef]
    originating_event_version_ids: list[UUID]
    primary_tool_call_id: UUID | None = None
    primary_api_request_id: UUID | None = None
    source_hints: dict[str, JsonValue] | None = None
```

An originating event is optional context; the fact remains a claim with its own
receipts. It does not contain another event payload.

Fact confidence is `unverified`, `inferred`, or `source_backed`; status is
`active`, `superseded`, `rejected`, or `archived`. A source-backed fact requires
at least one typed primary tool-call or API-request receipt. Source hints are
JSON-valued mappings and cannot independently establish source-backed confidence.

### Event

```python
class TradeEventPayload(BaseModel):
    kind: Literal["trade"]
    sender_franchise_id: UUID
    receiver_franchise_id: UUID
    assets: list[TradeAsset]


class MatchupEventPayload(BaseModel):
    kind: Literal["matchup"]
    winner_franchise_id: UUID
    loser_franchise_id: UUID
    sleeper_matchup_id: str


EventPayload = Annotated[
    TradeEventPayload | MatchupEventPayload,
    Field(discriminator="kind"),
]


class EventContent(BaseModel):
    schema_version: Literal[1]
    event_type: EventType
    headline: str
    summary: str
    salience: int
    confidence: EventConfidence
    status: EventStatus
    details: EventPayload
    primary_tool_call_id: UUID | None = None
    primary_api_request_id: UUID | None = None
    source_hints: dict[str, JsonValue] | None = None
```

`details` describes this event. It is not a collection of related events. The
declared event type and discriminated payload must agree.

The initial event union contains only `trade` and `matchup`. Event confidence and
status use the same values and typed-receipt rule as facts. Trade assets form a
second discriminated union over players, normalized draft picks, and budget.
Every asset states `sender_to_receiver` or `receiver_to_sender`, making bilateral
trades unambiguous. A trade requires distinct franchises and at least one unique
asset; a matchup requires distinct winner and loser franchises and a nonblank
Sleeper matchup ID.

### Trigger

```python
class TriggerContent(BaseModel):
    schema_version: Literal[1]
    trigger_type: TriggerType
    status: TriggerStatus
    fire_policy: FirePolicy
    target_competition_season_id: UUID | None = None
    target_storyline_item_id: UUID | None = None
    origin_event_item_id: UUID | None = None
    target_week: int | None = None
    target_at: datetime | None = None
    condition: TriggerCondition
    resolution_reason: str | None = None
```

Initial trigger types and conditions are:

- `rematch`, with exactly two distinct franchise IDs; it requires a target
  competition season and week;
- `trade_evaluation`, whose stable origin event supplies the trade details; it
  requires that origin event plus either a target week or target time.

The condition discriminator must agree with `trigger_type`. Trigger status is
`open`, `fired`, `satisfied`, `expired`, or `archived`; fire policy is `one_shot`,
`recurring`, or `until_resolved`. Target times must be timezone-aware.

### Context note

```python
class ContextNoteContent(BaseModel):
    schema_version: Literal[1]
    narrative: str
    outlook: str | None = None
    status: ContextNoteStatus
    tags: list[str]
```

The note's scope and key are loaded from its stable typed identity.

Context-note status is initially `active` or `archived`. Its identity is a
discriminated union for competition, competition-season, and franchise scopes,
so impossible mixed scope/target shapes cannot be constructed.

## Manager Context and Hydrated Resources

Every manager receives an immutable, already-resolved `ManagerContext` with a
discriminated local-user, system-process, or generation actor; an explicit
competition or global resource scope; and a required correlation ID. Memory
managers accept only competition scope. Global scope requires a nonblank reason.
Generation cutoffs and pinned memory revisions remain explicit workflow inputs,
not authorization context.

Hydration returns one generic `VersionedMemory[Content]` envelope containing the
stable memory-item identity, immutable version metadata, and the resource's typed
content. The envelope validates item kind and stored content-schema version.
History is a sequence of the same complete envelopes rather than a second shallow
history DTO. Context notes add their stable typed scope/key identity to this
aggregate.

## Mutation Contract

Public canonical mutations are service operations that create or replace
complete typed content:

```python
create_storyline(content: StorylineContent, ...)

replace_storyline(
    item_id: UUID,
    expected_item_revision: int,
    content: StorylineContent,
    ...,
)
```

A patch-oriented UI may edit individual fields locally, but
`MemoryMutationService` accepts one complete replacement, resolves its
bundle-local semantics, and hands the accepted unit of work to
`RevisionManager`. This prevents a caller from accidentally creating a partial
version whose omitted relationships have ambiguous meaning.

Typed resource managers do not expose standalone create or replace methods.
They own scoped reads, codecs, resource validation, and package-internal SQL for
their rows. `MemoryMutationService` owns the business decision that a single
proposal or completed proposal bundle is one atomic mutation;
`RevisionManager` owns the enclosed SQLAlchemy transaction, revision locking,
state hashing, pointer advancement, and commit or rollback. The service and its
callers never receive a session or ORM row.

### Generation-scoped proposal contract

Reporter-facing `save_*` operations do not invoke these public mutations one at
a time. `GenerationService` creates one `GenerationMemoryContext` after pinning
the generation's canonical input revision. The context exposes retrieval at
that revision and buffers complete typed proposals:

```python
context.propose_fact(content: FactContent)
context.propose_event(content: EventContent)
context.propose_storyline(content: StorylineContent)
context.propose_trigger(content: TriggerContent)
context.propose_context_note(identity: ContextNoteIdentity, content: ContextNoteContent)
```

The context is an in-memory, generation-scoped facade rather than a manager or
database unit of work. It contains no open session. Proposal-local references
allow a later proposal to target another item or version created in the same
bundle.

Searches through the context always use its immutable pinned canonical revision.
They do not hydrate buffered proposals or treat them as established memory. On
successful article submission, `GenerationService` hands the completed bundle
to `MemoryMutationService` once. On failure or abandonment, it discards the
buffer without creating a canonical revision.

Before opening the canonical write transaction, the service performs all model
or external work, validates pure typed-content rules, resolves proposal-local
references, and fixes the accepted mutation unit. It then hands that unit to
`RevisionManager`. Inside the short transaction, the revision manager invokes
resource-package basic SQL helpers to:

1. load database-backed reference targets in scoped batches;
2. validate their expected kinds and competition scope;
3. write complete typed rows and search projections.

Within that same transaction, `RevisionManager` itself locks and verifies the
canonical parent, persists generic revision/item/version envelopes, hashes the
resulting state, and advances the canonical pointer atomically.

Failures return typed application errors such as target-not-found,
wrong-target-kind, cross-competition-reference, stale-item-version, or
stale-canonical-revision. Callers do not interpret database constraint names.

## Schema Evolution

Immutable old content must remain decodable after application models evolve.
Every kind therefore has an explicit content-schema version and deterministic
conversion functions:

```text
stored v1 -> current resource object
stored v2 -> current resource object
```

Adding an optional field may not require stored-data rewriting. A breaking shape
change adds a new schema version and converter. Rebuilding a search projection
does not create a new memory version because it does not change canonical
meaning.

## Hydration Contract

Retrieval returns candidate version IDs and scores. The manager then:

1. loads the visible `memory_version` and correct typed row;
2. decodes it through the kind's application model;
3. loads exact evidence versions and visible stable-item references as requested;
4. returns a typed aggregate plus match reasons to the reporter tool.

The agent never receives a search document as authoritative memory and never
writes directly to the projection.
