from __future__ import annotations

from typing import Annotated, Literal, TypeAlias, cast
from uuid import UUID

from pydantic import Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.resources.memory.common.errors import (
    SearchProjectionHydrationError,
    TargetNotFoundError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes import ContextNote, ContextNoteManager
from backend.resources.memory.events import Event, EventManager
from backend.resources.memory.facts import Fact, FactManager
from backend.resources.memory.search_documents import (
    SearchDocumentCandidate,
    SearchDocumentManager,
    SearchDocumentQuery,
    SearchMatchReason,
    SearchScoreComponents,
)
from backend.resources.memory.storylines import (
    EvidenceRef,
    RelatedStorylineRef,
    Storyline,
    StorylineManager,
)
from backend.resources.memory.triggers import Trigger, TriggerManager


HydratedMemory: TypeAlias = Fact | Event | Storyline | Trigger | ContextNote


class StorylineEvidenceExpansion(ContractModel):
    kind: Literal["storyline_evidence"] = "storyline_evidence"
    reference: EvidenceRef
    memory: Fact | Event

    @model_validator(mode="after")
    def validate_target(self) -> StorylineEvidenceExpansion:
        if self.reference.version_id != self.memory.version.version_id:
            raise ValueError("storyline evidence expansion targets the wrong version")
        if self.reference.kind != self.memory.item.kind.value:
            raise ValueError("storyline evidence expansion targets the wrong kind")
        return self


class FactOriginatingEventExpansion(ContractModel):
    kind: Literal["fact_originating_event"] = "fact_originating_event"
    version_id: UUID
    memory: Event

    @model_validator(mode="after")
    def validate_target(self) -> FactOriginatingEventExpansion:
        if self.version_id != self.memory.version.version_id:
            raise ValueError(
                "fact originating-event expansion targets the wrong version"
            )
        return self


ExactReferenceExpansion = Annotated[
    StorylineEvidenceExpansion | FactOriginatingEventExpansion,
    Field(discriminator="kind"),
]


class RelatedStorylineExpansion(ContractModel):
    kind: Literal["related_storyline"] = "related_storyline"
    reference: RelatedStorylineRef
    memory: Storyline

    @model_validator(mode="after")
    def validate_target(self) -> RelatedStorylineExpansion:
        if self.reference.item_id != self.memory.item.item_id:
            raise ValueError("related-storyline expansion targets the wrong item")
        return self


class TriggerTargetStorylineExpansion(ContractModel):
    kind: Literal["trigger_target_storyline"] = "trigger_target_storyline"
    item_id: UUID
    memory: Storyline

    @model_validator(mode="after")
    def validate_target(self) -> TriggerTargetStorylineExpansion:
        if self.item_id != self.memory.item.item_id:
            raise ValueError("trigger storyline expansion targets the wrong item")
        return self


class TriggerOriginEventExpansion(ContractModel):
    kind: Literal["trigger_origin_event"] = "trigger_origin_event"
    item_id: UUID
    memory: Event

    @model_validator(mode="after")
    def validate_target(self) -> TriggerOriginEventExpansion:
        if self.item_id != self.memory.item.item_id:
            raise ValueError("trigger event expansion targets the wrong item")
        return self


StableReferenceExpansion = Annotated[
    RelatedStorylineExpansion
    | TriggerTargetStorylineExpansion
    | TriggerOriginEventExpansion,
    Field(discriminator="kind"),
]


class MemoryRetrievalRequest(ContractModel):
    query: SearchDocumentQuery
    expand_exact_references: bool = False
    expand_stable_references: bool = False


class HydratedMemoryMatch(ContractModel):
    memory: HydratedMemory
    week: SkipJsonSchema[int | None] = Field(
        default=None,
        ge=0,
        strict=True,
        exclude=True,
    )
    score: float = Field(ge=0)
    score_components: SearchScoreComponents
    matched_entity_keys: tuple[NonBlankStr, ...] = ()
    matched_evidence_version_ids: tuple[UUID, ...] = ()
    matched_related_item_ids: tuple[UUID, ...] = ()
    matched_tags: tuple[NonBlankStr, ...] = ()
    match_reasons: tuple[SearchMatchReason, ...]
    exact_references: tuple[ExactReferenceExpansion, ...] = ()
    stable_references: tuple[StableReferenceExpansion, ...] = ()


class MemoryRetrievalResult(ContractModel):
    competition_id: UUID
    revision_id: UUID
    matches: tuple[HydratedMemoryMatch, ...]

    @model_validator(mode="after")
    def validate_scope(self) -> MemoryRetrievalResult:
        if any(
            match.memory.item.competition_id != self.competition_id
            for match in self.matches
        ):
            raise ValueError("retrieval matches must belong to the result competition")
        return self


class MemoryInspectionResult(MemoryRetrievalResult):
    """One bounded page of selected canonical memory or its relationships."""

    has_more: bool = False


class MemoryRetrievalService:
    """Hydrate revision-grounded search candidates from canonical resources."""

    def __init__(
        self,
        *,
        search_documents: SearchDocumentManager,
        facts: FactManager,
        events: EventManager,
        storylines: StorylineManager,
        triggers: TriggerManager,
        context_notes: ContextNoteManager,
    ) -> None:
        self._search_documents = search_documents
        self._facts = facts
        self._events = events
        self._storylines = storylines
        self._triggers = triggers
        self._context_notes = context_notes

    def search(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        request: MemoryRetrievalRequest,
    ) -> MemoryRetrievalResult:
        """Search and return canonical typed memory at one pinned revision."""

        if competition_id != self._search_documents.competition_id:
            raise ValueError("retrieval request is outside the service competition")

        exact_cache: dict[tuple[MemoryKind, UUID], HydratedMemory] = {}
        visible_cache: dict[tuple[MemoryKind, UUID, UUID], Event | Storyline] = {}
        candidates = self._search_documents.search(revision_id, request.query)
        matches: list[HydratedMemoryMatch] = []
        for candidate in candidates:
            try:
                memory = self._hydrate_exact(
                    candidate.kind,
                    candidate.version_id,
                    exact_cache,
                )
            except TargetNotFoundError as error:
                raise SearchProjectionHydrationError(
                    candidate.version_id,
                    candidate.kind,
                    "the projected version is absent from its typed canonical resource",
                ) from error
            self._validate_candidate(candidate, memory, competition_id)
            matches.append(
                HydratedMemoryMatch(
                    memory=memory,
                    week=candidate.week,
                    score=candidate.score,
                    score_components=candidate.score_components,
                    matched_entity_keys=candidate.matched_entity_keys,
                    matched_evidence_version_ids=(
                        candidate.matched_evidence_version_ids
                    ),
                    matched_related_item_ids=candidate.matched_related_item_ids,
                    matched_tags=candidate.matched_tags,
                    match_reasons=candidate.match_reasons,
                    exact_references=(
                        self._expand_exact(
                            memory, exact_cache, revision_id, request.query,
                        )
                        if request.expand_exact_references
                        else ()
                    ),
                    stable_references=(
                        self._expand_stable(
                            memory,
                            revision_id,
                            visible_cache,
                            request.query,
                        )
                        if request.expand_stable_references
                        else ()
                    ),
                )
            )
        return MemoryRetrievalResult(
            competition_id=competition_id,
            revision_id=revision_id,
            matches=tuple(matches),
        )

    def inspect(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        memory: HydratedMemory,
        view: Literal["detail", "history", "evidence"] = "detail",
        offset: int = 0,
        limit: int = 20,
        scope: SearchDocumentQuery | None = None,
    ) -> MemoryInspectionResult:
        """Inspect selected canonical content without broadening its history pin."""
        if competition_id != self._search_documents.competition_id:
            raise ValueError("inspection request is outside the service competition")
        if memory.item.competition_id != competition_id:
            raise ValueError("selected memory belongs to another competition")
        if view not in ("detail", "history", "evidence"):
            raise ValueError("unknown memory inspection view")
        if (
            type(offset) is not int or type(limit) is not int
            or offset < 0 or not 1 <= limit <= 100
        ):
            raise ValueError("inspection requires offset >= 0 and limit in 1..100")
        selected_rows = self._search_documents.inspect_versions(
            revision_id, memory.version.version_id, scope=scope,
        )
        version_id, kind, _ = selected_rows[0]
        cache: dict[tuple[MemoryKind, UUID], HydratedMemory] = {}
        selected = self._hydrate_exact(kind, version_id, cache)
        if (
            selected.item.item_id != memory.item.item_id
            or selected.item.kind != memory.item.kind
        ):
            raise ValueError("selected memory identity differs from canonical memory")
        if view == "evidence":
            rows = self._inspection_evidence(selected, revision_id, scope)
            page = rows[offset : offset + limit + 1]
        else:
            page = self._search_documents.inspect_versions(
                revision_id, version_id, history=view == "history",
                offset=offset, limit=limit + 1, scope=scope,
            )
        return MemoryInspectionResult(
            competition_id=competition_id, revision_id=revision_id,
            matches=tuple(
                HydratedMemoryMatch(
                    memory=self._hydrate_exact(row_kind, row_id, cache), week=week,
                    score=0, score_components=SearchScoreComponents(),
                    match_reasons=(SearchMatchReason.BROWSE_MATCH,),
                )
                for row_id, row_kind, week in page[:limit]
            ),
            has_more=len(page) > limit,
        )

    def _inspection_evidence(
        self,
        memory: HydratedMemory,
        revision_id: UUID,
        scope: SearchDocumentQuery | None,
    ) -> tuple[tuple[UUID, MemoryKind, int | None], ...]:
        """Resolve one-hop references; validate temporal eligibility before hydration."""
        exact_ids: list[UUID] = []
        stable_targets: list[UUID] = []
        if isinstance(memory, Fact):
            exact_ids.extend(memory.content.originating_event_version_ids)
        elif isinstance(memory, Storyline):
            exact_ids.extend(
                reference.version_id for reference in memory.content.evidence
            )
            stable_targets.extend(
                reference.item_id for reference in memory.content.related_storylines
            )
        elif isinstance(memory, Trigger):
            if memory.content.target_storyline_item_id is not None:
                stable_targets.append(memory.content.target_storyline_item_id)
            if memory.content.origin_event_item_id is not None:
                stable_targets.append(memory.content.origin_event_item_id)
        for item_id in stable_targets:
            target_id = self._search_documents.visible_reference_version(
                revision_id, item_id,
            )
            if target_id is not None:
                exact_ids.append(target_id)
        rows: list[tuple[UUID, MemoryKind, int | None]] = []
        for target_id in dict.fromkeys(exact_ids):
            try:
                rows.extend(self._search_documents.inspect_versions(
                    revision_id, target_id, scope=scope,
                ))
            except TargetNotFoundError:
                continue
        return tuple(rows)

    def _hydrate_exact(
        self,
        kind: MemoryKind,
        version_id: UUID,
        cache: dict[tuple[MemoryKind, UUID], HydratedMemory],
    ) -> HydratedMemory:
        key = (kind, version_id)
        if key in cache:
            return cache[key]
        if kind is MemoryKind.FACT:
            memory: HydratedMemory = self._facts.exact(version_id)
        elif kind is MemoryKind.EVENT:
            memory = self._events.exact(version_id)
        elif kind is MemoryKind.STORYLINE:
            memory = self._storylines.exact(version_id)
        elif kind is MemoryKind.TRIGGER:
            memory = self._triggers.exact(version_id)
        else:
            memory = self._context_notes.exact(version_id)
        cache[key] = memory
        return memory

    def _hydrate_visible(
        self,
        kind: MemoryKind,
        item_id: UUID,
        revision_id: UUID,
        cache: dict[tuple[MemoryKind, UUID, UUID], Event | Storyline],
    ) -> Event | Storyline:
        key = (kind, item_id, revision_id)
        if key in cache:
            return cache[key]
        if kind is MemoryKind.EVENT:
            memory: Event | Storyline = self._events.visible_at(
                item_id,
                revision_id,
            )
        elif kind is MemoryKind.STORYLINE:
            memory = self._storylines.visible_at(item_id, revision_id)
        else:
            raise ValueError(f"{kind.value} is not a stable retrieval target")
        cache[key] = memory
        return memory

    def _expand_exact(
        self,
        memory: HydratedMemory,
        cache: dict[tuple[MemoryKind, UUID], HydratedMemory],
        revision_id: UUID,
        scope: SearchDocumentQuery,
    ) -> tuple[ExactReferenceExpansion, ...]:
        if memory.item.kind is MemoryKind.FACT:
            fact = cast(Fact, memory)
            return tuple(
                FactOriginatingEventExpansion(
                    version_id=version_id,
                    memory=self._require_event(
                        self._hydrate_exact(MemoryKind.EVENT, version_id, cache)
                    ),
                )
                for version_id in fact.content.originating_event_version_ids
                if self._reference_eligible(version_id, revision_id, scope)
            )
        if memory.item.kind is MemoryKind.STORYLINE:
            storyline = cast(Storyline, memory)
            return tuple(
                StorylineEvidenceExpansion(
                    reference=reference,
                    memory=self._require_evidence(
                        reference.kind,
                        self._hydrate_exact(
                            MemoryKind(reference.kind),
                            reference.version_id,
                            cache,
                        ),
                    ),
                )
                for reference in storyline.content.evidence
                if self._reference_eligible(reference.version_id, revision_id, scope)
            )
        return ()

    def _expand_stable(
        self,
        memory: HydratedMemory,
        revision_id: UUID,
        cache: dict[tuple[MemoryKind, UUID, UUID], Event | Storyline],
        scope: SearchDocumentQuery,
    ) -> tuple[StableReferenceExpansion, ...]:
        if memory.item.kind is MemoryKind.STORYLINE:
            storyline = cast(Storyline, memory)
            related_expansions = tuple(
                RelatedStorylineExpansion(
                    reference=reference,
                    memory=self._require_storyline(
                        self._hydrate_visible(
                            MemoryKind.STORYLINE,
                            reference.item_id,
                            revision_id,
                            cache,
                        )
                    ),
                )
                for reference in storyline.content.related_storylines
            )
            return tuple(
                expansion for expansion in related_expansions
                if self._reference_eligible(
                    expansion.memory.version.version_id, revision_id, scope,
                )
            )
        if memory.item.kind is MemoryKind.TRIGGER:
            trigger = cast(Trigger, memory)
            expansions: list[StableReferenceExpansion] = []
            if trigger.content.target_storyline_item_id is not None:
                item_id = trigger.content.target_storyline_item_id
                expansions.append(
                    TriggerTargetStorylineExpansion(
                        item_id=item_id,
                        memory=self._require_storyline(
                            self._hydrate_visible(
                                MemoryKind.STORYLINE,
                                item_id,
                                revision_id,
                                cache,
                            )
                        ),
                    )
                )
            if trigger.content.origin_event_item_id is not None:
                item_id = trigger.content.origin_event_item_id
                expansions.append(
                    TriggerOriginEventExpansion(
                        item_id=item_id,
                        memory=self._require_event(
                            self._hydrate_visible(
                                MemoryKind.EVENT,
                                item_id,
                                revision_id,
                                cache,
                            )
                        ),
                    )
                )
            return tuple(
                expansion for expansion in expansions
                if self._reference_eligible(
                    expansion.memory.version.version_id, revision_id, scope,
                )
            )
        return ()

    def _reference_eligible(
        self, version_id: UUID, revision_id: UUID, scope: SearchDocumentQuery,
    ) -> bool:
        try:
            self._search_documents.inspect_versions(revision_id, version_id, scope=scope)
        except TargetNotFoundError:
            return False
        return True

    @staticmethod
    def _validate_candidate(
        candidate: SearchDocumentCandidate,
        memory: HydratedMemory,
        competition_id: UUID,
    ) -> None:
        failures: list[str] = []
        if memory.version.version_id != candidate.version_id:
            failures.append("version ID differs from canonical memory")
        if memory.item.item_id != candidate.item_id:
            failures.append("item ID differs from canonical memory")
        if memory.item.kind is not candidate.kind:
            failures.append("kind differs from canonical memory")
        if memory.item.competition_id != competition_id:
            failures.append("canonical memory belongs to another competition")
        if failures:
            raise SearchProjectionHydrationError(
                candidate.version_id,
                candidate.kind,
                "; ".join(failures),
            )

    @staticmethod
    def _require_event(memory: HydratedMemory | Event | Storyline) -> Event:
        if memory.item.kind is not MemoryKind.EVENT:
            raise ValueError("canonical reference target is not an event")
        return cast(Event, memory)

    @staticmethod
    def _require_storyline(memory: Event | Storyline) -> Storyline:
        if memory.item.kind is not MemoryKind.STORYLINE:
            raise ValueError("canonical reference target is not a storyline")
        return cast(Storyline, memory)

    @staticmethod
    def _require_evidence(kind: str, memory: HydratedMemory) -> Fact | Event:
        if kind == MemoryKind.FACT.value and memory.item.kind is MemoryKind.FACT:
            return cast(Fact, memory)
        if kind == MemoryKind.EVENT.value and memory.item.kind is MemoryKind.EVENT:
            return cast(Event, memory)
        raise ValueError("canonical evidence target has the wrong kind")
