"""Typed reporter tools over one generation-scoped memory context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
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


MEMORY_TOOL_IMPLEMENTATION_VERSION = "9"
_READ_TOOL = "search_memory"
_WRITE_TOOLS = (
    "save_memory_event",
    "upsert_storyline_memory_card",
    "save_storyline_trigger",
    "update_memory_callback",
    "save_team_context",
    "save_league_note",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RematchTriggerInput(_StrictModel):
    roster_keys: tuple[str, str]


class TradeEvaluationTriggerInput(_StrictModel):
    pass


class ScheduledReviewTriggerInput(_StrictModel):
    review_question: str = Field(min_length=1)


class SearchMemoryArgs(_StrictModel):
    season: int | None = Field(default=None, ge=1900, le=9999, description="Optional season year; omitted searches all available seasons.")
    text: str | None = Field(
        default=None,
        description=(
            "Optional focused editorial concept, name, or phrase. Search uses "
            "structured, lexical and available semantic matching, including older "
            "narrative versions. Keep each call centered on one continuity question."
        ),
    )
    team_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Hard team filter: franchise:<UUID> selectors from memory cards, "
            "or team names/roster IDs in the selected season. Matches any selected franchise."
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
        default=False,
        description=(
            "Optionally include evidence summaries; prefer inspect_memory for selected results."
        ),
    )
    include_related: bool = Field(
        default=False,
        description=(
            "Optionally include related summaries; prefer inspect_memory for selected results."
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


class InspectMemoryArgs(_StrictModel):
    memory_handle: str = Field(min_length=1)
    view: Literal["detail", "history", "evidence"] = "detail"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=5, ge=1, le=20)


class UpdateMemoryCallbackArgs(_StrictModel):
    update_handle: str = Field(min_length=1)
    action: Literal["resolve", "reschedule", "defer"]
    reason: str = Field(min_length=1)
    target_week: int | None = Field(default=None, ge=0)


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
    subjects_mode: Literal["merge", "replace"] = Field(default="merge", description="Merge preserves existing subjects and roles. Replace explicitly removes omitted subjects; empty replacement clears all.")
    evidence_event_ids: list[str] = Field(default_factory=list)
    trigger_specs: list[dict[str, JsonValue]] = Field(default_factory=list)
    resolution_summary: str | None = None

    @model_validator(mode="after")
    def validate_selector(self) -> UpsertStorylineMemoryCardArgs:
        if (self.id is None) == (self.update_handle is None):
            raise ValueError("Use id to create a new arc OR update_handle from recalled memory to update it")
        return self


class SaveStorylineTriggerArgs(_StrictModel):
    trigger_type: Literal["rematch", "trade_evaluation", "scheduled_review"] | None = None
    id: str | None = Field(default=None, min_length=1)
    update_handle: str | None = Field(default=None, min_length=1)
    storyline_id: str | None = Field(default=None, min_length=1)
    event_id: str | None = Field(default=None, min_length=1)
    target_week: int | None = Field(default=None, ge=0)
    condition: RematchTriggerInput | ScheduledReviewTriggerInput | TradeEvaluationTriggerInput | None = None
    fire_policy: Literal["one_shot", "recurring", "until_resolved"] = "one_shot"
    status: Literal["open", "fired", "expired", "resolved"] = "open"
    resolution_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selector(self) -> SaveStorylineTriggerArgs:
        if self.id is not None and self.update_handle is not None:
            raise ValueError("Use id or a recalled trigger update_handle, not both")
        return self

    @model_validator(mode="before")
    @classmethod
    def reject_misplaced_event(cls, value: Any) -> Any:
        if isinstance(value, dict) and isinstance(value.get("condition"), dict):
            if "event_id" in value["condition"]:
                raise ValueError("event_id belongs at the top level; use scheduled_review with review_question for general follow-ups")
        return value


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
        "revision across available seasons. Text and tags are discovery signals; team, season, kinds, statuses, "
        "and inclusive week bounds narrow the results. Returned memories contain "
        "semantic writing context rather than storage identifiers. Treat every "
        "memory as a research lead and verify material claims against frozen data.",
        SearchMemoryArgs,
    ),
    _tool("inspect_memory", "Inspect a selected memory's detail, prior versions, or linked evidence. "
          "Use bounded pages; prior versions and evidence are read-only reporter memory, not verified current facts.", InspectMemoryArgs),
    _tool("update_memory_callback", "Resolve, reschedule, or defer one recalled callback using its handle and a reason. "
          "Reschedule needs a future target_week. Defer leaves it open and uninvestigated. "
          "No article mention or separate completion receipt is required.", UpdateMemoryCallbackArgs),
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
        "Save all supporting events first, then update each storyline once with their "
        "evidence_event_ids. Only exact retries are allowed after selection in this run. "
        "Do not invent a new key for a recalled arc.",
        UpsertStorylineMemoryCardArgs,
    ),
    _tool(
        "save_storyline_trigger",
        "Schedule an editorial review with trigger_type=scheduled_review, storyline_id, "
        "target_week and condition.review_question. Due means review requested, not an "
        "event occurred or an article mention is required. Default one_shot. Resolve a "
        "recalled trigger using update_handle, status=resolved and resolution_reason; "
        "reschedule the same handle with status=open and a new target_week. "
        "Omitted update fields are preserved. Trade evaluations require a source-backed "
        "trade event_id at the top level and empty condition. A rematch requires a "
        "source-backed prior matchup event_id and matching condition.roster_keys; its "
        "target_week is a review date, not proof of a scheduled meeting. Use "
        "scheduled_review whenever the event condition is unsupported.",
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


_spec_order = (_READ_TOOL, "inspect_memory", *_WRITE_TOOLS)
MEMORY_TOOL_SPECS.sort(key=lambda spec: _spec_order.index(spec["function"]["name"]))


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
        self._callback_dispositions: dict[str, dict[str, str]] = {}
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
        dispositions = self._callback_dispositions.copy()
        try:
            with self._memory_context.proposal_savepoint():
                yield
        except BaseException:
            self._completed_semantic_saves = completed
            self._local_agent_refs = local_refs
            self._proposed_item_ids = proposed_ids
            self._callback_dispositions = dispositions
            raise

    def build_recall(self, config: ReportConfig) -> MemoryRecallPlan:
        plan = self._recall.plan(config)
        self._cache_pinned_candidates(plan.candidates)
        return plan

    def _season_bounds(self) -> dict[UUID, int] | None:
        if not hasattr(self._data, "available_seasons"):
            return None
        return {season.competition_season_id: min(season.through_week, self._memory_context.week or season.through_week)
                if season.role == "primary" else season.through_week
                for season in self._data.available_seasons()}

    def search(self, arguments: SearchMemoryArgs) -> ToolExecutionResult:
        entity_keys: list[str] = []
        for roster_key in arguments.team_keys:
            identity = self._resolve_search_roster(roster_key, arguments.season)
            entity_keys.append(f"franchise:{identity.franchise_id}")
            entity_keys.append(f"roster:{identity.season_roster_id}")
            if arguments.season is None and hasattr(self._data, "available_seasons"):
                for scope in self._data.available_seasons():
                    alias = self._data.get_roster_identity_by_canonical_id(
                        franchise_id=identity.franchise_id, season=scope.season_year)
                    if alias is not None:
                        entity_keys.append(f"roster:{alias.season_roster_id}")
        query = SearchDocumentQuery(
            text=arguments.text,
            required_entity_keys=tuple(dict.fromkeys(entity_keys)),
            tags=tuple(arguments.tags), kinds=tuple(arguments.kinds),
            statuses=tuple(arguments.statuses), season=arguments.season,
            week_from=arguments.week_from, week_to=arguments.week_to,
            allowed_season_weeks=self._season_bounds(), limit=arguments.limit + 1,
            include_history=bool(arguments.text),
        )
        result = self._memory_context.search(MemoryRetrievalRequest(
            query=query, expand_exact_references=arguments.include_evidence,
            expand_stable_references=arguments.include_related,
        ))
        self._cache_pinned_candidates(result.matches)
        return self._presentation.present(result, query=query, limit=arguments.limit,
                                          compact=not (arguments.include_evidence or arguments.include_related))

    def inspect(self, arguments: InspectMemoryArgs) -> ToolExecutionResult:
        memory = self._presentation.resolve_handle(arguments.memory_handle)
        if memory is None:
            raise MemoryToolInputError("unknown_memory_handle", "Select a memory_handle from search or automatic context.")
        result = self._memory_context.inspect(memory, view=arguments.view,
            offset=arguments.offset, limit=arguments.limit,
            allowed_season_weeks=self._season_bounds())
        group = self._presentation.present_group(result.matches, root="memories", limit=arguments.limit,
            compact=arguments.view != "detail",
            read_only=arguments.view != "detail" or self._presentation.is_read_only(arguments.memory_handle))
        return ToolExecutionResult(result={
            "memories": [card.model_dump(mode="json", exclude_none=True) for card in group.memories],
            "view": arguments.view, "has_more": result.has_more,
            "next_offset": arguments.offset + len(group.memories) if result.has_more else None,
        }, metadata={"bindings": list(group.bindings), "pinned_revision_id": str(result.revision_id)})

    def _require_writable_handle(self, handle: str) -> None:
        if self._presentation.is_read_only(handle):
            raise MemoryToolInputError("read_only_memory_handle", "Historical versions and evidence inspection handles are read-only. Search for the current card to update it.")

    def _resolve_search_roster(self, key: str, season: int | None) -> Any:
        if season is not None or not hasattr(self._data, "available_seasons"):
            return self._resolve_roster(key, season=season)
        # Roster numbers are season-relative convenience selectors; names and
        # durable franchise selectors may discover a renamed historical team.
        if key.isdigit():
            return self._resolve_roster(key)
        matches: dict[UUID, Any] = {}
        for scope in self._data.available_seasons():
            try:
                identity = self._resolve_roster(key, season=scope.season_year)
            except MemoryToolInputError as error:
                if error.code != "roster_not_found":
                    raise
                continue
            matches.setdefault(identity.franchise_id, identity)
        if len(matches) > 1:
            raise MemoryToolInputError("roster_ambiguous", "This name identifies different franchises across seasons; select a season or a franchise key from a memory card.")
        if not matches:
            raise MemoryToolInputError("roster_not_found", "No matching team exists in the available frozen seasons.")
        return next(iter(matches.values()))

    def _cache_pinned_candidates(
        self,
        matches: tuple[HydratedMemoryMatch, ...],
    ) -> None:
        self._pinned_agent_candidates.update(
            ((match.memory.item.kind, match.memory.item.agent_key), match.memory)
            for match in matches
            if match.memory.item.agent_key is not None and match.current_at_pin
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
            self._require_writable_handle(arguments.update_handle)
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
            if arguments.subjects_mode == "merge":
                existing_subjects = {(subject.kind, subject.id): subject.model_dump(mode="python")
                                     for subject in candidate.content.subjects}
                for subject in subjects:
                    existing_subjects.setdefault((subject["kind"], subject["id"]), subject)
                values["subjects"] = list(existing_subjects.values())
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
        candidate = None
        if arguments.update_handle:
            self._require_writable_handle(arguments.update_handle)
            candidate = self._presentation.resolve_handle(arguments.update_handle)
            if candidate is None or candidate.item.kind is not MemoryKind.TRIGGER:
                raise MemoryToolInputError("unknown_memory_handle", "Use the memory_handle returned on the existing trigger.")
        elif arguments.id:
            candidate = self._agent_candidate(MemoryKind.TRIGGER, arguments.id)
        trigger_id = (candidate.item.agent_key or arguments.update_handle) if candidate else arguments.id or f"trigger_{uuid4().hex[:12]}"
        values = candidate.content.model_dump(mode="python") if candidate else {}
        trigger_type = arguments.trigger_type or values.get("trigger_type")
        if trigger_type is None:
            raise MemoryToolInputError("missing_trigger_type", "Use scheduled_review for a general storyline follow-up.")
        season_id = self._memory_context.competition_season_id
        if candidate and (candidate.version.competition_season_id not in (None, season_id)
                          or values.get("target_competition_season_id") not in (None, season_id)):
            raise MemoryToolInputError("cross_season_update_unsupported", "This trigger targets another season; cross-season rescheduling is not supported.")
        fields = arguments.model_fields_set
        values["trigger_type"] = trigger_type
        for argument_field, content_field in (
            ("target_week", "target_week"), ("fire_policy", "fire_policy"),
            ("resolution_reason", "resolution_reason"),
        ):
            if candidate is None or argument_field in fields:
                values[content_field] = getattr(arguments, argument_field)
        if candidate is None or "status" in fields:
            values["status"] = "satisfied" if arguments.status == "resolved" else arguments.status
        if candidate is None:
            values["target_competition_season_id"] = season_id
        if arguments.storyline_id:
            storyline = self._agent_reference(MemoryKind.STORYLINE, arguments.storyline_id)
            if storyline is None:
                raise MemoryToolInputError("unknown_storyline", "Save the storyline successfully first, then use its returned id or recalled handle.")
            values["target_storyline_item_id"] = storyline.item_id
        if arguments.event_id:
            event = self._agent_reference(MemoryKind.EVENT, arguments.event_id)
            if event is None:
                raise MemoryToolInputError("unknown_event", "Save the source-backed event first; use scheduled_review if this is a general follow-up.")
            values["origin_event_item_id"] = event.item_id
        if "condition" in fields or candidate is None:
            condition = arguments.condition or TradeEvaluationTriggerInput()
            if trigger_type == "scheduled_review" and isinstance(condition, ScheduledReviewTriggerInput):
                values["condition"] = {"kind": "scheduled_review", "review_question": condition.review_question}
            elif trigger_type == "rematch" and isinstance(condition, RematchTriggerInput):
                rosters = [self._resolve_roster(key) for key in condition.roster_keys]
                values["condition"] = {"kind": "rematch", "franchise_ids": [r.franchise_id for r in rosters]}
            elif trigger_type == "trade_evaluation" and isinstance(condition, TradeEvaluationTriggerInput):
                values["condition"] = {"kind": "trade_evaluation"}
            else:
                raise MemoryToolInputError("invalid_trigger_condition", "Condition does not match trigger_type. General follow-ups use scheduled_review with condition.review_question.")
        if trigger_type == "scheduled_review":
            if arguments.event_id:
                raise MemoryToolInputError("unexpected_review_event", "Scheduled reviews link a storyline, not an event; omit event_id.")
            values["origin_event_item_id"] = None
            values["target_competition_season_id"] = season_id
        elif values["status"] in {"open", "fired"}:
            if arguments.event_id:
                source = self._selected_event_content(arguments.event_id)
            elif candidate and candidate.content.origin_event_item_id:
                inspected = self._memory_context.inspect(candidate, view="evidence", limit=20,
                    allowed_season_weeks=self._season_bounds())
                source = next((match.memory.content for match in inspected.matches
                    if match.memory.item.item_id == candidate.content.origin_event_item_id
                    and match.memory.item.kind is MemoryKind.EVENT), None)
            else:
                raise MemoryToolInputError("missing_trigger_origin", "Provide a source-backed event_id for a new event callback; unchanged origins are preserved on updates.")
            expected = "trade" if trigger_type == "trade_evaluation" else "matchup"
            if source is None or source.event_type.value != expected or source.confidence.value != "source_backed":
                raise MemoryToolInputError("invalid_trigger_origin", f"This callback requires a source-backed {expected} event. Use scheduled_review for an unsupported or general follow-up.")
            if trigger_type == "rematch":
                participants = {source.details.winner_franchise_id, source.details.loser_franchise_id}
                if set(values["condition"]["franchise_ids"]) != participants:
                    raise MemoryToolInputError("invalid_trigger_origin", "Rematch teams must match the source matchup participants. Use scheduled_review for other follow-ups.")
        canonical = TriggerContent.model_validate(values)
        result = self._upsert(
            MemoryKind.TRIGGER, trigger_id, canonical, context=context, candidate=candidate,
            create=self._memory_context.propose_trigger,
            replace=self._memory_context.replace_trigger,
        )
        if candidate:
            handle = arguments.update_handle or self._presentation.handle_for(candidate)
            if canonical.status.value == "satisfied":
                self._callback_dispositions[handle] = {"action": "resolve", "reason": canonical.resolution_reason or "Resolved"}
            elif canonical.target_week != candidate.content.target_week:
                self._callback_dispositions[handle] = {"action": "reschedule", "reason": arguments.resolution_reason or "Review rescheduled"}
        return {**result, "id": trigger_id, "update_handle": arguments.update_handle,
                "trigger_type": canonical.trigger_type.value, "status": canonical.status.value,
                "review_notice": "Review requested; verify evidence. An article mention is optional."}

    def update_memory_callback(self, context: ToolContext, arguments: UpdateMemoryCallbackArgs) -> dict[str, Any]:
        self._require_writable_handle(arguments.update_handle)
        candidate = self._presentation.resolve_handle(arguments.update_handle)
        if candidate is None or candidate.item.kind is not MemoryKind.TRIGGER:
            raise MemoryToolInputError("unknown_memory_handle", "Select the callback's memory_handle.")
        if candidate.version.competition_season_id not in (None, self._memory_context.competition_season_id) or candidate.content.target_competition_season_id not in (None, self._memory_context.competition_season_id):
            raise MemoryToolInputError("cross_season_update_unsupported", "Historical callbacks cannot be updated.")
        if arguments.action == "defer":
            if any(proposal.item_id == candidate.item.item_id for proposal in self._memory_context.proposal_snapshot()):
                raise MemoryToolInputError("callback_already_updated", "This callback already has a selected update this run; keep its successful disposition.")
            if candidate.content.status.value not in {"open", "fired"}:
                raise MemoryToolInputError("callback_not_open", "Only open callbacks can be deferred.")
            if arguments.target_week is not None:
                raise MemoryToolInputError("unexpected_target_week", "Use reschedule to set a new review week.")
            result = {"ok": True, "saved": False, "status": candidate.content.status.value,
                      "outcome": "uninvestigated", "update_handle": arguments.update_handle}
        else:
            values: dict[str, Any] = {"update_handle": arguments.update_handle,
                "status": "resolved" if arguments.action == "resolve" else "open",
                "resolution_reason": arguments.reason if arguments.action == "resolve" else None}
            if arguments.action == "reschedule":
                if arguments.target_week is None or arguments.target_week <= (self._memory_context.week or 0):
                    raise MemoryToolInputError("future_review_week_required", "Reschedule requires target_week after the current reporting week.")
                values["target_week"] = arguments.target_week
            elif arguments.target_week is not None:
                raise MemoryToolInputError("unexpected_target_week", "Resolve does not accept a new target_week.")
            result = self.save_storyline_trigger(context, SaveStorylineTriggerArgs.model_validate(values))
        self._callback_dispositions[arguments.update_handle] = {"action": arguments.action, "reason": arguments.reason}
        return result

    def _selected_event_content(self, event_key: str) -> EventContent | None:
        reference = self._agent_reference(MemoryKind.EVENT, event_key)
        if reference is None:
            return None
        for proposal in self._memory_context.proposal_snapshot():
            if proposal.version_id == reference.version_id and isinstance(proposal.content, EventContent):
                return proposal.content
        candidate = self._presentation.resolve_handle(event_key) or self._agent_candidate(MemoryKind.EVENT, event_key)
        return candidate.content if candidate is not None else None

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
                    f"{kind.value}:{agent_key} already changed in this run. "
                    "Only exact retries are allowed. Save all supporting events first, "
                    "then update the storyline once with their returned IDs.",
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

    def _resolve_roster(self, roster_key: str, *, season: int | None = None) -> Any:
        scope = {"season": season} if season is not None else {}
        if roster_key.startswith("franchise:"):
            try:
                franchise_id = UUID(roster_key.removeprefix("franchise:"))
            except ValueError:
                raise MemoryToolInputError("invalid_team_selector", "Copy the complete franchise selector from a memory card.") from None
            identity = self._data.get_roster_identity_by_canonical_id(franchise_id=franchise_id, **scope)
            if identity is None:
                raise MemoryToolInputError("roster_not_found", "This franchise is not present in the selected frozen season.")
            return identity
        resolution = self._data.resolve_roster_identity(roster_key, **scope)
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
        if local is not None and not self._presentation.is_read_only(agent_key):
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

    def inspect_memory(**kwargs: Any) -> ToolExecutionResult | dict[str, Any]:
        try:
            return adapter.inspect(InspectMemoryArgs.model_validate(kwargs))
        except (ValidationError, MemoryToolInputError, ValueError) as error:
            if isinstance(error, (ValidationError, MemoryToolInputError)):
                return _safe_error(error)
            return _safe_error(MemoryToolInputError("memory_inspection_unavailable", str(error)))

    specs_by_name = {spec["function"]["name"]: spec for spec in MEMORY_TOOL_SPECS}
    registry.register("inspect_memory", inspect_memory, specs_by_name["inspect_memory"], MEMORY_TOOL_IMPLEMENTATION_VERSION)
    write_models: dict[str, type[BaseModel]] = {
        "update_memory_callback": UpdateMemoryCallbackArgs,
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
                if context.memory_closeout is not None:
                    for handle, disposition in adapter._callback_dispositions.items():
                        context.memory_closeout.record_callback_disposition(handle=handle, **disposition)
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
