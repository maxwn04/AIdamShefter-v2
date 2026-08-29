"""Typed reporter tools over one generation-scoped memory context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    model_validator,
)

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
from backend.services.reporter.runner.models import ToolDef, ToolExecutionResult
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.memory_presentation import (
    MemoryPresentationAdapter,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData


MEMORY_TOOL_IMPLEMENTATION_VERSION = "4"
_READ_TOOL = "search_memory"
_WRITE_TOOLS = (
    "save_memory_event",
    "upsert_storyline_memory_card",
    "save_storyline_trigger",
    "save_team_context",
    "save_league_note",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    """Reporter event payload adapted to canonical trade/matchup constraints."""

    event_type: Literal["trade", "matchup"]
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    salience: int = Field(ge=1, le=5)
    confidence: Literal["unverified", "inferred"]
    status: Literal["active", "superseded", "rejected", "archived"] = "active"
    details: ReporterEventDetails
    source_hints: dict[str, JsonValue] | None = None


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


class SearchMemoryArgs(_StrictModel):
    text: str | None = Field(
        default=None,
        description=(
            "Optional focused editorial concept, name, or phrase. Search uses "
            "lexical matching internally, so keep each call centered on one "
            "continuity question; use OR only for explicit alternatives."
        ),
    )
    team_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Current team names or roster IDs. They are resolved internally; "
            "canonical identifiers are never required or returned."
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Exact memory tags; matching any tag can discover a memory.",
    )
    kinds: list[MemoryKind] = Field(
        default_factory=list,
        description=(
            "Optional hard filter. Returned memories must have one of these kinds."
        ),
    )
    statuses: list[str] = Field(
        default_factory=list,
        description=(
            "Optional hard filter. Returned memories must have one of these exact "
            "statuses. Status vocabulary depends on memory kind."
        ),
    )
    week_from: int | None = Field(
        default=None,
        ge=0,
        description="Optional inclusive first relevant memory week.",
    )
    week_to: int | None = Field(
        default=None,
        ge=0,
        description="Optional inclusive last relevant memory week.",
    )
    limit: int = Field(
        default=8,
        ge=1,
        le=25,
        description="Maximum semantic memories to return; prefer 5-8 focused results.",
    )
    include_evidence: bool = Field(
        default=True,
        description=(
            "Include up to three semantic evidence summaries when available."
        ),
    )
    include_related: bool = Field(
        default=True,
        description=(
            "Include up to three semantic related-memory summaries when available."
        ),
    )

    @model_validator(mode="after")
    def _validate_week_range(self) -> SearchMemoryArgs:
        if (
            self.week_from is not None
            and self.week_to is not None
            and self.week_from > self.week_to
        ):
            raise ValueError("week_from cannot be greater than week_to")
        return self


class SaveMemoryEventArgs(_StrictModel):
    id: str = Field(min_length=1)
    event_type: Literal["trade", "matchup"]
    week: int = Field(ge=0)
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    importance: int = 1
    confidence: Literal["verified", "inferred", "needs_verification"] = (
        "needs_verification"
    )
    source_refs: list[JsonValue] = Field(default_factory=list)
    numbers: dict[str, JsonValue] = Field(default_factory=dict)
    entities: list[dict[str, JsonValue]] = Field(default_factory=list)
    transaction_id: str | None = None
    matchup_id: str | None = None
    details: ReporterEventDetails | None = None


class UpsertStorylineMemoryCardArgs(_StrictModel):
    id: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    status: Literal["active", "stale", "resolved"]
    priority: int = Field(default=2, ge=1, le=5)
    importance: int | None = None
    arc_type: str | None = None
    origin_week: int | None = Field(default=None, ge=0)
    future_callback_condition: str | None = None
    tags: list[str] = Field(default_factory=list)
    team_keys: list[str] = Field(default_factory=list)
    entities: list[dict[str, JsonValue]] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    trigger_specs: list[dict[str, JsonValue]] = Field(default_factory=list)


class SaveStorylineTriggerArgs(_StrictModel):
    trigger_type: Literal["rematch", "trade_evaluation"]
    id: str | None = None
    storyline_id: str | None = None
    event_id: str | None = None
    target_week: int | None = Field(default=None, ge=0)
    condition: dict[str, JsonValue] = Field(default_factory=dict)
    fire_policy: Literal["one_shot", "recurring", "until_resolved"] = "one_shot"
    status: Literal["open", "fired", "expired", "resolved"] = "open"


class SaveTeamContextArgs(_StrictModel):
    roster_key: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    outlook: (
        Literal["rebuilding", "contending", "middling", "surging", "fading"]
        | None
    ) = None


class SaveLeagueNoteArgs(_StrictModel):
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


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
        "Search reporter memory by editorial intent at this generation's pinned "
        "revision. Text, team names, and tags are discovery signals; kinds, statuses, "
        "and inclusive week bounds narrow the results. Returned memories contain "
        "semantic writing context rather than storage identifiers. Treat every "
        "memory as a research lead and verify material claims against frozen data.",
        SearchMemoryArgs,
    ),
    _tool(
        "save_memory_event",
        "Save event evidence for later callbacks. A stable id creates or updates "
        "the event. Include typed details for the trade participants and assets, "
        "or the matchup winner, loser, and Sleeper matchup id.",
        SaveMemoryEventArgs,
    ),
    _tool(
        "upsert_storyline_memory_card",
        "Create or update a storyline memory card by stable id.",
        UpsertStorylineMemoryCardArgs,
    ),
    _tool(
        "save_storyline_trigger",
        "Save or update a dormant callback trigger by stable id. A rematch needs "
        "target_week and two condition.roster_keys; a trade evaluation needs its "
        "event_id and a target week.",
        SaveStorylineTriggerArgs,
    ),
    _tool(
        "save_team_context",
        "Save or update persistent narrative context for one team.",
        SaveTeamContextArgs,
    ),
    _tool(
        "save_league_note",
        "Save or update a league-wide persistent note by key.",
        SaveLeagueNoteArgs,
    ),
]


class MemoryToolInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class _CanonicalReference:
    item_id: UUID
    version_id: UUID


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
        self._pinned_agent_candidates: dict[tuple[MemoryKind, str], Any] = {}
        self._local_agent_refs: dict[tuple[MemoryKind, str], Any] = {}
        self._completed_semantic_saves: dict[
            tuple[str, str], tuple[str, dict[str, Any]]
        ] = {}
        self._presentation = MemoryPresentationAdapter(data)

    def search(self, arguments: SearchMemoryArgs) -> ToolExecutionResult:
        season_id = self._memory_context.competition_season_id
        if season_id is None:
            raise RuntimeError("reporter memory search requires season scope")
        entity_keys: list[str] = []
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
            tags=tuple(arguments.tags),
            kinds=tuple(arguments.kinds),
            statuses=tuple(arguments.statuses),
            competition_season_id=season_id,
            week_from=arguments.week_from,
            week_to=arguments.week_to,
            limit=arguments.limit + 1,
        )
        result = self._memory_context.search(
            MemoryRetrievalRequest(
                query=query,
                expand_exact_references=arguments.include_evidence,
                expand_stable_references=arguments.include_related,
            )
        )
        self._pinned_agent_candidates.update(
            ((match.memory.item.kind, match.memory.item.agent_key), match.memory)
            for match in result.matches
            if match.memory.item.agent_key is not None
        )
        return self._presentation.present(
            result,
            query=query,
            limit=arguments.limit,
        )

    def save_memory_event(
        self,
        context: ToolContext,
        arguments: SaveMemoryEventArgs,
    ) -> dict[str, Any]:
        if arguments.confidence == "verified" and not arguments.source_refs:
            raise MemoryToolInputError(
                "missing_source_refs",
                "verified memory events require at least one source ref",
            )
        canonical = self._legacy_event(arguments)
        result = self._upsert(
            MemoryKind.EVENT,
            arguments.id,
            canonical,
            context=context,
            week=arguments.week,
            create=self._memory_context.propose_event,
            replace=self._memory_context.replace_event,
        )
        return {
            **result,
            "id": arguments.id,
            "confidence": arguments.confidence,
        }

    def upsert_storyline_memory_card(
        self,
        context: ToolContext,
        arguments: UpsertStorylineMemoryCardArgs,
    ) -> dict[str, Any]:
        subjects: list[dict[str, Any]] = []
        sleeper_team_ids: list[int | str] = []
        unresolved: list[str] = []
        team_keys = list(arguments.team_keys)
        for entity in arguments.entities:
            if entity.get("entity_type", entity.get("type")) == "team":
                team_keys.append(str(entity.get("roster_key", entity.get("id", ""))))
        for roster_key in dict.fromkeys(team_keys):
            try:
                roster = self._resolve_roster(roster_key)
            except MemoryToolInputError:
                unresolved.append(roster_key)
                continue
            subjects.append(
                {"kind": "franchise", "id": roster.franchise_id, "role": "focus"}
            )
            sleeper_team_ids.append(_numeric_when_possible(roster.sleeper_roster_id))
        evidence = []
        missing_events: list[str] = []
        for event_id in arguments.evidence_event_ids:
            reference = self._agent_reference(MemoryKind.EVENT, event_id)
            if reference is None:
                missing_events.append(event_id)
            else:
                evidence.append(
                    {
                        "kind": "event",
                        "version_id": reference.version_id,
                        "role": "support",
                    }
                )
        if missing_events:
            raise MemoryToolInputError(
                "unknown_evidence_events",
                f"Could not resolve evidence events: {', '.join(missing_events)}",
            )
        status = {"active": "active", "stale": "dormant", "resolved": "resolved"}[
            arguments.status
        ]
        canonical = StorylineContent.model_validate(
            {
                "headline": arguments.headline,
                "summary": arguments.summary,
                "status": status,
                "arc_type": arguments.arc_type,
                "salience": max(
                    1,
                    min(
                        5,
                        arguments.importance
                        if arguments.importance is not None
                        else 6 - arguments.priority,
                    ),
                ),
                "tags": arguments.tags,
                "subjects": subjects,
                "evidence": evidence,
                "related_storylines": [],
                "callback_condition": arguments.future_callback_condition,
                "resolution_summary": None,
            }
        )
        result = self._upsert(
            MemoryKind.STORYLINE,
            arguments.id,
            canonical,
            context=context,
            week=arguments.origin_week,
            create=self._memory_context.propose_storyline,
            replace=self._memory_context.replace_storyline,
        )
        saved_triggers: list[str] = []
        for raw_spec in arguments.trigger_specs:
            spec = SaveStorylineTriggerArgs.model_validate(
                {**raw_spec, "storyline_id": raw_spec.get("storyline_id", arguments.id)}
            )
            trigger_result = self.save_storyline_trigger(context, spec)
            saved_triggers.append(str(trigger_result["id"]))
        payload = {
            **result,
            "id": arguments.id,
            "status": arguments.status,
            "team_ids": sleeper_team_ids,
            "linked_events": arguments.evidence_event_ids,
            "triggers": saved_triggers,
        }
        if unresolved:
            payload["unresolved_team_keys"] = unresolved
        return payload

    def save_storyline_trigger(
        self,
        context: ToolContext,
        arguments: SaveStorylineTriggerArgs,
    ) -> dict[str, Any]:
        trigger_id = arguments.id or f"trigger_{uuid4().hex[:12]}"
        storyline = (
            self._agent_reference(MemoryKind.STORYLINE, arguments.storyline_id)
            if arguments.storyline_id
            else None
        )
        event = (
            self._agent_reference(MemoryKind.EVENT, arguments.event_id)
            if arguments.event_id
            else None
        )
        if arguments.storyline_id and storyline is None:
            raise MemoryToolInputError(
                "unknown_storyline", "Could not resolve storyline"
            )
        if arguments.event_id and event is None:
            raise MemoryToolInputError("unknown_event", "Could not resolve event")
        condition: dict[str, Any]
        if arguments.trigger_type == "rematch":
            roster_keys = arguments.condition.get("roster_keys")
            if not isinstance(roster_keys, list) or len(roster_keys) != 2:
                raise MemoryToolInputError(
                    "invalid_trigger_condition",
                    "rematch condition requires two roster_keys",
                )
            condition = {"kind": "rematch", "roster_keys": roster_keys}
        else:
            condition = {"kind": "trade_evaluation"}
        canonical = self._trigger(
            ReporterTriggerContent.model_validate(
                {
                    "trigger_type": arguments.trigger_type,
                    "status": (
                        "satisfied"
                        if arguments.status == "resolved"
                        else arguments.status
                    ),
                    "fire_policy": arguments.fire_policy,
                    "target_storyline_item_id": (
                        storyline.item_id if storyline else None
                    ),
                    "origin_event_item_id": event.item_id if event else None,
                    "target_week": arguments.target_week,
                    "condition": condition,
                }
            )
        )
        result = self._upsert(
            MemoryKind.TRIGGER,
            trigger_id,
            canonical,
            context=context,
            create=self._memory_context.propose_trigger,
            replace=self._memory_context.replace_trigger,
        )
        return {
            **result,
            "id": trigger_id,
            "trigger_type": arguments.trigger_type,
            "status": arguments.status,
        }

    def save_team_context(
        self,
        context: ToolContext,
        arguments: SaveTeamContextArgs,
    ) -> dict[str, Any]:
        roster = self._resolve_roster(arguments.roster_key)
        identity = {
            "scope": "franchise",
            "franchise_id": roster.franchise_id,
            "note_key": "team_context",
        }
        canonical = ContextNoteContent.model_validate(
            {
                "narrative": arguments.narrative,
                "outlook": arguments.outlook,
                "status": "active",
                "tags": [],
            }
        )
        result = self._upsert_context_note(
            f"team_context:{roster.franchise_id}", identity, canonical, context
        )
        return {
            **result,
            "roster_id": _numeric_when_possible(roster.sleeper_roster_id),
            "roster_key": arguments.roster_key,
        }

    def save_league_note(
        self,
        context: ToolContext,
        arguments: SaveLeagueNoteArgs,
    ) -> dict[str, Any]:
        identity = {"scope": "competition", "note_key": arguments.key}
        canonical = ContextNoteContent.model_validate(
            {"narrative": arguments.value, "status": "active", "tags": []}
        )
        result = self._upsert_context_note(
            f"league_note:{arguments.key}", identity, canonical, context
        )
        return {**result, "key": arguments.key}

    def buffer_brief_facts(self, brief: Any) -> list[dict[str, Any]]:
        """Buffer every final brief storyline's supporting facts once."""
        results: list[dict[str, Any]] = []
        week = getattr(self._memory_context, "_week", None)
        for storyline in brief.storylines:
            for fact_id in storyline.supporting_fact_ids:
                fact = brief.get_fact(fact_id)
                if fact is None:
                    continue
                agent_key = f"brief:{storyline.id}:{week}:{fact.id}"
                canonical = FactContent.model_validate(
                    {
                        "claim": fact.claim_text,
                        "category": fact.category,
                        "numbers": fact.numbers,
                        "confidence": "inferred",
                        "status": "active",
                        "subjects": [],
                        "originating_event_version_ids": [],
                        "source_hints": {
                            "brief_fact_id": fact.id,
                            "brief_storyline_id": storyline.id,
                            "data_refs": list(fact.data_refs),
                        },
                    }
                )
                results.append(
                    self._upsert(
                        MemoryKind.FACT,
                        agent_key,
                        canonical,
                        context=None,
                        create=self._memory_context.propose_fact,
                        replace=self._memory_context.replace_fact,
                    )
                )
        return results

    def _upsert(
        self,
        kind: MemoryKind,
        agent_key: str,
        canonical: BaseModel,
        *,
        context: ToolContext | None,
        week: int | None = None,
        create: Any,
        replace: Any,
    ) -> dict[str, Any]:
        signature = canonical.model_dump_json()
        save_key = (kind.value, agent_key)
        previous = self._completed_semantic_saves.get(save_key)
        if previous is not None:
            if previous[0] != signature:
                raise MemoryToolInputError(
                    "memory_already_selected",
                    f"{kind.value}:{agent_key} already changed in this run",
                )
            return {**previous[1], "saved": False, "no_change": True}
        candidate = self._agent_candidate(kind, agent_key)
        if candidate is not None and candidate.content == canonical:
            result = {"ok": True, "saved": False, "no_change": True}
        elif candidate is None:
            reference = create(
                canonical,
                metadata=self._metadata(
                    context,
                    agent_key=agent_key,
                    week=week,
                ),
            )
            self._proposed_item_ids.add(reference.item_id)
            self._local_agent_refs[(kind, agent_key)] = reference
            result = self._saved(reference)
        else:
            reference = replace(
                candidate.item.item_id,
                candidate.version.revision_number,
                canonical,
                metadata=self._metadata(context, week=week),
            )
            result = self._saved(reference)
        self._completed_semantic_saves[save_key] = (signature, result)
        return result

    def _upsert_context_note(
        self,
        agent_key: str,
        identity: dict[str, Any],
        canonical: ContextNoteContent,
        context: ToolContext,
    ) -> dict[str, Any]:
        candidate = self._agent_candidate(MemoryKind.CONTEXT_NOTE, agent_key)
        if candidate is None:
            return self._upsert(
                MemoryKind.CONTEXT_NOTE,
                agent_key,
                canonical,
                context=context,
                create=lambda content, *, metadata: (
                    self._memory_context.propose_context_note(
                        identity, content, metadata=metadata
                    )
                ),
                replace=self._memory_context.replace_context_note,
            )
        if candidate.note_identity.model_dump(mode="python") != identity:
            raise MemoryToolInputError(
                "memory_identity_mismatch",
                f"Context note identity changed for {agent_key}",
            )
        return self._upsert(
            MemoryKind.CONTEXT_NOTE,
            agent_key,
            canonical,
            context=context,
            create=self._memory_context.propose_context_note,
            replace=self._memory_context.replace_context_note,
        )

    def _legacy_event(self, arguments: SaveMemoryEventArgs) -> EventContent:
        if arguments.details is None:
            raise MemoryToolInputError(
                "missing_event_details",
                "Typed trade or matchup details are required for durable event memory",
            )
        confidence = (
            "inferred"
            if arguments.confidence in {"verified", "inferred"}
            else "unverified"
        )
        return self._event(
            ReporterEventContent(
                event_type=arguments.event_type,
                headline=arguments.headline,
                summary=arguments.summary,
                salience=max(1, min(5, arguments.importance)),
                confidence=confidence,
                details=arguments.details,
                source_hints={
                    "legacy_confidence": arguments.confidence,
                    "week": arguments.week,
                    "importance": arguments.importance,
                    "source_refs": arguments.source_refs,
                    "numbers": arguments.numbers,
                    "transaction_id": arguments.transaction_id,
                    "matchup_id": arguments.matchup_id,
                    "entities": arguments.entities,
                },
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

    def _agent_candidate(self, kind: MemoryKind, agent_key: str) -> Any | None:
        key = (kind, agent_key)
        if key in self._pinned_agent_candidates:
            return self._pinned_agent_candidates[key]
        result = self._memory_context.search(
            MemoryRetrievalRequest(
                query=SearchDocumentQuery(kinds=(kind,), limit=100)
            )
        )
        matches = [
            match.memory
            for match in result.matches
            if match.memory.item.kind is kind
            and match.memory.item.agent_key == agent_key
        ]
        if len(matches) > 1:
            raise MemoryToolInputError(
                "duplicate_agent_key",
                f"Multiple {kind.value} memories use stable id {agent_key}",
            )
        candidate = matches[0] if matches else None
        if candidate is not None:
            self._pinned_agent_candidates[key] = candidate
        return candidate

    def _agent_reference(self, kind: MemoryKind, agent_key: str | None) -> Any | None:
        if agent_key is None:
            return None
        local = self._local_agent_refs.get((kind, agent_key))
        if local is not None:
            return local
        candidate = self._agent_candidate(kind, agent_key)
        if candidate is None:
            return None
        return _CanonicalReference(
            item_id=candidate.item.item_id,
            version_id=candidate.version.version_id,
        )

    @staticmethod
    def _saved(reference: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "saved": True,
            "proposal": reference.model_dump(mode="json"),
        }

    @staticmethod
    def _metadata(
        context: ToolContext | None,
        *,
        agent_key: str | None = None,
        week: int | None = None,
    ) -> MemoryMutationMetadata:
        return MemoryMutationMetadata(
            creating_tool_call_id=(
                context.current_tool_call_id if context is not None else None
            ),
            agent_key=agent_key,
            week=week,
        )


def _numeric_when_possible(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _safe_error(
    error: ValidationError | MemoryToolInputError,
    *,
    write: bool = False,
) -> dict[str, Any]:
    if isinstance(error, MemoryToolInputError):
        code = error.code
        message = str(error)
    else:
        code = "invalid_memory_input"
        message = "Memory input did not match the typed contract"
    result: dict[str, Any] = {
        "ok": False,
        "error": {"code": code, "message": message},
    }
    if write:
        result["saved"] = False
    return result


def memory_write_blocked_result(tool_name: str) -> dict[str, Any]:
    return {
        "ok": True,
        "saved": False,
        "persisted": False,
        "recorded": False,
        "eval_mode": True,
        "message": f"{tool_name} skipped: memory writes disabled in eval mode",
    }


def register_memory_tools(
    registry: ToolRegistry,
    memory_context: GenerationMemoryContext,
    data: FrozenLeagueData,
    *,
    allow_memory_writes: bool = True,
) -> TypedMemoryAdapter:
    """Register pinned retrieval and buffered semantic memory tools."""

    adapter = TypedMemoryAdapter(memory_context, data)

    def search_memory(**kwargs: Any) -> ToolExecutionResult | dict[str, Any]:
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
        "save_memory_event": SaveMemoryEventArgs,
        "upsert_storyline_memory_card": UpsertStorylineMemoryCardArgs,
        "save_storyline_trigger": SaveStorylineTriggerArgs,
        "save_team_context": SaveTeamContextArgs,
        "save_league_note": SaveLeagueNoteArgs,
    }

    def make_handler(tool_name: str, arguments_model: type[BaseModel]) -> Any:
        def handler(context: ToolContext, **kwargs: Any) -> dict[str, Any]:
            if not allow_memory_writes:
                return memory_write_blocked_result(tool_name)
            try:
                arguments = arguments_model.model_validate(kwargs)
                method = getattr(adapter, tool_name)
                return method(context, arguments)
            except (ValidationError, MemoryToolInputError) as error:
                return _safe_error(error, write=True)

        return handler

    specs_by_name = {spec["function"]["name"]: spec for spec in MEMORY_TOOL_SPECS}
    for tool_name in _WRITE_TOOLS:
        registry.register_context_tool(
            tool_name,
            make_handler(tool_name, write_models[tool_name]),
            specs_by_name[tool_name],
            MEMORY_TOOL_IMPLEMENTATION_VERSION,
        )
    return adapter


__all__ = [
    "MEMORY_TOOL_IMPLEMENTATION_VERSION",
    "MEMORY_TOOL_SPECS",
    "TypedMemoryAdapter",
    "memory_write_blocked_result",
    "register_memory_tools",
]
