"""Deterministic generation-start reporter-memory recall."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import re
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from backend.resources.memory.context_notes import ContextNote
from backend.resources.memory.triggers import (
    FirePolicy,
    Trigger,
    TriggerStatus,
)
from backend.services.memory import (
    HydratedMemoryMatch,
    MemoryKind,
    MemoryRetrievalRequest,
    SearchDocumentQuery,
)
from backend.services.reporter.config import ReportConfig
from backend.services.reporter.runner.models import serialize_model_value
from backend.services.reporter.runner.provider_telemetry import sanitize_provider_error
from backend.services.reporter.runner.tools.memory_presentation import (
    MEMORY_PRESENTATION_BUILDER_VERSION,
    MEMORY_PRESENTATION_SCHEMA_VERSION,
    ContextNoteMemoryContext,
    EventMemoryContext,
    FactMemoryContext,
    MemoryContext,
    MemoryPresentationAdapter,
    StorylineMemoryContext,
    TriggerMemoryContext,
)

if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData
    from backend.services.memory import GenerationMemoryContext


MEMORY_RECALL_SCHEMA_VERSION = 1
MEMORY_RECALL_PLANNER_VERSION = 1
MAX_RECALL_CANDIDATES = 100
MAX_DUE_CALLBACKS = 8
MAX_STANDING_CONTEXT = 8
MAX_LIKELY_RELEVANT = 5
MAX_INTENT_TEXT_LENGTH = 500

RecallStatus = Literal["complete", "partial", "failed"]


class _RecallModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryRecallPrelude(_RecallModel):
    context_type: Literal["automatic_reporter_memory"] = (
        "automatic_reporter_memory"
    )
    due_callbacks: list[TriggerMemoryContext]
    standing_context: list[ContextNoteMemoryContext]
    likely_relevant_memories: list[
        StorylineMemoryContext | FactMemoryContext | EventMemoryContext
    ]
    notice: str | None = None
    partial: bool = False


@dataclass(frozen=True, slots=True)
class MemoryRecallPlan:
    status: RecallStatus
    result: JsonValue
    result_text: str
    metadata: dict[str, JsonValue]
    candidates: tuple[HydratedMemoryMatch, ...]


@dataclass(frozen=True, slots=True)
class _GroupResult:
    root: str
    memories: tuple[MemoryContext, ...]
    candidates: tuple[HydratedMemoryMatch, ...]
    bindings: tuple[dict[str, JsonValue], ...]
    query: SearchDocumentQuery | None
    candidate_count: int
    selected_count: int
    omitted_count: int
    truncated: bool
    error: dict[str, JsonValue] | None = None


class MemoryRecallPlanner:
    """Select and present bounded memory from one pinned generation context."""

    def __init__(
        self,
        memory_context: GenerationMemoryContext,
        data: FrozenLeagueData,
        presentation: MemoryPresentationAdapter,
    ) -> None:
        self._memory_context = memory_context
        self._data = data
        self._presentation = presentation

    def plan(self, config: ReportConfig) -> MemoryRecallPlan:
        season_id = self._memory_context.competition_season_id
        current_week = self._memory_context.week
        knowledge_cutoff_at = self._memory_context.knowledge_cutoff_at
        if season_id is None or current_week is None or knowledge_cutoff_at is None:
            return self._failed_plan(
                RuntimeError("automatic recall requires season, week, and cutoff scope")
            )

        entity_keys, focused_franchises, resolution_diagnostics = (
            self._resolve_team_scope(config)
        )
        due = self._capture_group(
            "due_callbacks",
            lambda: self._due_callbacks(
                season_id=season_id,
                current_week=current_week,
                knowledge_cutoff_at=knowledge_cutoff_at,
            ),
        )
        standing = self._capture_group(
            "standing_context",
            lambda: self._standing_context(
                season_id=season_id,
                focused_franchises=focused_franchises,
            ),
        )
        likely = self._capture_group(
            "likely_relevant_memories",
            lambda: self._likely_relevant(
                config=config,
                season_id=season_id,
                entity_keys=entity_keys,
            ),
        )
        groups = (due, standing, likely)
        errors = {
            group.root: group.error
            for group in groups
            if group.error is not None
        }
        any_memories = any(group.memories for group in groups)
        if errors:
            labels = ", ".join(root.replace("_", " ") for root in errors)
            notice = f"Automatic memory recall was partial; unavailable: {labels}."
        elif not any_memories:
            notice = "No automatic reporter memory matched this generation."
        else:
            notice = None

        prelude = MemoryRecallPrelude(
            due_callbacks=[
                cast(TriggerMemoryContext, memory) for memory in due.memories
            ],
            standing_context=[
                cast(ContextNoteMemoryContext, memory)
                for memory in standing.memories
            ],
            likely_relevant_memories=[
                cast(
                    StorylineMemoryContext
                    | FactMemoryContext
                    | EventMemoryContext,
                    memory,
                )
                for memory in likely.memories
            ],
            notice=notice,
            partial=bool(errors),
        )
        result = cast(
            JsonValue,
            prelude.model_dump(mode="json", exclude_none=True),
        )
        status: RecallStatus = (
            "failed" if len(errors) == len(groups) else "partial" if errors else "complete"
        )
        bindings = [
            binding
            for group in groups
            for binding in group.bindings
        ]
        metadata: dict[str, JsonValue] = {
            "recall_schema_version": MEMORY_RECALL_SCHEMA_VERSION,
            "recall_planner_version": MEMORY_RECALL_PLANNER_VERSION,
            "presentation_schema_version": MEMORY_PRESENTATION_SCHEMA_VERSION,
            "presentation_builder_version": MEMORY_PRESENTATION_BUILDER_VERSION,
            "pinned_revision_id": str(self._memory_context.pinned_revision_id),
            "resolved_scope": {
                "competition_id": str(self._memory_context.competition_id),
                "competition_season_id": str(season_id),
                "week": current_week,
                "knowledge_cutoff_at": knowledge_cutoff_at.isoformat(),
            },
            "team_resolution_diagnostics": cast(
                JsonValue,
                resolution_diagnostics,
            ),
            "groups": cast(
                JsonValue,
                {
                    group.root: self._group_metadata(group)
                    for group in groups
                },
            ),
            "bindings": cast(JsonValue, bindings),
        }
        if errors:
            metadata["errors"] = cast(JsonValue, errors)
        candidates = tuple(
            candidate for group in groups for candidate in group.candidates
        )
        return MemoryRecallPlan(
            status=status,
            result=result,
            result_text=serialize_model_value(result),
            metadata=metadata,
            candidates=candidates,
        )

    def _due_callbacks(
        self,
        *,
        season_id: UUID,
        current_week: int,
        knowledge_cutoff_at: datetime,
    ) -> _GroupResult:
        query = SearchDocumentQuery(
            kinds=(MemoryKind.TRIGGER,),
            statuses=(TriggerStatus.OPEN.value, TriggerStatus.FIRED.value),
            limit=MAX_RECALL_CANDIDATES,
        )
        retrieval = self._memory_context.search(
            MemoryRetrievalRequest(
                query=query,
                expand_stable_references=True,
            )
        )
        due = tuple(
            sorted(
                (
                    match
                    for match in retrieval.matches
                    if self._is_due(
                        match,
                        season_id=season_id,
                        current_week=current_week,
                        knowledge_cutoff_at=knowledge_cutoff_at,
                    )
                ),
                key=self._due_sort_key,
            )
        )
        return self._present_group(
            root="due_callbacks",
            query=query,
            candidates=retrieval.matches,
            selected=due,
            limit=MAX_DUE_CALLBACKS,
        )

    def _standing_context(
        self,
        *,
        season_id: UUID,
        focused_franchises: frozenset[UUID],
    ) -> _GroupResult:
        query = SearchDocumentQuery(
            kinds=(MemoryKind.CONTEXT_NOTE,),
            statuses=("active",),
            limit=MAX_RECALL_CANDIDATES,
        )
        retrieval = self._memory_context.search(MemoryRetrievalRequest(query=query))
        applicable = tuple(
            sorted(
                (
                    match
                    for match in retrieval.matches
                    if self._context_note_applies(
                        match,
                        season_id=season_id,
                        focused_franchises=focused_franchises,
                    )
                ),
                key=self._context_sort_key,
            )
        )
        return self._present_group(
            root="standing_context",
            query=query,
            candidates=retrieval.matches,
            selected=applicable,
            limit=MAX_STANDING_CONTEXT,
        )

    def _likely_relevant(
        self,
        *,
        config: ReportConfig,
        season_id: UUID,
        entity_keys: tuple[str, ...],
    ) -> _GroupResult:
        text = self._intent_text(config)
        if text is None and not entity_keys:
            return _GroupResult(
                root="likely_relevant_memories",
                memories=(),
                candidates=(),
                bindings=(),
                query=None,
                candidate_count=0,
                selected_count=0,
                omitted_count=0,
                truncated=False,
            )
        query = SearchDocumentQuery(
            text=text,
            entity_keys=entity_keys,
            kinds=(MemoryKind.STORYLINE, MemoryKind.FACT, MemoryKind.EVENT),
            statuses=("active", "dormant"),
            competition_season_id=season_id,
            limit=MAX_LIKELY_RELEVANT + 1,
        )
        retrieval = self._memory_context.search(
            MemoryRetrievalRequest(
                query=query,
                expand_exact_references=True,
                expand_stable_references=True,
            )
        )
        return self._present_group(
            root="likely_relevant_memories",
            query=query,
            candidates=retrieval.matches,
            selected=retrieval.matches,
            limit=MAX_LIKELY_RELEVANT,
        )

    def _present_group(
        self,
        *,
        root: str,
        query: SearchDocumentQuery,
        candidates: tuple[HydratedMemoryMatch, ...],
        selected: tuple[HydratedMemoryMatch, ...],
        limit: int,
    ) -> _GroupResult:
        group = self._presentation.present_group(
            selected,
            root=root,
            limit=limit,
        )
        returned = selected[:limit]
        return _GroupResult(
            root=root,
            memories=group.memories,
            candidates=returned,
            bindings=group.bindings,
            query=query,
            candidate_count=len(candidates),
            selected_count=len(selected),
            omitted_count=group.omitted_count,
            truncated=len(selected) > limit,
        )

    def _capture_group(
        self,
        root: str,
        build: Callable[[], _GroupResult],
    ) -> _GroupResult:
        try:
            return build()
        except Exception as exc:
            return _GroupResult(
                root=root,
                memories=(),
                candidates=(),
                bindings=(),
                query=None,
                candidate_count=0,
                selected_count=0,
                omitted_count=0,
                truncated=False,
                error=sanitize_provider_error(exc),
            )

    def _resolve_team_scope(
        self,
        config: ReportConfig,
    ) -> tuple[tuple[str, ...], frozenset[UUID], list[dict[str, JsonValue]]]:
        bias = config.bias_profile
        keys = tuple(
            dict.fromkeys(
                (
                    *config.focus_teams,
                    *(bias.favored_teams if bias else ()),
                    *(bias.disfavored_teams if bias else ()),
                    *config.focus_hints,
                )
            )
        )
        entity_keys: list[str] = []
        franchises: set[UUID] = set()
        diagnostics: list[dict[str, JsonValue]] = []
        for key in keys:
            try:
                resolution = self._data.resolve_roster_identity(key)
            except Exception as exc:
                diagnostics.append(
                    {
                        "roster_key": key,
                        "status": "error",
                        "error": cast(JsonValue, sanitize_provider_error(exc)),
                    }
                )
                continue
            if resolution.status != "resolved":
                diagnostics.append(
                    {"roster_key": key, "status": resolution.status}
                )
                continue
            identity = resolution.identity
            franchises.add(identity.franchise_id)
            entity_keys.extend(
                (
                    f"franchise:{identity.franchise_id}",
                    f"season_roster:{identity.season_roster_id}",
                )
            )
            diagnostics.append(
                {
                    "roster_key": key,
                    "status": "resolved",
                    "franchise_id": str(identity.franchise_id),
                    "season_roster_id": str(identity.season_roster_id),
                }
            )
        return (
            tuple(dict.fromkeys(entity_keys)),
            frozenset(franchises),
            diagnostics,
        )

    @staticmethod
    def _intent_text(config: ReportConfig) -> str | None:
        value = " ".join(
            part.strip()
            for part in (config.custom_instructions, *config.focus_hints)
            if part.strip()
        )
        normalized = re.sub(r"\s+", " ", value).strip()
        return normalized[:MAX_INTENT_TEXT_LENGTH] or None

    @staticmethod
    def _is_due(
        match: HydratedMemoryMatch,
        *,
        season_id: UUID,
        current_week: int,
        knowledge_cutoff_at: datetime,
    ) -> bool:
        trigger = cast(Trigger, match.memory)
        content = trigger.content
        if (
            content.target_competition_season_id is not None
            and content.target_competition_season_id != season_id
        ):
            return False
        if content.fire_policy is FirePolicy.ONE_SHOT:
            if content.status is not TriggerStatus.OPEN:
                return False
        elif content.status not in {TriggerStatus.OPEN, TriggerStatus.FIRED}:
            return False
        if content.target_week is None and content.target_at is None:
            return False
        if content.target_week is not None and content.target_week > current_week:
            return False
        if content.target_at is not None and content.target_at > knowledge_cutoff_at:
            return False
        return True

    @staticmethod
    def _due_sort_key(match: HydratedMemoryMatch) -> tuple[float, float, str]:
        content = cast(Trigger, match.memory).content
        return (
            -float(content.target_week if content.target_week is not None else -1),
            -(
                content.target_at.timestamp()
                if content.target_at is not None
                else float("-inf")
            ),
            str(match.memory.item.item_id),
        )

    @staticmethod
    def _context_note_applies(
        match: HydratedMemoryMatch,
        *,
        season_id: UUID,
        focused_franchises: frozenset[UUID],
    ) -> bool:
        note = cast(ContextNote, match.memory)
        if note.content.status.value != "active":
            return False
        identity = note.note_identity
        if identity.scope == "competition":
            return True
        if identity.scope == "competition_season":
            return identity.competition_season_id == season_id
        return identity.franchise_id in focused_franchises

    @staticmethod
    def _context_sort_key(match: HydratedMemoryMatch) -> tuple[int, str]:
        identity = cast(ContextNote, match.memory).note_identity
        priority = {"franchise": 0, "competition_season": 1, "competition": 2}
        return (priority[identity.scope], str(match.memory.item.item_id))

    @staticmethod
    def _group_metadata(group: _GroupResult) -> JsonValue:
        value: dict[str, JsonValue] = {
            "candidate_count": group.candidate_count,
            "selected_count": group.selected_count,
            "returned_count": len(group.memories),
            "omitted_count": group.omitted_count,
            "truncated": group.truncated,
        }
        if group.query is not None:
            value["resolved_query"] = cast(
                JsonValue,
                group.query.model_dump(mode="json", exclude_none=True),
            )
        if group.error is not None:
            value["error"] = cast(JsonValue, group.error)
        return cast(JsonValue, value)

    def _failed_plan(self, exc: Exception) -> MemoryRecallPlan:
        prelude = MemoryRecallPrelude(
            due_callbacks=[],
            standing_context=[],
            likely_relevant_memories=[],
            notice="Automatic reporter memory was unavailable for this generation.",
            partial=True,
        )
        result = cast(
            JsonValue,
            prelude.model_dump(mode="json", exclude_none=True),
        )
        return MemoryRecallPlan(
            status="failed",
            result=result,
            result_text=serialize_model_value(result),
            metadata={
                "recall_schema_version": MEMORY_RECALL_SCHEMA_VERSION,
                "recall_planner_version": MEMORY_RECALL_PLANNER_VERSION,
                "presentation_schema_version": MEMORY_PRESENTATION_SCHEMA_VERSION,
                "presentation_builder_version": MEMORY_PRESENTATION_BUILDER_VERSION,
                "pinned_revision_id": str(self._memory_context.pinned_revision_id),
                "errors": {
                    "scope": cast(JsonValue, sanitize_provider_error(exc))
                },
                "bindings": [],
            },
            candidates=(),
        )


__all__ = [
    "MAX_DUE_CALLBACKS",
    "MAX_LIKELY_RELEVANT",
    "MAX_RECALL_CANDIDATES",
    "MAX_STANDING_CONTEXT",
    "MEMORY_RECALL_PLANNER_VERSION",
    "MEMORY_RECALL_SCHEMA_VERSION",
    "MemoryRecallPlan",
    "MemoryRecallPlanner",
    "MemoryRecallPrelude",
]
