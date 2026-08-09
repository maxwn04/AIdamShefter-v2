"""Revision-safe retrieval policy and canonical memory read facade."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from backend.resources.memory.cursors import decode_item_cursor
from backend.resources.memory.errors import (
    InvalidMemoryCursor,
    MemoryNotFound,
    MemoryScopeViolation,
    SearchProjectionUnavailable,
)
from backend.resources.memory.objects import (
    DEFAULT_EXPANSION,
    EntityKey,
    ExpansionPolicy,
    HydratedMemoryVersion,
    ItemHistory,
    MemoryListQuery,
    MemoryPage,
    MemoryQuery,
    MemoryRevisionRef,
    RetrievedMemory,
    RetrievedMemoryEntry,
    RevisionPage,
)
from backend.resources.memory.search_documents import entity_search_key
from backend.services.memory.contracts import PinnedMemoryReader


class CandidateMatch(Protocol):
    """Raw persistence signals accepted by service-owned ranking policy."""

    version_id: UUID
    lexical_match: bool
    matched_entities: Sequence[str]
    matched_evidence_version_ids: Sequence[UUID]
    matched_related_item_ids: Sequence[UUID]
    salience: int | None
    recorded_at: datetime


class MemoryReadManager(Protocol):
    """Persistence capabilities needed by the cohesive memory service."""

    def current_revision(self, competition_id: UUID) -> MemoryRevisionRef: ...

    def get_revision(
        self,
        revision_id: UUID,
        competition_id: UUID | None = None,
    ) -> MemoryRevisionRef: ...

    def get_visible_item(
        self,
        revision: MemoryRevisionRef,
        item_id: UUID,
        expansion: ExpansionPolicy,
    ) -> HydratedMemoryVersion: ...

    def get_visible_version(
        self,
        revision: MemoryRevisionRef,
        version_id: UUID,
        expansion: ExpansionPolicy,
    ) -> HydratedMemoryVersion: ...

    def list_visible_items(
        self,
        revision: MemoryRevisionRef,
        query: MemoryListQuery,
    ) -> MemoryPage: ...

    def item_history(self, competition_id: UUID, item_id: UUID) -> ItemHistory: ...

    def list_revisions(
        self,
        competition_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> RevisionPage: ...

    def find_candidates(
        self,
        revision: MemoryRevisionRef,
        query: MemoryQuery,
    ) -> Sequence[CandidateMatch]: ...

    def scan_visible_candidates(
        self,
        revision: MemoryRevisionRef,
        query: MemoryQuery,
    ) -> Sequence[CandidateMatch]: ...

    def hydrate_visible_versions(
        self,
        revision: MemoryRevisionRef,
        version_ids: Sequence[UUID],
        expansion: ExpansionPolicy,
    ) -> Mapping[UUID, HydratedMemoryVersion]: ...


@dataclass(frozen=True, slots=True)
class _RankedCandidate:
    version_id: UUID
    score: float
    match_reasons: tuple[str, ...]
    matched_entities: tuple[EntityKey, ...]


@dataclass(slots=True)
class _CandidateSignals:
    recorded_at: datetime
    lexical_match: bool = False
    entities: set[str] = field(default_factory=set)
    evidence: set[UUID] = field(default_factory=set)
    related: set[UUID] = field(default_factory=set)
    salience: int | None = None


@dataclass(frozen=True, slots=True)
class _PinnedMemoryReader:
    """Immutable capability that prevents competition or revision drift."""

    _manager: MemoryReadManager
    _service: MemoryService
    revision: MemoryRevisionRef

    def retrieve(self, query: MemoryQuery) -> RetrievedMemory:
        return self._service._retrieve_at(self.revision, query)

    def get_version(
        self,
        version_id: UUID,
        expansion: ExpansionPolicy = DEFAULT_EXPANSION,
    ) -> HydratedMemoryVersion:
        return self._manager.get_visible_version(self.revision, version_id, expansion)

    def get_item(
        self,
        item_id: UUID,
        expansion: ExpansionPolicy = DEFAULT_EXPANSION,
    ) -> HydratedMemoryVersion:
        return self._manager.get_visible_item(self.revision, item_id, expansion)


class MemoryService:
    """One cohesive facade for revision-safe retrieval and basic inspection."""

    _EXACT_EVIDENCE_WEIGHT = 4.0
    _RELATED_ITEM_WEIGHT = 3.0
    _ENTITY_WEIGHT = 2.0
    _LEXICAL_WEIGHT = 1.5
    _SALIENCE_WEIGHT = 0.5
    _RECENCY_WEIGHT = 0.25
    _RECENCY_WINDOW_SECONDS = 365 * 24 * 60 * 60

    def __init__(self, manager: MemoryReadManager) -> None:
        self._manager = manager

    def pin_current(self, competition_id: UUID) -> PinnedMemoryReader:
        return _PinnedMemoryReader(
            self._manager,
            self,
            self._manager.current_revision(competition_id),
        )

    def at_revision(self, revision_id: UUID) -> PinnedMemoryReader:
        return _PinnedMemoryReader(
            self._manager,
            self,
            self._manager.get_revision(revision_id),
        )

    def list_items(self, query: MemoryListQuery) -> MemoryPage:
        revision_id = query.revision_id
        if query.cursor is not None:
            cursor = decode_item_cursor(query.cursor)
            if revision_id is not None and revision_id != cursor.revision_id:
                raise InvalidMemoryCursor(
                    "memory item cursor conflicts with the requested revision",
                    details={
                        "cursor_revision_id": str(cursor.revision_id),
                        "revision_id": str(revision_id),
                    },
                )
            revision_id = cursor.revision_id
        try:
            revision = self._resolve_revision(query.competition_id, revision_id)
        except (MemoryNotFound, MemoryScopeViolation) as error:
            if query.cursor is None:
                raise
            raise InvalidMemoryCursor(
                "memory item cursor references an unavailable revision"
            ) from error
        return self._manager.list_visible_items(revision, query)

    def get_item(
        self,
        competition_id: UUID,
        item_id: UUID,
        revision_id: UUID | None = None,
    ) -> HydratedMemoryVersion:
        revision = self._resolve_revision(competition_id, revision_id)
        return self._manager.get_visible_item(revision, item_id, DEFAULT_EXPANSION)

    def item_history(self, competition_id: UUID, item_id: UUID) -> ItemHistory:
        return self._manager.item_history(competition_id, item_id)

    def list_revisions(
        self,
        competition_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> RevisionPage:
        return self._manager.list_revisions(competition_id, cursor, limit)

    def _resolve_revision(
        self,
        competition_id: UUID,
        revision_id: UUID | None,
    ) -> MemoryRevisionRef:
        if revision_id is None:
            return self._manager.current_revision(competition_id)
        return self._manager.get_revision(revision_id, competition_id)

    def _retrieve_at(
        self,
        revision: MemoryRevisionRef,
        query: MemoryQuery,
    ) -> RetrievedMemory:
        degraded = False
        try:
            candidates = self._manager.find_candidates(revision, query)
        except SearchProjectionUnavailable:
            degraded = True
            candidates = self._manager.scan_visible_candidates(
                revision,
                query,
            )

        ranked = self._rank_candidates(candidates, query.entities)[: query.limit]
        hydrated = self._manager.hydrate_visible_versions(
            revision,
            [candidate.version_id for candidate in ranked],
            query.expansion,
        )
        entries = tuple(
            RetrievedMemoryEntry(
                memory=hydrated[candidate.version_id],
                score=candidate.score,
                match_reasons=candidate.match_reasons,
                matched_entities=candidate.matched_entities,
            )
            for candidate in ranked
        )
        return RetrievedMemory(
            revision=revision,
            entries=entries,
            degraded=degraded,
        )

    def _rank_candidates(
        self,
        candidates: Sequence[CandidateMatch],
        query_entities: Sequence[EntityKey],
    ) -> tuple[_RankedCandidate, ...]:
        """Merge raw signals and apply one deterministic ranking policy."""

        merged: dict[UUID, _CandidateSignals] = {}
        for candidate in candidates:
            signals = merged.setdefault(
                candidate.version_id,
                _CandidateSignals(recorded_at=candidate.recorded_at),
            )
            signals.lexical_match = (
                signals.lexical_match or candidate.lexical_match
            )
            signals.entities.update(candidate.matched_entities)
            signals.evidence.update(candidate.matched_evidence_version_ids)
            signals.related.update(candidate.matched_related_item_ids)
            if candidate.salience is not None:
                signals.salience = max(
                    candidate.salience,
                    signals.salience or 0,
                )
            if candidate.recorded_at > signals.recorded_at:
                signals.recorded_at = candidate.recorded_at

        newest = max(
            (signals.recorded_at for signals in merged.values()),
            default=None,
        )
        ranked: list[_RankedCandidate] = []
        typed_entities = {
            entity_search_key(entity): entity for entity in query_entities
        }
        for version_id, signals in merged.items():
            components: dict[str, float] = {}
            reasons: list[str] = []
            if signals.evidence:
                reasons.append("exact_evidence")
                components["exact_evidence"] = self._EXACT_EVIDENCE_WEIGHT
            if signals.related:
                reasons.append("related_item")
                components["related_item"] = self._RELATED_ITEM_WEIGHT
            if signals.entities:
                reasons.append("entity_overlap")
                components["entity"] = self._ENTITY_WEIGHT
            if signals.lexical_match:
                reasons.append("lexical_match")
                components["lexical"] = self._LEXICAL_WEIGHT
            if signals.salience is not None:
                components["salience"] = (
                    signals.salience / 5 * self._SALIENCE_WEIGHT
                )
            if newest is not None:
                age_seconds = max(
                    0.0,
                    (newest - signals.recorded_at).total_seconds(),
                )
                recency = max(
                    0.0,
                    1.0 - age_seconds / self._RECENCY_WINDOW_SECONDS,
                )
                if recency > 0:
                    components["recency"] = recency * self._RECENCY_WEIGHT
            if not reasons:
                reasons.append("filter_match")
            ranked.append(
                _RankedCandidate(
                    version_id=version_id,
                    score=sum(components.values()),
                    match_reasons=tuple(reasons),
                    matched_entities=tuple(
                        sorted(
                            (
                                typed_entities[key]
                                for key in signals.entities
                                if key in typed_entities
                            ),
                            key=lambda entity: (entity.kind, str(entity.id)),
                        )
                    ),
                )
            )

        return tuple(
            sorted(ranked, key=lambda item: (-item.score, str(item.version_id)))
        )
