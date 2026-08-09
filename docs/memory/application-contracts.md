# Application Memory Contracts

**Status:** Application design; database storage implemented, application code pending

## Goal

Callers should know the complete legal shape of a mutation without understanding
ORM association rows. Routes, tools, services, and the reporter operate on typed
resource objects; only the memory manager translates those objects into storage.
The caller-facing capability boundaries and orchestration ownership are defined
in [`service-architecture.md`](service-architecture.md).

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

Retrieval filters use the corresponding role-free `EntityKey` union. Roles and
display-name snapshots describe how authored memory uses an entity; asking for
memory about an entity should not require the caller to invent either value.

`display_name` is an optional immutable label snapshot for this memory version,
not a pointer to a current name. Search-document rebuilds may use the stored
snapshot but never resolve a newer external label. The stable ID remains
authoritative.

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

The public service accepts one general bundle of discriminated create and
replace operations:

```python
class CreateItem(BaseModel):
    item_id: UUID = Field(default_factory=uuid4)
    version_id: UUID = Field(default_factory=uuid4)
    client_key: str
    content: MemoryContent


class ReplaceItem(BaseModel):
    item_id: UUID
    content: MemoryContent
    change_reason: str | None = None


class MemoryMutationBundle(BaseModel):
    producing_generation_id: UUID
    operations: list[CreateItem | ReplaceItem]
```

`MemoryContent` is the discriminated union of the five complete content types.
There are no separate `create_storyline`, `replace_fact`, or similar service
methods. Small kind-specific constructors may improve call-site typing, but they
only construct these general operations and do not add service layers.

Create IDs are generated when the immutable operation is constructed. A later
operation in the same bundle can therefore reference the exact version or stable
item of an earlier create without introducing a parallel client-key reference
vocabulary. The service rejects duplicate generated IDs and duplicate client
keys before persistence.

A patch-oriented UI may edit individual fields locally, but the manager validates
and persists one complete replacement. This prevents a caller from accidentally
creating a partial version whose omitted relationships have ambiguous meaning.

The manager derives competition, season, week, knowledge cutoff, and the pinned
base revision from the producing generation inside the mutation operation. The
base revision is the only optimistic concurrency token; the version visible for
a replacement item is determined under that locked base.

Before opening the canonical write transaction, all model or external work is
complete. Validation ownership is split once:

1. Pydantic resource objects validate content shape, schema version,
   discriminators, and pure per-object invariants.
2. The service validates same-bundle client keys and references, rejects
   contradictions, and returns `NoChange` for an empty bundle.
3. Inside the short transaction, the manager loads the generation and persisted
   references, checks kinds and competition, resolves identical-content no-ops,
   locks the current canonical revision, and writes complete replacements with
   search documents atomically.

Failures return typed application errors such as target-not-found,
wrong-target-kind, cross-competition-reference, or stale-canonical-revision.
The manager translates expected constraint failures while it still has database
context; callers do not interpret constraint names.

An empty bundle, identical replacement, or already-represented transition is a
`NoChange` result and creates no revision. Retrying a producing generation that
already committed returns its existing committed result.

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
