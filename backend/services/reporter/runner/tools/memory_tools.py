"""Typed reporter tools over one generation-scoped memory context."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from backend.services.memory import (
    ContextNoteContent,
    EventContent,
    FactContent,
    GenerationMemoryContext,
    MemoryKind,
    MemoryMutationMetadata,
    MemoryRetrievalRequest,
    SearchDocumentQuery,
    StorylineContent,
    TriggerContent,
)
from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry


if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData


MEMORY_TOOL_IMPLEMENTATION_VERSION = "1"
_READ_TOOL = "search_memory"
_WRITE_TOOLS = (
    "propose_fact",
    "replace_fact",
    "propose_event",
    "replace_event",
    "propose_storyline",
    "replace_storyline",
    "propose_trigger",
    "replace_trigger",
    "propose_context_note",
    "replace_context_note",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactFranchiseSubject(_StrictModel):
    kind: Literal["franchise"]
    roster_key: str = Field(min_length=1)
    role: Literal["subject"] = "subject"
    display_name: str | None = None


class FactSeasonRosterSubject(_StrictModel):
    kind: Literal["season_roster"]
    roster_key: str = Field(min_length=1)
    role: Literal["subject"] = "subject"
    display_name: str | None = None


class FactPlayerSubject(_StrictModel):
    kind: Literal["player"]
    id: str = Field(min_length=1)
    role: Literal["subject"] = "subject"
    display_name: str | None = None


class FactSeasonSubject(_StrictModel):
    kind: Literal["season"]
    id: UUID
    role: Literal["subject"] = "subject"
    display_name: str | None = None


class FactSleeperUserSubject(_StrictModel):
    kind: Literal["sleeper_user"]
    id: str = Field(min_length=1)
    role: Literal["subject"] = "subject"
    display_name: str | None = None


FactSubject = Annotated[
    FactFranchiseSubject
    | FactSeasonRosterSubject
    | FactPlayerSubject
    | FactSeasonSubject
    | FactSleeperUserSubject,
    Field(discriminator="kind"),
]


class StorylineFranchiseSubject(_StrictModel):
    kind: Literal["franchise"]
    roster_key: str = Field(min_length=1)
    role: Literal["focus", "counterparty"]
    display_name: str | None = None


class StorylineSeasonRosterSubject(_StrictModel):
    kind: Literal["season_roster"]
    roster_key: str = Field(min_length=1)
    role: Literal["focus", "counterparty"]
    display_name: str | None = None


class StorylinePlayerSubject(_StrictModel):
    kind: Literal["player"]
    id: str = Field(min_length=1)
    role: Literal["focus", "counterparty"]
    display_name: str | None = None


class StorylineSeasonSubject(_StrictModel):
    kind: Literal["season"]
    id: UUID
    role: Literal["focus", "counterparty"]
    display_name: str | None = None


class StorylineSleeperUserSubject(_StrictModel):
    kind: Literal["sleeper_user"]
    id: str = Field(min_length=1)
    role: Literal["focus", "counterparty"]
    display_name: str | None = None


StorylineSubject = Annotated[
    StorylineFranchiseSubject
    | StorylineSeasonRosterSubject
    | StorylinePlayerSubject
    | StorylineSeasonSubject
    | StorylineSleeperUserSubject,
    Field(discriminator="kind"),
]


class ReporterFactContent(_StrictModel):
    claim: str = Field(min_length=1)
    category: str = Field(min_length=1)
    numbers: dict[str, JsonValue] = Field(default_factory=dict)
    confidence: Literal["unverified", "inferred"]
    status: Literal["active", "superseded", "rejected", "archived"] = "active"
    subjects: list[FactSubject] = Field(default_factory=list)
    originating_event_version_ids: list[UUID] = Field(default_factory=list)
    source_hints: dict[str, JsonValue] | None = None


class PlayerTradeAsset(_StrictModel):
    kind: Literal["player"]
    direction: Literal["sender_to_receiver", "receiver_to_sender"]
    player_id: str = Field(min_length=1)


class DraftPickTradeAsset(_StrictModel):
    kind: Literal["draft_pick"]
    direction: Literal["sender_to_receiver", "receiver_to_sender"]
    draft_pick_id: UUID


class BudgetTradeAsset(_StrictModel):
    kind: Literal["budget"]
    direction: Literal["sender_to_receiver", "receiver_to_sender"]
    amount: int = Field(ge=0)


TradeAsset = Annotated[
    PlayerTradeAsset | DraftPickTradeAsset | BudgetTradeAsset,
    Field(discriminator="kind"),
]


class ReporterTradeDetails(_StrictModel):
    kind: Literal["trade"]
    sender_roster_key: str = Field(min_length=1)
    receiver_roster_key: str = Field(min_length=1)
    assets: list[TradeAsset] = Field(min_length=1)


class ReporterMatchupDetails(_StrictModel):
    kind: Literal["matchup"]
    winner_roster_key: str = Field(min_length=1)
    loser_roster_key: str = Field(min_length=1)
    sleeper_matchup_id: str = Field(min_length=1)


ReporterEventDetails = Annotated[
    ReporterTradeDetails | ReporterMatchupDetails,
    Field(discriminator="kind"),
]


class ReporterEventContent(_StrictModel):
    event_type: Literal["trade", "matchup"]
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    salience: int = Field(ge=1, le=5)
    confidence: Literal["unverified", "inferred"]
    status: Literal["active", "superseded", "rejected", "archived"] = "active"
    details: ReporterEventDetails
    source_hints: dict[str, JsonValue] | None = None


class StorylineEvidence(_StrictModel):
    kind: Literal["fact", "event"]
    version_id: UUID
    role: Literal["origin", "support", "update", "payoff"]


class RelatedStoryline(_StrictModel):
    item_id: UUID
    role: Literal["related_arc", "continuation", "counterpoint"]


class ReporterStorylineContent(_StrictModel):
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    status: Literal["active", "dormant", "resolved", "archived"] = "active"
    arc_type: str | None = None
    salience: int = Field(ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    subjects: list[StorylineSubject] = Field(default_factory=list)
    evidence: list[StorylineEvidence] = Field(default_factory=list)
    related_storylines: list[RelatedStoryline] = Field(default_factory=list)
    callback_condition: str | None = None
    resolution_summary: str | None = None


class ReporterRematchCondition(_StrictModel):
    kind: Literal["rematch"]
    roster_keys: tuple[str, str]


class ReporterTradeEvaluationCondition(_StrictModel):
    kind: Literal["trade_evaluation"]


ReporterTriggerCondition = Annotated[
    ReporterRematchCondition | ReporterTradeEvaluationCondition,
    Field(discriminator="kind"),
]


class ReporterTriggerContent(_StrictModel):
    trigger_type: Literal["rematch", "trade_evaluation"]
    status: Literal["open", "fired", "satisfied", "expired", "archived"] = "open"
    fire_policy: Literal["one_shot", "recurring", "until_resolved"]
    target_competition_season_id: UUID | None = None
    target_storyline_item_id: UUID | None = None
    origin_event_item_id: UUID | None = None
    target_week: int | None = Field(default=None, ge=0)
    target_at: datetime | None = None
    condition: ReporterTriggerCondition
    resolution_reason: str | None = None


class CompetitionNoteIdentity(_StrictModel):
    scope: Literal["competition"]
    note_key: str = Field(min_length=1)


class CompetitionSeasonNoteIdentity(_StrictModel):
    scope: Literal["competition_season"]
    competition_season_id: UUID
    note_key: str = Field(min_length=1)


class FranchiseNoteIdentity(_StrictModel):
    scope: Literal["franchise"]
    roster_key: str = Field(min_length=1)
    note_key: str = Field(min_length=1)


ReporterContextNoteIdentity = Annotated[
    CompetitionNoteIdentity | CompetitionSeasonNoteIdentity | FranchiseNoteIdentity,
    Field(discriminator="scope"),
]


class ReporterContextNoteContent(_StrictModel):
    narrative: str = Field(min_length=1)
    outlook: str | None = None
    status: Literal["active", "archived"] = "active"
    tags: list[str] = Field(default_factory=list)


class SearchMemoryArgs(_StrictModel):
    text: str | None = None
    team_keys: list[str] = Field(default_factory=list)
    entity_keys: list[str] = Field(default_factory=list)
    evidence_version_ids: list[UUID] = Field(default_factory=list)
    related_item_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    kinds: list[MemoryKind] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    week: int | None = Field(default=None, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    expand_exact_references: bool = False
    expand_stable_references: bool = False


class ProposeFactArgs(_StrictModel):
    content: ReporterFactContent


class ReplaceFactArgs(ProposeFactArgs):
    item_id: UUID
    expected_item_revision: int = Field(gt=0)


class ProposeEventArgs(_StrictModel):
    content: ReporterEventContent


class ReplaceEventArgs(ProposeEventArgs):
    item_id: UUID
    expected_item_revision: int = Field(gt=0)


class ProposeStorylineArgs(_StrictModel):
    content: ReporterStorylineContent


class ReplaceStorylineArgs(ProposeStorylineArgs):
    item_id: UUID
    expected_item_revision: int = Field(gt=0)


class ProposeTriggerArgs(_StrictModel):
    content: ReporterTriggerContent


class ReplaceTriggerArgs(ProposeTriggerArgs):
    item_id: UUID
    expected_item_revision: int = Field(gt=0)


class ProposeContextNoteArgs(_StrictModel):
    identity: ReporterContextNoteIdentity
    content: ReporterContextNoteContent


class ReplaceContextNoteArgs(_StrictModel):
    item_id: UUID
    expected_item_revision: int = Field(gt=0)
    content: ReporterContextNoteContent


def _tool(name: str, description: str, arguments: type[BaseModel]) -> ToolDef:
    parameters = arguments.model_json_schema()
    parameters.pop("title", None)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


MEMORY_TOOL_SPECS: list[ToolDef] = [
    _tool(
        _READ_TOOL,
        "Search fully hydrated canonical memory at this generation's pinned revision. "
        "Returned memories are research leads and must be verified against frozen data.",
        SearchMemoryArgs,
    ),
    _tool("propose_fact", "Buffer a new typed fact.", ProposeFactArgs),
    _tool("replace_fact", "Buffer a complete replacement for a canonical fact.", ReplaceFactArgs),
    _tool("propose_event", "Buffer a new typed matchup or trade event.", ProposeEventArgs),
    _tool(
        "replace_event",
        "Buffer a complete replacement for a canonical event.",
        ReplaceEventArgs,
    ),
    _tool("propose_storyline", "Buffer a new typed storyline.", ProposeStorylineArgs),
    _tool(
        "replace_storyline",
        "Buffer a complete replacement for a canonical storyline.",
        ReplaceStorylineArgs,
    ),
    _tool("propose_trigger", "Buffer a new typed callback trigger.", ProposeTriggerArgs),
    _tool(
        "replace_trigger",
        "Buffer a complete replacement for a canonical trigger.",
        ReplaceTriggerArgs,
    ),
    _tool("propose_context_note", "Buffer a new typed context note.", ProposeContextNoteArgs),
    _tool(
        "replace_context_note",
        "Buffer a complete replacement for a canonical context note.",
        ReplaceContextNoteArgs,
    ),
]


class MemoryToolInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TypedMemoryAdapter:
    """Translate model-facing inputs into canonical typed memory proposals."""

    def __init__(
        self,
        memory_context: GenerationMemoryContext,
        data: FrozenLeagueData,
    ) -> None:
        self._memory_context = memory_context
        self._data = data
        self._proposed_item_ids: set[UUID] = set()

    def search(self, arguments: SearchMemoryArgs) -> dict[str, Any]:
        entity_keys = list(arguments.entity_keys)
        for roster_key in arguments.team_keys:
            identity = self._resolve_roster(roster_key)
            entity_keys.extend(
                (
                    f"franchise:{identity.franchise_id}",
                    f"season_roster:{identity.season_roster_id}",
                )
            )
        query = SearchDocumentQuery(
            text=arguments.text,
            entity_keys=tuple(dict.fromkeys(entity_keys)),
            evidence_version_ids=tuple(arguments.evidence_version_ids),
            related_item_ids=tuple(arguments.related_item_ids),
            tags=tuple(arguments.tags),
            kinds=tuple(arguments.kinds),
            statuses=tuple(arguments.statuses),
            week=arguments.week,
            limit=arguments.limit,
        )
        result = self._memory_context.search(
            MemoryRetrievalRequest(
                query=query,
                expand_exact_references=arguments.expand_exact_references,
                expand_stable_references=arguments.expand_stable_references,
            )
        )
        return {"ok": True, **result.model_dump(mode="json")}

    def propose_fact(
        self,
        context: ToolContext,
        content: ReporterFactContent,
    ) -> dict[str, Any]:
        canonical = FactContent.model_validate(
            {
                **content.model_dump(mode="python", exclude={"subjects"}),
                "subjects": [self._fact_subject(item) for item in content.subjects],
            }
        )
        return self._proposed(
            self._memory_context.propose_fact(
                canonical,
                metadata=self._metadata(context),
            )
        )

    def replace_fact(
        self,
        context: ToolContext,
        arguments: ReplaceFactArgs,
    ) -> dict[str, Any]:
        self._require_canonical_target(arguments.item_id)
        canonical = FactContent.model_validate(
            {
                **arguments.content.model_dump(mode="python", exclude={"subjects"}),
                "subjects": [
                    self._fact_subject(item) for item in arguments.content.subjects
                ],
            }
        )
        return self._replacement(
            self._memory_context.replace_fact(
                arguments.item_id,
                arguments.expected_item_revision,
                canonical,
                metadata=self._metadata(context),
            )
        )

    def propose_event(
        self,
        context: ToolContext,
        content: ReporterEventContent,
    ) -> dict[str, Any]:
        return self._proposed(
            self._memory_context.propose_event(
                self._event(content),
                metadata=self._metadata(context),
            )
        )

    def replace_event(
        self,
        context: ToolContext,
        arguments: ReplaceEventArgs,
    ) -> dict[str, Any]:
        self._require_canonical_target(arguments.item_id)
        return self._replacement(
            self._memory_context.replace_event(
                arguments.item_id,
                arguments.expected_item_revision,
                self._event(arguments.content),
                metadata=self._metadata(context),
            )
        )

    def propose_storyline(
        self,
        context: ToolContext,
        content: ReporterStorylineContent,
    ) -> dict[str, Any]:
        return self._proposed(
            self._memory_context.propose_storyline(
                self._storyline(content),
                metadata=self._metadata(context),
            )
        )

    def replace_storyline(
        self,
        context: ToolContext,
        arguments: ReplaceStorylineArgs,
    ) -> dict[str, Any]:
        self._require_canonical_target(arguments.item_id)
        return self._replacement(
            self._memory_context.replace_storyline(
                arguments.item_id,
                arguments.expected_item_revision,
                self._storyline(arguments.content),
                metadata=self._metadata(context),
            )
        )

    def propose_trigger(
        self,
        context: ToolContext,
        content: ReporterTriggerContent,
    ) -> dict[str, Any]:
        return self._proposed(
            self._memory_context.propose_trigger(
                self._trigger(content),
                metadata=self._metadata(context),
            )
        )

    def replace_trigger(
        self,
        context: ToolContext,
        arguments: ReplaceTriggerArgs,
    ) -> dict[str, Any]:
        self._require_canonical_target(arguments.item_id)
        return self._replacement(
            self._memory_context.replace_trigger(
                arguments.item_id,
                arguments.expected_item_revision,
                self._trigger(arguments.content),
                metadata=self._metadata(context),
            )
        )

    def propose_context_note(
        self,
        context: ToolContext,
        arguments: ProposeContextNoteArgs,
    ) -> dict[str, Any]:
        identity = arguments.identity.model_dump(mode="python")
        if isinstance(arguments.identity, FranchiseNoteIdentity):
            roster = self._resolve_roster(arguments.identity.roster_key)
            identity.pop("roster_key")
            identity["franchise_id"] = roster.franchise_id
        canonical = ContextNoteContent.model_validate(
            arguments.content.model_dump(mode="python")
        )
        return self._proposed(
            self._memory_context.propose_context_note(
                identity,
                canonical,
                metadata=self._metadata(context),
            )
        )

    def replace_context_note(
        self,
        context: ToolContext,
        arguments: ReplaceContextNoteArgs,
    ) -> dict[str, Any]:
        self._require_canonical_target(arguments.item_id)
        canonical = ContextNoteContent.model_validate(
            arguments.content.model_dump(mode="python")
        )
        return self._replacement(
            self._memory_context.replace_context_note(
                arguments.item_id,
                arguments.expected_item_revision,
                canonical,
                metadata=self._metadata(context),
            )
        )

    def _event(self, content: ReporterEventContent) -> EventContent:
        details = content.details.model_dump(mode="python")
        if isinstance(content.details, ReporterTradeDetails):
            sender = self._resolve_roster(content.details.sender_roster_key)
            receiver = self._resolve_roster(content.details.receiver_roster_key)
            details.pop("sender_roster_key")
            details.pop("receiver_roster_key")
            details["sender_franchise_id"] = sender.franchise_id
            details["receiver_franchise_id"] = receiver.franchise_id
        else:
            winner = self._resolve_roster(content.details.winner_roster_key)
            loser = self._resolve_roster(content.details.loser_roster_key)
            details.pop("winner_roster_key")
            details.pop("loser_roster_key")
            details["winner_franchise_id"] = winner.franchise_id
            details["loser_franchise_id"] = loser.franchise_id
        return EventContent.model_validate(
            {
                **content.model_dump(mode="python", exclude={"details"}),
                "details": details,
            }
        )

    def _storyline(self, content: ReporterStorylineContent) -> StorylineContent:
        return StorylineContent.model_validate(
            {
                **content.model_dump(mode="python", exclude={"subjects"}),
                "subjects": [
                    self._storyline_subject(item) for item in content.subjects
                ],
            }
        )

    def _trigger(self, content: ReporterTriggerContent) -> TriggerContent:
        condition = content.condition.model_dump(mode="python")
        values = content.model_dump(mode="python", exclude={"condition"})
        if isinstance(content.condition, ReporterRematchCondition):
            first = self._resolve_roster(content.condition.roster_keys[0])
            second = self._resolve_roster(content.condition.roster_keys[1])
            condition.pop("roster_keys")
            condition["franchise_ids"] = (
                first.franchise_id,
                second.franchise_id,
            )
            supplied_season = content.target_competition_season_id
            if (
                supplied_season is not None
                and supplied_season != first.competition_season_id
            ):
                raise MemoryToolInputError(
                    "competition_season_mismatch",
                    "Target season does not match the frozen roster identity",
                )
            values["target_competition_season_id"] = first.competition_season_id
        return TriggerContent.model_validate({**values, "condition": condition})

    def _fact_subject(self, subject: FactSubject) -> dict[str, Any]:
        return self._subject(subject)

    def _storyline_subject(self, subject: StorylineSubject) -> dict[str, Any]:
        return self._subject(subject)

    def _subject(self, subject: BaseModel) -> dict[str, Any]:
        values = subject.model_dump(mode="python", exclude_none=True)
        if isinstance(
            subject,
            (
                FactFranchiseSubject,
                FactSeasonRosterSubject,
                StorylineFranchiseSubject,
                StorylineSeasonRosterSubject,
            ),
        ):
            roster = self._resolve_roster(subject.roster_key)
            values.pop("roster_key")
            values["id"] = (
                roster.franchise_id
                if subject.kind == "franchise"
                else roster.season_roster_id
            )
        return values

    def _resolve_roster(self, roster_key: str) -> Any:
        resolution = self._data.resolve_roster_identity(roster_key)
        if resolution.status == "not_found":
            raise MemoryToolInputError(
                "roster_not_found",
                f"Could not resolve roster key: {roster_key}",
            )
        if resolution.status == "ambiguous":
            raise MemoryToolInputError(
                "roster_ambiguous",
                f"Roster key matches multiple teams: {roster_key}",
            )
        return resolution.identity

    def _require_canonical_target(self, item_id: UUID) -> None:
        if item_id in self._proposed_item_ids:
            raise MemoryToolInputError(
                "proposal_local_replacement",
                "A proposal created in this run cannot also be replaced",
            )

    def _proposed(self, reference: Any) -> dict[str, Any]:
        self._proposed_item_ids.add(reference.item_id)
        return {"ok": True, "proposal": reference.model_dump(mode="json")}

    @staticmethod
    def _replacement(reference: Any) -> dict[str, Any]:
        return {"ok": True, "proposal": reference.model_dump(mode="json")}

    @staticmethod
    def _metadata(context: ToolContext) -> MemoryMutationMetadata:
        return MemoryMutationMetadata(
            creating_tool_call_id=context.current_tool_call_id,
        )


def memory_write_blocked_result(tool_name: str) -> dict[str, Any]:
    return {
        "ok": True,
        "proposed": False,
        "eval_mode": True,
        "message": f"{tool_name} skipped: memory writes disabled in eval mode",
    }


def _safe_error(error: ValidationError | MemoryToolInputError) -> dict[str, Any]:
    if isinstance(error, MemoryToolInputError):
        code = error.code
        message = str(error)
    else:
        code = "invalid_memory_input"
        message = "Memory input did not match the typed contract"
    return {"ok": False, "error": {"code": code, "message": message}}


def register_memory_tools(
    registry: ToolRegistry,
    memory_context: GenerationMemoryContext,
    data: FrozenLeagueData,
    *,
    allow_memory_writes: bool = True,
) -> None:
    """Register pinned retrieval and buffered typed proposal tools."""

    adapter = TypedMemoryAdapter(memory_context, data)

    def search_memory(**kwargs: Any) -> dict[str, Any]:
        try:
            return adapter.search(SearchMemoryArgs.model_validate(kwargs))
        except (ValidationError, MemoryToolInputError) as error:
            return _safe_error(error)

    registry.register(
        _READ_TOOL,
        search_memory,
        MEMORY_TOOL_SPECS[0],
        MEMORY_TOOL_IMPLEMENTATION_VERSION,
    )

    write_models: dict[str, type[BaseModel]] = {
        "propose_fact": ProposeFactArgs,
        "replace_fact": ReplaceFactArgs,
        "propose_event": ProposeEventArgs,
        "replace_event": ReplaceEventArgs,
        "propose_storyline": ProposeStorylineArgs,
        "replace_storyline": ReplaceStorylineArgs,
        "propose_trigger": ProposeTriggerArgs,
        "replace_trigger": ReplaceTriggerArgs,
        "propose_context_note": ProposeContextNoteArgs,
        "replace_context_note": ReplaceContextNoteArgs,
    }

    def make_handler(tool_name: str, arguments_model: type[BaseModel]) -> Any:
        def handler(context: ToolContext, **kwargs: Any) -> dict[str, Any]:
            if not allow_memory_writes:
                return memory_write_blocked_result(tool_name)
            try:
                arguments = arguments_model.model_validate(kwargs)
                method = getattr(adapter, tool_name)
                if (
                    tool_name.startswith("propose_")
                    and tool_name != "propose_context_note"
                ):
                    return method(context, arguments.content)
                return method(context, arguments)
            except (ValidationError, MemoryToolInputError) as error:
                return _safe_error(error)

        return handler

    specs_by_name = {spec["function"]["name"]: spec for spec in MEMORY_TOOL_SPECS}
    for tool_name in _WRITE_TOOLS:
        registry.register_context_tool(
            tool_name,
            make_handler(tool_name, write_models[tool_name]),
            specs_by_name[tool_name],
            MEMORY_TOOL_IMPLEMENTATION_VERSION,
        )


__all__ = [
    "MEMORY_TOOL_IMPLEMENTATION_VERSION",
    "MEMORY_TOOL_SPECS",
    "TypedMemoryAdapter",
    "memory_write_blocked_result",
    "register_memory_tools",
]
