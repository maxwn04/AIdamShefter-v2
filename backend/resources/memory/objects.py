"""Typed public resource objects for canonical reporter memory."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import core_schema

from backend.resources.memory.errors import InvalidMemoryContent


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

JsonScalar: TypeAlias = str | int | float | bool | None


class FrozenJsonObject(Mapping[str, Any]):
    """Recursively immutable JSON object with ordinary JSON serialization."""

    __slots__ = ("_values",)

    def __init__(self, value: Mapping[str, Any]) -> None:
        self._values = MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )

    def __getitem__(self, key: str) -> FrozenJsonValue:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"FrozenJsonObject({_thaw_json(self)!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Mapping) and dict(self) == dict(other)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: Any,
    ) -> core_schema.CoreSchema:
        dictionary_schema = core_schema.dict_schema(
            keys_schema=core_schema.str_schema(),
            values_schema=core_schema.any_schema(),
        )
        return core_schema.no_info_after_validator_function(
            cls,
            dictionary_schema,
            serialization=core_schema.plain_serializer_function_ser_schema(
                _thaw_json,
                return_schema=dictionary_schema,
            ),
        )


FrozenJsonValue: TypeAlias = (
    JsonScalar | tuple["FrozenJsonValue", ...] | FrozenJsonObject
)


def _freeze_json(value: Any) -> FrozenJsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return FrozenJsonObject(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise ValueError(f"value is not JSON serializable: {type(value).__name__}")


def _thaw_json(value: FrozenJsonValue) -> Any:
    if isinstance(value, FrozenJsonObject):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


class MemoryObject(BaseModel):
    """Immutable, closed resource value used across application boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class MemoryKind(StrEnum):
    STORYLINE = "storyline"
    FACT = "fact"
    EVENT = "event"
    TRIGGER = "trigger"
    CONTEXT_NOTE = "context_note"


class StorylineStatus(StrEnum):
    ACTIVE = "active"
    DORMANT = "dormant"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class FactStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class EventStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class TriggerStatus(StrEnum):
    OPEN = "open"
    FIRED = "fired"
    SATISFIED = "satisfied"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class ContextNoteStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MemoryStatus(StrEnum):
    """Cross-kind status vocabulary used only for retrieval filtering."""

    ACTIVE = "active"
    DORMANT = "dormant"
    RESOLVED = "resolved"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    OPEN = "open"
    FIRED = "fired"
    SATISFIED = "satisfied"
    EXPIRED = "expired"


class MemoryConfidence(StrEnum):
    UNVERIFIED = "unverified"
    INFERRED = "inferred"
    SOURCE_BACKED = "source_backed"


FactConfidence = MemoryConfidence
EventConfidence = MemoryConfidence


class EntityReference(MemoryObject):
    role: NonEmptyStr
    display_name: NonEmptyStr | None = None


class FranchiseRef(EntityReference):
    kind: Literal["franchise"] = "franchise"
    id: UUID


class PlayerRef(EntityReference):
    kind: Literal["player"] = "player"
    id: NonEmptyStr


class SeasonRosterRef(EntityReference):
    kind: Literal["season_roster"] = "season_roster"
    id: UUID


class SeasonRef(EntityReference):
    kind: Literal["competition_season"] = "competition_season"
    id: UUID


class SleeperUserRef(EntityReference):
    kind: Literal["sleeper_user"] = "sleeper_user"
    id: NonEmptyStr


EntityRef: TypeAlias = Annotated[
    FranchiseRef | PlayerRef | SeasonRosterRef | SeasonRef | SleeperUserRef,
    Field(discriminator="kind"),
]


class FranchiseKey(MemoryObject):
    kind: Literal["franchise"] = "franchise"
    id: UUID


class PlayerKey(MemoryObject):
    kind: Literal["player"] = "player"
    id: NonEmptyStr


class SeasonRosterKey(MemoryObject):
    kind: Literal["season_roster"] = "season_roster"
    id: UUID


class SeasonKey(MemoryObject):
    kind: Literal["competition_season"] = "competition_season"
    id: UUID


class SleeperUserKey(MemoryObject):
    kind: Literal["sleeper_user"] = "sleeper_user"
    id: NonEmptyStr


EntityKey: TypeAlias = Annotated[
    FranchiseKey | PlayerKey | SeasonRosterKey | SeasonKey | SleeperUserKey,
    Field(discriminator="kind"),
]


class EvidenceRef(MemoryObject):
    kind: Literal["fact", "event"]
    version_id: UUID
    role: Literal["origin", "support", "update", "payoff"]


class RelatedStorylineRef(MemoryObject):
    item_id: UUID
    role: Literal["related_arc", "continuation", "counterpoint"]


class StorylineContent(MemoryObject):
    kind: Literal["storyline"] = "storyline"
    schema_version: Literal[1] = 1
    headline: NonEmptyStr
    summary: NonEmptyStr
    status: StorylineStatus
    arc_type: NonEmptyStr | None = None
    salience: int = Field(ge=1, le=5)
    tags: tuple[NonEmptyStr, ...] = ()
    subjects: tuple[EntityRef, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    related_storylines: tuple[RelatedStorylineRef, ...] = ()
    callback_condition: NonEmptyStr | None = None
    resolution_summary: NonEmptyStr | None = None

    @field_validator("tags")
    @classmethod
    def tags_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("tags must be unique")
        return value

    @model_validator(mode="after")
    def validates_owned_references(self) -> StorylineContent:
        allowed_roles = {"focus", "counterparty"}
        invalid_roles = sorted({ref.role for ref in self.subjects} - allowed_roles)
        if invalid_roles:
            raise ValueError(f"invalid storyline subject roles: {invalid_roles}")
        evidence_keys = [(ref.kind, ref.version_id, ref.role) for ref in self.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("storyline evidence references must be unique")
        related_keys = [(ref.item_id, ref.role) for ref in self.related_storylines]
        if len(related_keys) != len(set(related_keys)):
            raise ValueError("related storyline references must be unique")
        return self


class FactContent(MemoryObject):
    kind: Literal["fact"] = "fact"
    schema_version: Literal[1] = 1
    claim: NonEmptyStr
    category: NonEmptyStr
    numbers: FrozenJsonObject = Field(default_factory=lambda: FrozenJsonObject({}))
    confidence: FactConfidence
    status: FactStatus
    subjects: tuple[EntityRef, ...] = ()
    originating_event_version_ids: tuple[UUID, ...] = ()
    primary_tool_call_id: UUID | None = None
    primary_api_request_id: UUID | None = None
    source_hints: FrozenJsonObject | None = None

    @model_validator(mode="after")
    def validates_owned_references(self) -> FactContent:
        invalid_roles = sorted({ref.role for ref in self.subjects} - {"subject"})
        if invalid_roles:
            raise ValueError(f"invalid fact subject roles: {invalid_roles}")
        if len(self.originating_event_version_ids) != len(
            set(self.originating_event_version_ids)
        ):
            raise ValueError("originating event references must be unique")
        return self


class PlayerTradeAsset(MemoryObject):
    kind: Literal["player"] = "player"
    player_id: NonEmptyStr
    display_name: NonEmptyStr | None = None


class DraftPickTradeAsset(MemoryObject):
    kind: Literal["draft_pick"] = "draft_pick"
    season: int = Field(ge=2000, le=2200)
    round: int = Field(ge=1)
    original_season_roster_id: UUID | None = None


class FaabTradeAsset(MemoryObject):
    kind: Literal["faab"] = "faab"
    amount: int = Field(gt=0)


TradeAsset: TypeAlias = Annotated[
    PlayerTradeAsset | DraftPickTradeAsset | FaabTradeAsset,
    Field(discriminator="kind"),
]


class TradeEventPayload(MemoryObject):
    kind: Literal["trade"] = "trade"
    sender_franchise_id: UUID
    receiver_franchise_id: UUID
    assets: tuple[TradeAsset, ...] = Field(min_length=1)
    sleeper_transaction_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def has_distinct_participants(self) -> TradeEventPayload:
        if self.sender_franchise_id == self.receiver_franchise_id:
            raise ValueError("trade sender and receiver must differ")
        return self


class MatchupEventPayload(MemoryObject):
    kind: Literal["matchup"] = "matchup"
    winner_franchise_id: UUID
    loser_franchise_id: UUID
    sleeper_matchup_id: NonEmptyStr

    @model_validator(mode="after")
    def has_distinct_participants(self) -> MatchupEventPayload:
        if self.winner_franchise_id == self.loser_franchise_id:
            raise ValueError("matchup winner and loser must differ")
        return self


class WaiverEventPayload(MemoryObject):
    kind: Literal["waiver"] = "waiver"
    franchise_id: UUID
    added_player_id: NonEmptyStr
    dropped_player_id: NonEmptyStr | None = None
    sleeper_transaction_id: NonEmptyStr | None = None


class StandingsEventPayload(MemoryObject):
    kind: Literal["standings"] = "standings"
    franchise_id: UUID
    previous_rank: int = Field(ge=1)
    current_rank: int = Field(ge=1)

    @model_validator(mode="after")
    def rank_changed(self) -> StandingsEventPayload:
        if self.previous_rank == self.current_rank:
            raise ValueError("standings event must describe a rank change")
        return self


EventPayload: TypeAlias = Annotated[
    TradeEventPayload
    | MatchupEventPayload
    | WaiverEventPayload
    | StandingsEventPayload,
    Field(discriminator="kind"),
]


class EventType(StrEnum):
    TRADE = "trade"
    MATCHUP = "matchup"
    WAIVER = "waiver"
    STANDINGS = "standings"


class EventContent(MemoryObject):
    kind: Literal["event"] = "event"
    schema_version: Literal[1] = 1
    event_type: EventType
    headline: NonEmptyStr
    summary: NonEmptyStr
    salience: int = Field(ge=1, le=5)
    confidence: EventConfidence
    status: EventStatus
    details: EventPayload
    primary_tool_call_id: UUID | None = None
    primary_api_request_id: UUID | None = None
    source_hints: FrozenJsonObject | None = None

    @model_validator(mode="after")
    def event_type_matches_payload(self) -> EventContent:
        if self.event_type.value != self.details.kind:
            raise ValueError("event_type must match details.kind")
        return self


class TriggerType(StrEnum):
    WEEK = "week"
    DATETIME = "datetime"
    EVENT_CALLBACK = "event_callback"


class FirePolicy(StrEnum):
    ONE_SHOT = "one_shot"
    RECURRING = "recurring"
    UNTIL_RESOLVED = "until_resolved"


class WeekTriggerCondition(MemoryObject):
    kind: Literal["week"] = "week"
    week: int = Field(ge=0)


class TimeTriggerCondition(MemoryObject):
    kind: Literal["datetime"] = "datetime"
    at: AwareDatetime


class EventCallbackTriggerCondition(MemoryObject):
    kind: Literal["event_callback"] = "event_callback"
    event_type: EventType
    subject: EntityRef | None = None

    @model_validator(mode="after")
    def validates_subject_role(self) -> EventCallbackTriggerCondition:
        if self.subject is not None and self.subject.role != "subject":
            raise ValueError("event callback subject role must be 'subject'")
        return self


TriggerCondition: TypeAlias = Annotated[
    WeekTriggerCondition | TimeTriggerCondition | EventCallbackTriggerCondition,
    Field(discriminator="kind"),
]


class TriggerContent(MemoryObject):
    kind: Literal["trigger"] = "trigger"
    schema_version: Literal[1] = 1
    trigger_type: TriggerType
    status: TriggerStatus
    fire_policy: FirePolicy
    target_competition_season_id: UUID | None = None
    target_storyline_item_id: UUID | None = None
    origin_event_item_id: UUID | None = None
    target_week: int | None = Field(default=None, ge=0)
    target_at: AwareDatetime | None = None
    condition: TriggerCondition
    resolution_reason: NonEmptyStr | None = None

    @model_validator(mode="before")
    @classmethod
    def derives_time_target_from_condition(cls, value: Any) -> Any:
        if not isinstance(value, dict) or not isinstance(value.get("condition"), dict):
            return value
        normalized = dict(value)
        condition = value["condition"]
        if condition.get("kind") == "week" and "target_week" not in normalized:
            normalized["target_week"] = condition.get("week")
        elif condition.get("kind") == "datetime" and "target_at" not in normalized:
            normalized["target_at"] = condition.get("at")
        return normalized

    @model_validator(mode="after")
    def trigger_type_matches_condition(self) -> TriggerContent:
        if self.trigger_type.value != self.condition.kind:
            raise ValueError("trigger_type must match condition.kind")
        if isinstance(self.condition, WeekTriggerCondition):
            if self.target_week != self.condition.week or self.target_at is not None:
                raise ValueError("week trigger target must match its condition")
        elif isinstance(self.condition, TimeTriggerCondition):
            if self.target_at != self.condition.at or self.target_week is not None:
                raise ValueError("datetime trigger target must match its condition")
        elif self.target_at is not None or self.target_week is not None:
            raise ValueError("event callback triggers do not have a time target")
        return self


class ContextNoteContent(MemoryObject):
    kind: Literal["context_note"] = "context_note"
    schema_version: Literal[1] = 1
    narrative: NonEmptyStr
    outlook: NonEmptyStr | None = None
    status: ContextNoteStatus
    tags: tuple[NonEmptyStr, ...] = ()


MemoryContent: TypeAlias = Annotated[
    StorylineContent | FactContent | EventContent | TriggerContent | ContextNoteContent,
    Field(discriminator="kind"),
]


class ContextNoteScope(StrEnum):
    COMPETITION = "competition"
    COMPETITION_SEASON = "competition_season"
    FRANCHISE = "franchise"


class ContextNoteIdentity(MemoryObject):
    scope: ContextNoteScope
    note_key: NonEmptyStr
    competition_season_id: UUID | None = None
    franchise_id: UUID | None = None

    @model_validator(mode="after")
    def scope_matches_target(self) -> ContextNoteIdentity:
        expected = {
            ContextNoteScope.COMPETITION: (False, False),
            ContextNoteScope.COMPETITION_SEASON: (True, False),
            ContextNoteScope.FRANCHISE: (False, True),
        }[self.scope]
        actual = (
            self.competition_season_id is not None,
            self.franchise_id is not None,
        )
        if actual != expected:
            raise ValueError("context-note target must match its scope")
        return self


class MemoryRevisionRef(MemoryObject):
    id: UUID
    competition_id: UUID
    sequence_number: int = Field(ge=0)
    state_content_hash: NonEmptyStr


class MemoryRevision(MemoryRevisionRef):
    previous_revision_id: UUID | None = None
    producing_generation_id: UUID | None = None
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0)
    knowledge_cutoff_at: AwareDatetime | None = None
    created_at: AwareDatetime


class ExpansionPolicy(MemoryObject):
    include_evidence: bool = False
    include_related_items: bool = False


DEFAULT_EXPANSION = ExpansionPolicy()


class MemoryQuery(MemoryObject):
    text: NonEmptyStr | None = None
    entities: tuple[EntityKey, ...] = ()
    kinds: frozenset[MemoryKind] = frozenset()
    statuses: frozenset[MemoryStatus] = frozenset()
    season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    expansion: ExpansionPolicy = Field(default_factory=ExpansionPolicy)


class TypedMemoryVersion(MemoryObject):
    version_id: UUID
    item_id: UUID
    competition_id: UUID
    kind: MemoryKind
    content: MemoryContent
    content_schema_version: int = Field(ge=1)
    revision_number: int = Field(ge=1)
    introduced_revision_id: UUID
    retired_revision_id: UUID | None = None
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0)
    occurred_at: AwareDatetime | None = None
    creating_generation_id: UUID
    creating_tool_call_id: UUID | None = None
    change_reason: NonEmptyStr | None = None
    recorded_at: AwareDatetime
    context_note_identity: ContextNoteIdentity | None = None

    @model_validator(mode="after")
    def envelope_matches_content(self) -> TypedMemoryVersion:
        if self.kind.value != self.content.kind:
            raise ValueError("version kind must match content kind")
        if self.content_schema_version != self.content.schema_version:
            raise ValueError("content schema version must match decoded content")
        if (self.context_note_identity is not None) != (
            self.kind is MemoryKind.CONTEXT_NOTE
        ):
            raise ValueError(
                "context_note_identity is required exactly for context-note versions"
            )
        if (
            self.context_note_identity is not None
            and self.context_note_identity.scope
            is ContextNoteScope.COMPETITION_SEASON
            and self.context_note_identity.competition_season_id
            != self.competition_season_id
        ):
            raise ValueError(
                "context-note season identity must match the version envelope"
            )
        return self


class HydratedMemoryVersion(MemoryObject):
    version: TypedMemoryVersion
    evidence: tuple[TypedMemoryVersion, ...] = ()
    related_items: tuple[TypedMemoryVersion, ...] = ()


class RetrievedMemoryEntry(MemoryObject):
    memory: HydratedMemoryVersion
    score: float
    match_reasons: tuple[NonEmptyStr, ...] = ()
    rank_components: FrozenJsonObject = Field(
        default_factory=lambda: FrozenJsonObject({})
    )
    matched_entities: tuple[NonEmptyStr, ...] = ()


class RetrievedMemory(MemoryObject):
    revision: MemoryRevisionRef
    entries: tuple[RetrievedMemoryEntry, ...] = ()
    degraded: bool = False


class MemoryListQuery(MemoryObject):
    competition_id: UUID
    revision_id: UUID | None = None
    kinds: frozenset[MemoryKind] = frozenset()
    statuses: frozenset[MemoryStatus] = frozenset()
    cursor: NonEmptyStr | None = None
    limit: int = Field(default=50, ge=1, le=100)


class MemoryPage(MemoryObject):
    revision: MemoryRevisionRef
    items: tuple[HydratedMemoryVersion, ...] = ()
    next_cursor: str | None = None


class ItemHistory(MemoryObject):
    competition_id: UUID
    item_id: UUID
    versions: tuple[TypedMemoryVersion, ...] = ()


class RevisionPage(MemoryObject):
    competition_id: UUID
    revisions: tuple[MemoryRevision, ...] = ()
    next_cursor: str | None = None


class SearchIndexStatus(MemoryObject):
    competition_id: UUID
    builder_version: int = Field(ge=1)
    canonical_version_count: int = Field(ge=0)
    indexed_document_count: int = Field(ge=0)
    missing_document_count: int = Field(ge=0)
    stale_document_count: int = Field(ge=0)


class RebuildResult(MemoryObject):
    competition_id: UUID
    builder_version: int = Field(ge=1)
    rebuilt_document_count: int = Field(ge=0)


class CreateItem(MemoryObject):
    operation: Literal["create"] = "create"
    item_id: UUID = Field(default_factory=uuid4)
    version_id: UUID = Field(default_factory=uuid4)
    client_key: NonEmptyStr
    content: MemoryContent
    context_note_identity: ContextNoteIdentity | None = None

    @model_validator(mode="after")
    def validates_context_note_identity(self) -> CreateItem:
        if (self.context_note_identity is not None) != (
            self.content.kind == MemoryKind.CONTEXT_NOTE.value
        ):
            raise ValueError(
                "context_note_identity is required exactly for context-note creates"
            )
        return self


class ReplaceItem(MemoryObject):
    operation: Literal["replace"] = "replace"
    item_id: UUID
    content: MemoryContent
    change_reason: NonEmptyStr | None = None


MemoryMutation: TypeAlias = Annotated[
    CreateItem | ReplaceItem,
    Field(discriminator="operation"),
]


class MemoryMutationBundle(MemoryObject):
    producing_generation_id: UUID
    operations: tuple[MemoryMutation, ...] = ()


class MutationItemResult(MemoryObject):
    operation_index: int = Field(ge=0)
    client_key: str | None = None
    item_id: UUID
    version_id: UUID


class NoChange(MemoryObject):
    outcome: Literal["no_change"] = "no_change"
    revision: MemoryRevisionRef
    reason: NonEmptyStr


class RevisionCommitted(MemoryObject):
    outcome: Literal["revision_committed"] = "revision_committed"
    revision: MemoryRevisionRef
    items: tuple[MutationItemResult, ...] = ()


MutationResult: TypeAlias = Annotated[
    NoChange | RevisionCommitted,
    Field(discriminator="outcome"),
]


_CONTENT_ADAPTER = TypeAdapter(MemoryContent)


def decode_memory_content(
    kind: MemoryKind | str,
    schema_version: int,
    payload: dict[str, Any],
) -> MemoryContent:
    """Decode one retained storage shape into the current typed contract."""

    try:
        normalized_kind = MemoryKind(kind)
    except ValueError as exc:
        raise InvalidMemoryContent(
            f"unsupported memory kind: {kind}", details={"kind": str(kind)}
        ) from exc
    if schema_version != 1:
        raise InvalidMemoryContent(
            f"unsupported {normalized_kind.value} content schema version {schema_version}",
            details={"kind": normalized_kind.value, "schema_version": schema_version},
        )
    candidate = {**payload, "kind": normalized_kind.value, "schema_version": 1}
    try:
        return _CONTENT_ADAPTER.validate_python(candidate)
    except ValidationError as exc:
        raise InvalidMemoryContent(
            f"invalid {normalized_kind.value} content",
            details={
                "kind": normalized_kind.value,
                "errors": exc.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                ),
            },
        ) from exc
