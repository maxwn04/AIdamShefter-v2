# Application Memory Contracts

**Status:** Application design; database storage implemented, application code pending

## Goal

Callers should know the complete legal shape of a mutation without understanding
ORM association rows. Routes, tools, services, and the reporter operate on typed
resource objects. Typed resource managers translate their own objects, while
the mutation service and revision manager coordinate an atomic bundle.

The examples below are illustrative Pydantic-style contracts, not final code.

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

Each owning content type narrows the roles it accepts. A trade event may accept
`sender`, `receiver`, and `asset`; a fact may accept `subject`; a storyline may
accept `focus` and `counterparty`. Sharing the low-level reference primitive does
not imply sharing one generic semantic role bag.

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
    numbers: dict[str, object]
    confidence: FactConfidence
    status: FactStatus
    subjects: list[FactEntityRef]
    originating_event_version_ids: list[UUID]
    primary_tool_call_id: UUID | None = None
    primary_api_request_id: UUID | None = None
    source_hints: dict[str, object] | None = None
```

An originating event is optional context; the fact remains a claim with its own
receipts. It does not contain another event payload.

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
    TradeEventPayload | MatchupEventPayload | WaiverEventPayload,
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
```

`details` describes this event. It is not a collection of related events. The
declared event type and discriminated payload must agree.

### Trigger

```python
class TriggerContent(BaseModel):
    schema_version: Literal[1]
    trigger_type: TriggerType
    status: TriggerStatus
    fire_policy: FirePolicy
    target_storyline_item_id: UUID | None = None
    origin_event_item_id: UUID | None = None
    target_week: int | None = None
    target_at: datetime | None = None
    condition: TriggerCondition
    resolution_reason: str | None = None
```

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

## Mutation Contract

Public mutations create or replace complete typed content:

```python
create_storyline(content: StorylineContent, ...)

replace_storyline(
    item_id: UUID,
    expected_item_revision: int,
    content: StorylineContent,
    ...,
)
```

A patch-oriented UI may edit individual fields locally, but the manager validates
and persists one complete replacement. This prevents a caller from accidentally
creating a partial version whose omitted relationships have ambiguous meaning.

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
or external work. Inside the short transaction, the revision manager invokes
resource-local transaction helpers to:

1. validate Pydantic content and schema version;
2. load every referenced item/version in one scoped batch;
3. require the expected kinds and same competition;
4. validate references created in the same mutation bundle;
5. lock and verify the current canonical revision;
6. write the complete replacement and its search projection atomically.

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
