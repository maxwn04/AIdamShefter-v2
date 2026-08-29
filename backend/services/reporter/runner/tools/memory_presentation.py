"""Model-safe semantic presentation for canonical reporter memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from backend.resources.memory.common.references import EntityReference
from backend.resources.memory.context_notes import ContextNote, ContextNoteContent
from backend.resources.memory.events import EventContent
from backend.resources.memory.events.payloads.matchup import MatchupEventPayload
from backend.resources.memory.events.payloads.trade import (
    BudgetTradeAsset,
    DraftPickTradeAsset,
    PlayerTradeAsset,
    TradeEventPayload,
)
from backend.resources.memory.facts import FactContent
from backend.resources.memory.storylines import StorylineContent
from backend.resources.memory.triggers import TriggerContent
from backend.resources.memory.triggers.conditions.rematch import RematchCondition
from backend.services.memory import (
    ExactReferenceExpansion,
    HydratedMemory,
    HydratedMemoryMatch,
    MemoryKind,
    MemoryRetrievalResult,
    RelatedStorylineExpansion,
    SearchDocumentQuery,
    StableReferenceExpansion,
    StorylineEvidenceExpansion,
    TriggerOriginEventExpansion,
    TriggerTargetStorylineExpansion,
)
from backend.services.reporter.runner.models import ToolExecutionResult


if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData


MEMORY_PRESENTATION_SCHEMA_VERSION = 1
MEMORY_PRESENTATION_BUILDER_VERSION = 1
MAX_PRESENTED_REFERENCES = 3


class _PresentationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SemanticEntity(_PresentationModel):
    label: str
    role: str


class SemanticAsset(_PresentationModel):
    label: str
    direction: str


class SemanticMemorySummary(_PresentationModel):
    kind: MemoryKind
    role: str
    headline: str | None = None
    summary: str
    status: str | None = None


class StorylineMemoryContext(_PresentationModel):
    kind: Literal[MemoryKind.STORYLINE] = MemoryKind.STORYLINE
    headline: str
    summary: str
    status: str
    salience: int
    arc_type: str | None = None
    subjects: list[SemanticEntity]
    tags: list[str]
    callback_condition: str | None = None
    evidence: list[SemanticMemorySummary]
    related_memories: list[SemanticMemorySummary]
    relevant_week: int | None = None


class FactMemoryContext(_PresentationModel):
    kind: Literal[MemoryKind.FACT] = MemoryKind.FACT
    claim: str
    category: str
    numbers: dict[str, JsonValue]
    confidence: str
    status: str
    subjects: list[SemanticEntity]
    relevant_week: int | None = None


class EventMemoryContext(_PresentationModel):
    kind: Literal[MemoryKind.EVENT] = MemoryKind.EVENT
    event_type: str
    headline: str
    summary: str
    salience: int
    confidence: str
    status: str
    participants: list[SemanticEntity]
    assets: list[SemanticAsset]
    relevant_week: int | None = None


class TriggerMemoryContext(_PresentationModel):
    kind: Literal[MemoryKind.TRIGGER] = MemoryKind.TRIGGER
    trigger_type: str
    status: str
    fire_policy: str
    condition_summary: str
    due_week: int | None = None
    due_time: datetime | None = None
    linked_memories: list[SemanticMemorySummary]


class ContextNoteMemoryContext(_PresentationModel):
    kind: Literal[MemoryKind.CONTEXT_NOTE] = MemoryKind.CONTEXT_NOTE
    scope_label: str
    narrative: str
    outlook: str | None = None
    status: str
    tags: list[str]


MemoryContext = Annotated[
    StorylineMemoryContext
    | FactMemoryContext
    | EventMemoryContext
    | TriggerMemoryContext
    | ContextNoteMemoryContext,
    Field(discriminator="kind"),
]


class MemorySearchContext(_PresentationModel):
    memories: list[MemoryContext]
    notice: str | None = None
    truncated: bool = False


@dataclass
class _PresentationState:
    bindings: list[dict[str, JsonValue]]
    omitted_count: int = 0


class MemoryPresentationAdapter:
    """Project hydrated memory into bounded editorial context and hidden metadata."""

    def __init__(self, data: FrozenLeagueData) -> None:
        self._data = data

    def present(
        self,
        retrieval: MemoryRetrievalResult,
        *,
        query: SearchDocumentQuery,
        limit: int,
    ) -> ToolExecutionResult:
        state = _PresentationState(bindings=[])
        selected = retrieval.matches[:limit]
        memories: list[MemoryContext] = []
        for ordinal, match in enumerate(selected):
            omissions: list[str] = []
            binding_index = len(state.bindings)
            state.bindings.append({})
            presented = self._present_match(
                match,
                path=["memories", ordinal],
                state=state,
                omissions=omissions,
            )
            memories.append(presented)
            state.bindings[binding_index] = self._binding(
                match.memory,
                path=["memories", ordinal],
                match=match,
                omissions=omissions,
            )

        truncated = len(retrieval.matches) > limit
        if truncated:
            state.omitted_count += len(retrieval.matches) - limit
        context = MemorySearchContext(
            memories=memories,
            notice=(
                None
                if memories
                else "No relevant memory matched these editorial selectors."
            ),
            truncated=truncated,
        )
        metadata: dict[str, JsonValue] = {
            "presentation_schema_version": MEMORY_PRESENTATION_SCHEMA_VERSION,
            "presentation_builder_version": MEMORY_PRESENTATION_BUILDER_VERSION,
            "pinned_revision_id": str(retrieval.revision_id),
            "resolved_query": cast(
                JsonValue,
                query.model_dump(mode="json", exclude_none=True),
            ),
            "retrieved_count": len(retrieval.matches),
            "returned_count": len(memories),
            "omitted_count": state.omitted_count,
            "truncated": truncated,
            "bindings": cast(JsonValue, state.bindings),
        }
        return ToolExecutionResult(
            result=cast(
                JsonValue,
                context.model_dump(mode="json", exclude_none=True),
            ),
            metadata=metadata,
        )

    def _present_match(
        self,
        match: HydratedMemoryMatch,
        *,
        path: list[str | int],
        state: _PresentationState,
        omissions: list[str],
    ) -> MemoryContext:
        content = match.memory.content
        if isinstance(content, StorylineContent):
            evidence = self._summaries(
                match.exact_references,
                path=path + ["evidence"],
                state=state,
            )
            related = self._summaries(
                match.stable_references,
                path=path + ["related_memories"],
                state=state,
            )
            return StorylineMemoryContext(
                headline=content.headline,
                summary=content.summary,
                status=content.status.value,
                salience=content.salience,
                arc_type=content.arc_type,
                subjects=[
                    SemanticEntity(
                        label=self._entity_label(
                            subject,
                            omissions,
                            f"subjects.{index}.label",
                        ),
                        role=subject.role.value,
                    )
                    for index, subject in enumerate(content.subjects)
                ],
                tags=list(content.tags),
                callback_condition=content.callback_condition,
                evidence=evidence,
                related_memories=related,
                relevant_week=match.week,
            )
        if isinstance(content, FactContent):
            return FactMemoryContext(
                claim=content.claim,
                category=content.category,
                numbers=content.numbers,
                confidence=content.confidence.value,
                status=content.status.value,
                subjects=[
                    SemanticEntity(
                        label=self._entity_label(
                            subject,
                            omissions,
                            f"subjects.{index}.label",
                        ),
                        role=subject.role.value,
                    )
                    for index, subject in enumerate(content.subjects)
                ],
                relevant_week=match.week,
            )
        if isinstance(content, EventContent):
            participants, assets = self._event_details(content, omissions)
            return EventMemoryContext(
                event_type=content.event_type.value,
                headline=content.headline,
                summary=content.summary,
                salience=content.salience,
                confidence=content.confidence.value,
                status=content.status.value,
                participants=participants,
                assets=assets,
                relevant_week=match.week,
            )
        if isinstance(content, TriggerContent):
            return TriggerMemoryContext(
                trigger_type=content.trigger_type.value,
                status=content.status.value,
                fire_policy=content.fire_policy.value,
                condition_summary=self._condition_summary(content, omissions),
                due_week=content.target_week,
                due_time=content.target_at,
                linked_memories=self._summaries(
                    match.stable_references,
                    path=path + ["linked_memories"],
                    state=state,
                ),
            )
        if isinstance(content, ContextNoteContent):
            note = cast(ContextNote, match.memory)
            return ContextNoteMemoryContext(
                scope_label=self._scope_label(note, omissions),
                narrative=content.narrative,
                outlook=content.outlook,
                status=content.status.value,
                tags=list(content.tags),
            )
        raise TypeError(f"unsupported hydrated memory kind: {match.memory.item.kind}")

    def _event_details(
        self,
        content: EventContent,
        omissions: list[str],
    ) -> tuple[list[SemanticEntity], list[SemanticAsset]]:
        details = content.details
        if isinstance(details, MatchupEventPayload):
            return (
                [
                    SemanticEntity(
                        label=self._roster_label(
                            franchise_id=details.winner_franchise_id,
                            omissions=omissions,
                            field="participants.0.label",
                        ),
                        role="winner",
                    ),
                    SemanticEntity(
                        label=self._roster_label(
                            franchise_id=details.loser_franchise_id,
                            omissions=omissions,
                            field="participants.1.label",
                        ),
                        role="loser",
                    ),
                ],
                [],
            )
        if not isinstance(details, TradeEventPayload):
            raise TypeError(f"unsupported event payload: {details.kind}")
        participants = [
            SemanticEntity(
                label=self._roster_label(
                    franchise_id=details.sender_franchise_id,
                    omissions=omissions,
                    field="participants.0.label",
                ),
                role="sender",
            ),
            SemanticEntity(
                label=self._roster_label(
                    franchise_id=details.receiver_franchise_id,
                    omissions=omissions,
                    field="participants.1.label",
                ),
                role="receiver",
            ),
        ]
        assets: list[SemanticAsset] = []
        for index, asset in enumerate(details.assets):
            if isinstance(asset, PlayerTradeAsset):
                label = self._player_label(
                    asset.player_id,
                    omissions,
                    f"assets.{index}.label",
                )
            elif isinstance(asset, DraftPickTradeAsset):
                label = "Draft pick"
                omissions.append(f"assets.{index}.draft_pick_label")
            elif isinstance(asset, BudgetTradeAsset):
                label = f"{asset.amount} FAAB"
            else:
                raise TypeError(f"unsupported trade asset: {asset.kind}")
            assets.append(
                SemanticAsset(label=label, direction=asset.direction.value)
            )
        return participants, assets

    def _condition_summary(
        self,
        content: TriggerContent,
        omissions: list[str],
    ) -> str:
        if isinstance(content.condition, RematchCondition):
            first, second = content.condition.franchise_ids
            return "Rematch between " + " and ".join(
                (
                    self._roster_label(
                        franchise_id=first,
                        omissions=omissions,
                        field="condition_summary.first_team",
                    ),
                    self._roster_label(
                        franchise_id=second,
                        omissions=omissions,
                        field="condition_summary.second_team",
                    ),
                )
            )
        return "Re-evaluate the linked trade"

    def _summaries(
        self,
        expansions: tuple[ExactReferenceExpansion | StableReferenceExpansion, ...],
        *,
        path: list[str | int],
        state: _PresentationState,
    ) -> list[SemanticMemorySummary]:
        summaries: list[SemanticMemorySummary] = []
        for expansion in expansions[:MAX_PRESENTED_REFERENCES]:
            memory = expansion.memory
            role = self._expansion_role(expansion)
            content = memory.content
            headline = getattr(content, "headline", None)
            summary = getattr(content, "summary", None) or getattr(
                content, "claim", None
            )
            if summary is None:
                raise TypeError(f"cannot summarize linked {memory.item.kind} memory")
            result_path = path + [len(summaries)]
            summaries.append(
                SemanticMemorySummary(
                    kind=memory.item.kind,
                    role=role,
                    headline=headline,
                    summary=summary,
                    status=self._status_value(getattr(content, "status", None)),
                )
            )
            state.bindings.append(self._binding(memory, path=result_path))
        state.omitted_count += max(
            0,
            len(expansions) - MAX_PRESENTED_REFERENCES,
        )
        return summaries

    @staticmethod
    def _expansion_role(
        expansion: ExactReferenceExpansion | StableReferenceExpansion,
    ) -> str:
        if isinstance(expansion, StorylineEvidenceExpansion):
            return expansion.reference.role.value
        if isinstance(expansion, RelatedStorylineExpansion):
            return expansion.reference.role.value
        if isinstance(expansion, TriggerTargetStorylineExpansion):
            return "target_storyline"
        if isinstance(expansion, TriggerOriginEventExpansion):
            return "origin_event"
        return "originating_event"

    def _entity_label(
        self,
        subject: EntityReference[Any],
        omissions: list[str],
        field: str,
    ) -> str:
        if subject.display_name:
            return subject.display_name
        kind = getattr(subject, "kind")
        if kind == "franchise":
            return self._roster_label(
                franchise_id=subject.id,
                omissions=omissions,
                field=field,
            )
        if kind == "season_roster":
            return self._roster_label(
                season_roster_id=subject.id,
                omissions=omissions,
                field=field,
            )
        if kind == "player":
            return self._player_label(subject.id, omissions, field)
        fallback = "Season" if kind == "season" else "League manager"
        omissions.append(field)
        return fallback

    def _roster_label(
        self,
        *,
        omissions: list[str],
        field: str,
        franchise_id: UUID | None = None,
        season_roster_id: UUID | None = None,
    ) -> str:
        identity = self._data.get_roster_identity_by_canonical_id(
            franchise_id=franchise_id,
            season_roster_id=season_roster_id,
        )
        if identity is not None:
            return identity.team_name or identity.manager_name or "Team"
        omissions.append(field)
        return "Team"

    def _player_label(
        self,
        player_id: str,
        omissions: list[str],
        field: str,
    ) -> str:
        result = self._data.get_player_summary(player_id)
        if result.get("found"):
            player = result.get("player") or {}
            label = player.get("player_name")
            if isinstance(label, str) and label:
                return label
        omissions.append(field)
        return "Player"

    def _scope_label(
        self,
        memory: ContextNote,
        omissions: list[str],
    ) -> str:
        identity = memory.note_identity
        if identity.scope == "competition":
            return "League"
        if identity.scope == "competition_season":
            return "Season"
        return self._roster_label(
            franchise_id=identity.franchise_id,
            omissions=omissions,
            field="scope_label",
        )

    @staticmethod
    def _status_value(value: Any) -> str | None:
        if value is None:
            return None
        return value.value if hasattr(value, "value") else str(value)

    @staticmethod
    def _binding(
        memory: HydratedMemory,
        *,
        path: list[str | int],
        match: HydratedMemoryMatch | None = None,
        omissions: list[str] | None = None,
    ) -> dict[str, JsonValue]:
        binding: dict[str, JsonValue] = {
            "result_path": cast(JsonValue, path),
            "kind": memory.item.kind.value,
            "item_id": str(memory.item.item_id),
            "version_id": str(memory.version.version_id),
            "expected_item_revision": memory.version.revision_number,
        }
        if len(path) >= 2 and path[0] == "memories" and isinstance(path[1], int):
            binding["result_ordinal"] = path[1]
        if memory.item.agent_key is not None:
            binding["agent_key"] = memory.item.agent_key
        if match is not None:
            binding.update(
                {
                    "score": match.score,
                    "score_components": cast(
                        JsonValue,
                        match.score_components.model_dump(mode="json"),
                    ),
                    "match_reasons": cast(
                        JsonValue,
                        [reason.value for reason in match.match_reasons],
                    ),
                    "matched_entity_keys": cast(
                        JsonValue,
                        list(match.matched_entity_keys),
                    ),
                    "matched_evidence_version_ids": cast(
                        JsonValue,
                        [str(value) for value in match.matched_evidence_version_ids],
                    ),
                    "matched_related_item_ids": cast(
                        JsonValue,
                        [str(value) for value in match.matched_related_item_ids],
                    ),
                    "matched_tags": cast(JsonValue, list(match.matched_tags)),
                }
            )
        if omissions:
            binding["omitted_fields"] = cast(JsonValue, list(omissions))
        return binding
