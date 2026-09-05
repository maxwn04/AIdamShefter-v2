"""Typed reporter tools over one generation-scoped memory context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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
    GenerationMemoryContext,
    HydratedMemoryMatch,
    MemoryKind,
    MemoryMutationMetadata,
    MemoryRetrievalRequest,
    SearchDocumentQuery,
    StorylineContent,
    TriggerContent,
)
from backend.services.reporter.config import ReportConfig
from backend.services.reporter.runner.models import ToolDef, ToolExecutionResult
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.memory_event_evidence import (
    EventEvidenceError,
    resolve_event,
)
from backend.services.reporter.runner.tools.memory_presentation import (
    MemoryPresentationAdapter,
)
from backend.services.reporter.runner.tools.memory_recall import (
    MemoryRecallPlan,
    MemoryRecallPlanner,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData


MEMORY_TOOL_IMPLEMENTATION_VERSION = "6"
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
    source_fact_ids: list[str] = Field(
        min_length=1,
        description=("Successfully saved brief fact IDs for one matchup or trade; "
                     "runtime derives identities, week, and all assets."),
    )
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    importance: int = 1


class UpsertStorylineMemoryCardArgs(_StrictModel):
    id: str | None = Field(
        default=None, min_length=1,
        description="Creation key for a new arc only. Update recalled cards with update_handle.",
    )
    update_handle: str | None = Field(
        default=None, min_length=1,
        description="memory_handle returned with the existing storyline. Mutually exclusive with id.",
    )
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    status: Literal["active", "stale", "resolved"] | None = None
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
    resolution_summary: str | None = None

    @model_validator(mode="after")
    def validate_selector(self) -> UpsertStorylineMemoryCardArgs:
        if (self.id is None) == (self.update_handle is None):
            raise ValueError("Use id to create a new arc OR update_handle from recalled memory to update it")
        return self


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
        "Save one durable event from successful source_fact_ids in the brief. "
        "Runtime derives the event week, identities, participants and all trade assets. "
        "Use returned id in storyline evidence_event_ids only after a successful save or no_change receipt. "
        "Never author matchup IDs, player IDs, draft-pick IDs or source_refs.",
        SaveMemoryEventArgs,
    ),
    _tool(
        "upsert_storyline_memory_card",
        "Create a new storyline with id, or update a recalled card with its memory_handle "
        "as update_handle. Updates preserve origin, existing evidence and omitted state; "
        "evidence_event_ids add successfully saved events. Do not invent a new key for a recalled arc.",
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
        self._recall = MemoryRecallPlanner(
            memory_context,
            data,
            self._presentation,
        )

    @contextmanager
    def write_savepoint(self) -> Iterator[None]:
        """Keep a parent card and its dependent proposals atomic within a call."""
        completed = self._completed_semantic_saves.copy()
        local_refs = self._local_agent_refs.copy()
        proposed_ids = self._proposed_item_ids.copy()
        try:
            with self._memory_context.proposal_savepoint():
                yield
        except BaseException:
            self._completed_semantic_saves = completed
            self._local_agent_refs = local_refs
            self._proposed_item_ids = proposed_ids
            raise

    def build_recall(self, config: ReportConfig) -> MemoryRecallPlan:
        plan = self._recall.plan(config)
        self._cache_pinned_candidates(plan.candidates)
        return plan

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
        self._cache_pinned_candidates(result.matches)
        return self._presentation.present(
            result,
            query=query,
            limit=arguments.limit,
        )

    def _cache_pinned_candidates(
        self,
        matches: tuple[HydratedMemoryMatch, ...],
    ) -> None:
        self._pinned_agent_candidates.update(
            ((match.memory.item.kind, match.memory.item.agent_key), match.memory)
            for match in matches
            if match.memory.item.agent_key is not None
        )

    def save_memory_event(
        self,
        context: ToolContext,
        arguments: SaveMemoryEventArgs,
    ) -> dict[str, Any]:
        try:
            resolved = resolve_event(
                context, self._data, arguments.event_type, arguments.source_fact_ids,
                competition_season_id=self._memory_context.competition_season_id,
            )
        except EventEvidenceError as error:
            raise MemoryToolInputError("insufficient_event_evidence", str(error)) from error
        candidate = self._agent_candidate(MemoryKind.EVENT, arguments.id)
        if (
            candidate is not None
            and candidate.version.competition_season_id is not None
            and candidate.version.competition_season_id
            != self._memory_context.competition_season_id
        ):
            raise MemoryToolInputError(
                "cross_season_update_unsupported",
                "This event key belongs to another season. Use a new event key "
                "for the current-season source facts; historical events cannot "
                "be replaced with current-season details.",
            )
        canonical = EventContent.model_validate({
            "event_type": arguments.event_type, "headline": arguments.headline,
            "summary": arguments.summary, "salience": max(1, min(5, arguments.importance)),
            "confidence": "source_backed" if context.current_tool_call_id else "inferred",
            "primary_tool_call_id": context.current_tool_call_id,
            "status": "active", "details": resolved.details,
            "source_hints": resolved.audit,
        })
        result = self._upsert(
            MemoryKind.EVENT,
            arguments.id,
            canonical,
            context=context,
            week=resolved.week,
            occurred_at=resolved.occurred_at,
            candidate=candidate,
            create=self._memory_context.propose_event,
            replace=self._memory_context.replace_event,
        )
        return {
            **result,
            "id": arguments.id,
            "event_type": arguments.event_type,
            "week": resolved.week,
            "source_fact_ids": arguments.source_fact_ids,
            "confidence": canonical.confidence.value,
            "_event_resolution": resolved.audit,
        }

    def upsert_storyline_memory_card(
        self,
        context: ToolContext,
        arguments: UpsertStorylineMemoryCardArgs,
    ) -> dict[str, Any]:
        candidate = None
        if arguments.update_handle:
            candidate = self._presentation.resolve_handle(arguments.update_handle)
            if candidate is None or candidate.item.kind is not MemoryKind.STORYLINE:
                raise MemoryToolInputError("unknown_memory_handle", "Use the memory_handle returned on the existing storyline; search for the arc if it is not in context.")
            if (candidate.version.competition_season_id is not None
                    and candidate.version.competition_season_id != self._memory_context.competition_season_id):
                raise MemoryToolInputError("cross_season_update_unsupported",
                    "This storyline belongs to another season. Cross-season memory transfer is not supported by this update tool.")
            agent_key = candidate.item.agent_key or arguments.update_handle
        else:
            agent_key = arguments.id
            existing = self._agent_candidate(MemoryKind.STORYLINE, agent_key)
            if existing is not None:
                handle = self._presentation.handle_for(existing)
                raise MemoryToolInputError("existing_storyline", f"Creation id already exists. Update it with update_handle={handle}; do not create another key.")
        # Validate embedded trigger shapes before selecting the parent card.
        trigger_specs = [SaveStorylineTriggerArgs.model_validate(raw) for raw in arguments.trigger_specs]
        subjects: list[dict[str, Any]] = []
        sleeper_team_ids: list[int | str] = []
        team_keys = list(arguments.team_keys)
        for entity in arguments.entities:
            if entity.get("entity_type", entity.get("type")) != "team":
                raise MemoryToolInputError(
                    "unsupported_storyline_entity",
                    "Each entities entry must explicitly identify type='team' "
                    "(or entity_type='team') and a roster_key, id, or name. "
                    "Use team_keys for team names, omit entities to preserve "
                    "existing subjects, or supply an empty list to clear them.",
                )
            team_keys.append(str(entity.get("roster_key") or entity.get("id") or entity.get("name") or ""))
        for roster_key in dict.fromkeys(team_keys):
            roster = self._resolve_roster(roster_key)
            subjects.append(
                {"kind": "franchise", "id": roster.franchise_id, "role": "focus"}
            )
            sleeper_team_ids.append(_numeric_when_possible(roster.sleeper_roster_id))
        evidence = [ref.model_dump(mode="python") for ref in candidate.content.evidence] if candidate else []
        missing_events: list[str] = []
        for event_id in arguments.evidence_event_ids:
            reference = self._agent_reference(MemoryKind.EVENT, event_id)
            if reference is None:
                missing_events.append(event_id)
            else:
                if any(ref["version_id"] == reference.version_id for ref in evidence):
                    continue
                evidence.append(
                    {
                        "kind": "event",
                        "version_id": reference.version_id,
                        "role": "update" if candidate else "origin" if not evidence else "support",
                    }
                )
        if missing_events:
            successful_events = sorted(
                key for (kind, key) in self._local_agent_refs
                if kind is MemoryKind.EVENT
            )[:5]
            repair = (
                "Save or repair those events successfully first, then retry "
                "the storyline using their returned IDs; do not invent IDs."
            )
            if successful_events:
                repair += " Successful event keys this run: " + ", ".join(successful_events)
            raise MemoryToolInputError(
                "unknown_evidence_events",
                f"Could not resolve evidence events: {', '.join(missing_events)}. {repair}",
            )
        status = candidate.content.status.value if candidate else "active"
        if arguments.status is not None:
            status = {"active": "active", "stale": "dormant", "resolved": "resolved"}[arguments.status]
        values: dict[str, Any] = candidate.content.model_dump(mode="python") if candidate else {}
        values.update({
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
                "related_storylines": values.get("related_storylines", []),
                "callback_condition": arguments.future_callback_condition,
                "resolution_summary": arguments.resolution_summary,
            })
        if candidate:
            preserved = {"arc_type": "arc_type", "tags": "tags",
                         "future_callback_condition": "callback_condition", "resolution_summary": "resolution_summary"}
            for argument_field, content_field in preserved.items():
                if argument_field not in arguments.model_fields_set:
                    values[content_field] = getattr(candidate.content, content_field)
            if not {"team_keys", "entities"}.intersection(arguments.model_fields_set):
                values["subjects"] = candidate.content.subjects
            if "importance" not in arguments.model_fields_set and "priority" not in arguments.model_fields_set:
                values["salience"] = candidate.content.salience
        canonical = StorylineContent.model_validate(values)
        result = self._upsert(
            MemoryKind.STORYLINE,
            agent_key,
            canonical,
            context=context,
            week=candidate.version.week if candidate else arguments.origin_week,
            candidate=candidate,
            create=self._memory_context.propose_storyline,
            replace=self._memory_context.replace_storyline,
        )
        trigger_results: list[dict[str, Any]] = []
        for spec in trigger_specs:
            spec = spec.model_copy(update={"storyline_id": spec.storyline_id or agent_key})
            trigger_result = self.save_storyline_trigger(context, spec)
            trigger_results.append(trigger_result)
        payload = {
            **result,
            "id": agent_key,
            "update_handle": arguments.update_handle,
            "status": canonical.status.value,
            "team_ids": sleeper_team_ids,
            "linked_events": arguments.evidence_event_ids,
            "triggers": [str(result["id"]) for result in trigger_results],
            "trigger_results": trigger_results,
        }
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
        candidate: Any = None,
        occurred_at: datetime | None = None,
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
            return {
                **previous[1],
                "saved": False,
                "no_change": True,
                "operation": "no_change",
            }
        candidate = candidate or self._agent_candidate(kind, agent_key)
        if candidate is not None and candidate.content == canonical:
            result = {
                "ok": True,
                "saved": False,
                "no_change": True,
                "memory_kind": kind.value,
                "operation": "no_change",
            }
        elif candidate is None:
            reference = create(
                canonical,
                metadata=self._metadata(
                    context,
                    agent_key=agent_key,
                    week=week,
                    occurred_at=occurred_at,
                ),
            )
            self._proposed_item_ids.add(reference.item_id)
            self._local_agent_refs[(kind, agent_key)] = reference
            result = self._saved(reference, kind=kind, operation="create")
        else:
            reference = replace(
                candidate.item.item_id,
                candidate.version.revision_number,
                canonical,
                metadata=self._metadata(
                    context, week=week if week is not None else candidate.version.week,
                    competition_season_id=candidate.version.competition_season_id,
                    occurred_at=occurred_at or candidate.version.occurred_at,
                ),
            )
            self._local_agent_refs[(kind, agent_key)] = reference
            result = self._saved(reference, kind=kind, operation="replace")
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
                query=SearchDocumentQuery(kinds=(kind,), agent_key=agent_key, limit=2)
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
        candidate = self._presentation.resolve_handle(agent_key)
        if candidate is not None and candidate.item.kind is not kind:
            raise MemoryToolInputError("memory_kind_mismatch", f"{agent_key} is not a {kind.value} memory")
        candidate = candidate or self._agent_candidate(kind, agent_key)
        if candidate is None:
            return None
        local = self._local_agent_refs.get((kind, candidate.item.agent_key))
        if local is not None:
            return local
        return _CanonicalReference(
            item_id=candidate.item.item_id,
            version_id=candidate.version.version_id,
        )

    @staticmethod
    def _saved(
        reference: Any,
        *,
        kind: MemoryKind,
        operation: str,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "saved": True,
            "memory_kind": kind.value,
            "operation": operation,
            "proposal": reference.model_dump(mode="json"),
        }

    @staticmethod
    def _metadata(
        context: ToolContext | None,
        *,
        agent_key: str | None = None,
        week: int | None = None,
        occurred_at: datetime | None = None,
        competition_season_id: UUID | None = None,
    ) -> MemoryMutationMetadata:
        return MemoryMutationMetadata(
            creating_tool_call_id=(
                context.current_tool_call_id if context is not None else None
            ),
            agent_key=agent_key,
            competition_season_id=competition_season_id,
            week=week,
            occurred_at=occurred_at,
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
        fields = [".".join(map(str, detail["loc"])) + ": " + detail["msg"] for detail in error.errors(include_input=False, include_url=False)[:4]]
        message = "Memory input did not match the typed contract: " + "; ".join(fields)
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
        def handler(
            context: ToolContext, **kwargs: Any
        ) -> ToolExecutionResult | dict[str, Any]:
            if not allow_memory_writes:
                return memory_write_blocked_result(tool_name)
            try:
                arguments = arguments_model.model_validate(kwargs)
                method = getattr(adapter, tool_name)
                with adapter.write_savepoint():
                    result = method(context, arguments)
                activity_items: list[dict[str, JsonValue]] = []
                if result.get("saved") is True:
                    activity_items.append(
                        {
                            "path": "result",
                            "kind": result.pop("memory_kind"),
                            "operation": result.pop("operation"),
                        }
                    )
                else:
                    result.pop("memory_kind", None)
                    result.pop("operation", None)

                trigger_results = result.pop("trigger_results", [])
                for index, trigger_result in enumerate(trigger_results):
                    if trigger_result.get("saved") is not True:
                        continue
                    activity_items.append(
                        {
                            "path": f"arguments.trigger_specs.{index}",
                            "kind": trigger_result["memory_kind"],
                            "operation": trigger_result["operation"],
                        }
                    )
                metadata: dict[str, JsonValue] = {}
                resolution = result.pop("_event_resolution", None)
                if resolution is not None:
                    metadata["event_resolution"] = resolution
                if activity_items:
                    metadata["memory_activity"] = {"items": activity_items}
                return ToolExecutionResult(result=result, metadata=metadata)
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
