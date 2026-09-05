# Application Memory Contracts

**Status:** Typed v1 contracts, resource managers, services, and HTTP boundary
implemented

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

Retrieval accepts a typed search query plus independent exact-reference and
stable-reference expansion flags. The retrieval service then:

1. loads the visible `memory_version` and correct typed row;
2. decodes it through the kind's application model;
3. loads exact evidence versions and visible stable-item references as requested;
4. returns a typed aggregate plus match reasons and matched query values.

Expansions are typed, one-hop sidecars. Storyline evidence and fact originating
events preserve exact immutable version identity even after retirement.
Related storylines and trigger storyline/event targets resolve the version of
the stable item visible at the pinned revision. Expanded targets are not
recursively enriched, and the owning canonical aggregate is not rewritten.

The agent never receives a search document as authoritative memory and never
writes directly to the projection.


## Source-derived reporter event handoff

The reporter's `save_memory_event` takes successful `source_fact_ids`, an event
kind, and editorial headline/summary/salience. Canonical saved bindings select
executed source records; the frozen query runtime resolves exactly one matchup or
completed two-party trade. The runtime derives matchup number, participants,
asset identity and asset direction. All assets in the selected trade are retained,
even when the selecting fact binds only one movement. Unsupported or ambiguous
source events fail before a proposal is selected, with a repair message.

Resolution reads use the guarded frozen SQL interface. Full query parameters,
returned rows and selected bindings are retained in tool execution metadata and
event source hints. The model receives a compact success receipt with the stable
event key, source fact IDs and event week. Headlines and summaries remain editorial
interpretation; selecting a factual source is not a proof of their wording.

Transaction `source_week` is a provider grouping, not an occurrence interval.
The source timestamp is preserved as `occurred_at` when available. Events can be
saved only in the active generation's season; historical facts remain research
leads until explicit cross-season transfer is implemented.

Draft-pick event assets accept either the existing `draft_pick_id` UUID or a
complete natural identity: `season` (the **draft year**), `round`, and
`original_franchise_id`. This is an extension of the stored event JSON contract;
it needs no relational column migration. Natural identities represent source
picks whose frozen snapshot has no canonical pick UUID. Original franchise must
belong to the competition. UUID and natural identity must not be mixed, incomplete
identities are rejected, and two draft years remain distinct picks. Legacy UUID
assets retain their exact previous serialized shape; new optional fields are not
inserted into old content or its canonical hash input.

## Recalled-memory update handles

Semantic memory context includes a run-local `memory_handle`, bound to a canonical
item and exact immutable version. Repeated hydration of that version returns the
same handle. `upsert_storyline_memory_card` accepts either a new creation `id` or
an `update_handle`. Creation keys already present at the pinned revision return an
update handle instead of creating a duplicate. Exact creation-key resolution is
filtered before ranking or limits; it is not a scan of the top recalled items.

Updates preserve omitted subjects, status, tags, salience, callback, resolution,
origin week and origin season, retain existing evidence and linked arcs, and append
new successful event references. Explicit field changes still undergo canonical
validation. Cross-season storyline updates currently return an actionable error.
A handle linked after an event replacement in the same run resolves to the new
selected event version. A card and its embedded trigger writes form one proposal
savepoint: any failure rolls back all changes from that tool call, including local
reference and idempotency caches. Earlier successful tool calls remain buffered.
Successful tools still produce proposals; generation finalization controls atomic
persistence and must not be inferred from a save receipt alone.


## Scheduled editorial reviews

A `scheduled_review` trigger requests a review of a canonical storyline at an
explicit target season and week. Its condition carries a `review_question`.
There is no required event or fabricated matchup participant. The reporter binds
the target season from its runtime and defaults to `one_shot`.

Being due means that the reporter should examine evidence and decide whether the
arc changed. It does not prove an event occurred or require mentioning the arc in
an article. The reporter can mark the same trigger resolved with a review reason,
or explicitly reopen it with a later week. Omitted fields on a handle update retain
the existing target and question. Resolved one-shot reviews are not due again.

Tool conditions accept only the fields defined for their trigger kind. Event IDs
belong at the top level, and generic follow-ups use scheduled reviews instead of
trade or rematch labels. New trade evaluations require source-backed trade-event
origins, including events selected earlier in the same generation. A reporter
rematch callback requires a source-backed prior matchup between the selected
franchises; its future week is a review date, not a claim that the teams are
scheduled to meet. Recall presents all callbacks as questions to verify.

This extends the stored v1 trigger JSON union without changing relational columns.
Legacy trigger content remains readable with its original shape and hash inputs.
Closing a legacy callback does not assert that its old condition was correct.


Each memory item can be selected once per generation; an exact retry is a no-op.
Save all supporting events before updating their storyline. A second differing
storyline update in the same run is rejected rather than amending the selected
proposal, so events saved later cannot be appended to that selection. This remains
an explicit loop limitation; adding mutable proposal amendments is separate work.
Active trade origins rejected at the HTTP boundary return `invalid_trigger_origin`
with status 400. Historical malformed callbacks can still be read and closed;
closing them does not certify the condition or origin.


## Automatic recall for broad and focused reports

Automatic lexical discovery uses explicit `focus_hints` as independent OR anchors,
plus resolved focus-team and bias-team identities. The full writing request,
custom instructions and operational/time notices never become mandatory search
terms. A focused request that matches nothing stays narrow; an unresolved team
name does not silently enable broad recall.

Without explicit focus inputs, generation-start recall supplies a separate
`storyline_review_pool`: at most three active storylines from the current season,
with memory weeks no later than the report week, at the exact pinned revision.
The existing deterministic salience ranking selects the pool. Each lead includes
its update handle, a bounded headline/summary/callback and relevant week. Text
truncation is explicit. Evidence and related-memory expansion are omitted here;
focused search and due callbacks retain their normal paths. Arcs already presented
through due callbacks do not consume the pool budget.

These are prior editorial hypotheses for optional review, not verified current
facts or requirements to mention every arc. Selecting a lead neither updates it
nor resolves it. Scheduled reviews and explicit search remain the mechanisms for
following quiet arcs; this small pool is not a comprehensive lifecycle scheduler
or a guarantee that every active arc is revisited.
