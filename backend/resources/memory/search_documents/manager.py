"""Competition-scoped search-document queries and deterministic rebuilds."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.memory import (
    CurrentRevision,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
)
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common.errors import (
    RevisionNotFoundError,
    TargetNotFoundError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.codec import (
    context_note_rows_statement,
    decode_context_note,
)
from backend.resources.memory.events.codec import decode_event, event_rows_statement
from backend.resources.memory.facts.codec import decode_fact, fact_rows_statement
from backend.resources.memory.revisions.shared import visible_versions_statement
from backend.resources.memory.search_documents.builders import (
    build_context_note_document,
    build_event_document,
    build_fact_document,
    build_storyline_document,
    build_trigger_document,
)
from backend.resources.memory.search_documents.objects import (
    SearchDiscoveryResult,
    SearchDiscoveryStatus,
    SearchDocumentCandidate,
    SearchDocumentProjection,
    SearchDocumentQuery,
    SearchMatchReason,
    SearchProjectionRebuildResult,
    SearchScoreComponents,
)
from backend.resources.memory.search_documents.query import (
    query_search_documents,
    temporal_conditions,
)
from backend.resources.memory.search_documents.shared import insert_search_document
from backend.resources.memory.search_documents.ranking import rank_candidates
from backend.resources.memory.search_documents.semantic import EmbeddingDocument, SemanticScorer
from backend.resources.memory.storylines.codec import (
    decode_storyline,
    storyline_rows_statement,
)
from backend.resources.memory.triggers.codec import (
    decode_trigger,
    trigger_rows_statement,
)


class SearchDocumentManager:
    """Candidate discovery and projection maintenance for one competition."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
        *,
        semantic_index: SemanticScorer | None = None,
    ) -> None:
        self._session_factory: SessionFactory = session_factory
        self._competition_id: UUID = context.scope.competition_id
        self._semantic_index = semantic_index

    @property
    def competition_id(self) -> UUID:
        return self._competition_id

    def search(
        self,
        revision_id: UUID,
        query: SearchDocumentQuery,
    ) -> tuple[SearchDocumentCandidate, ...]:
        """Compatibility API for callers needing only candidates."""
        return self.discover(revision_id, query).candidates

    def discover(
        self, revision_id: UUID, query: SearchDocumentQuery,
    ) -> SearchDiscoveryResult:
        """Discover scoped canonical units and report semantic index coverage."""
        with read_only_session(self._session_factory) as session:
            self._require_revision(session, revision_id)
            rows = query_search_documents(
                session, self._competition_id, revision_id, query,
            )
        candidates = tuple(
            self._candidate(row.document, row.lexical_rank, query).model_copy(update={
                "current_at_pin": row.current_at_pin,
                "revision_number": row.revision_number,
            }) for row in rows
        )
        scores: dict[UUID, float] = {}
        status = SearchDiscoveryStatus(
            total_count=len(rows), reason="Semantic discovery is not configured.",
        )
        if query.text and self._semantic_index is not None:
            semantic = self._semantic_index.score(query.text, tuple(
                EmbeddingDocument(
                    version_id=row.document.version_id,
                    document_text=row.document.document_text,
                    content_hash=row.document.content_hash,
                    builder_version=row.document.builder_version,
                ) for row in rows
            ))
            scores = semantic.scores
            status = SearchDiscoveryStatus(
                status=semantic.status, total_count=semantic.total_count,
                available_count=semantic.available_count,
                missing_count=semantic.missing_count, stale_count=semantic.stale_count,
                reason=semantic.reason,
            )
        elif not query.text:
            status = SearchDiscoveryStatus(
                total_count=len(rows), reason="Structured discovery does not require embeddings.",
            )
        return SearchDiscoveryResult(
            candidates=rank_candidates(candidates, query, scores), semantic_status=status,
        )

    def visible_reference_version(
        self, revision_id: UUID, item_id: UUID,
    ) -> UUID | None:
        """Resolve a stable relationship without hydrating unselected content."""
        visible = visible_versions_statement(
            self._competition_id, revision_id,
        ).subquery("visible_reference_versions")
        with read_only_session(self._session_factory) as session:
            return session.scalar(
                sa.select(visible.c.id).where(visible.c.item_id == item_id)
            )

    def inspect_versions(
        self,
        revision_id: UUID,
        version_id: UUID,
        *,
        history: bool = False,
        offset: int = 0,
        limit: int = 21,
        scope: SearchDocumentQuery | None = None,
    ) -> tuple[tuple[UUID, MemoryKind, int | None], ...]:
        """Select bounded canonical history through a selected version and pin.

        Unlike discovery, this deliberately permits retired exact versions. No
        version introduced after the pin or after the selected item revision is
        eligible, and pagination occurs before canonical content hydration.
        """
        if offset < 0 or not 1 <= limit <= 101:
            raise ValueError("inspection requires offset >= 0 and limit in 1..101")
        with read_only_session(self._session_factory) as session:
            self._require_revision(session, revision_id)
            pinned_sequence = (
                sa.select(MemoryRevision.sequence_number)
                .where(
                    MemoryRevision.id == revision_id,
                    MemoryRevision.competition_id == self._competition_id,
                )
                .scalar_subquery()
            )
            statement = (
                sa.select(MemoryVersion, MemoryItem.kind)
                .join(MemoryItem, MemoryItem.id == MemoryVersion.item_id)
                .join(
                    MemoryRevision,
                    MemoryRevision.id == MemoryVersion.introduced_revision_id,
                )
                .where(
                    MemoryVersion.competition_id == self._competition_id,
                    MemoryItem.competition_id == self._competition_id,
                    MemoryRevision.competition_id == self._competition_id,
                    MemoryRevision.sequence_number <= pinned_sequence,
                    *temporal_conditions(
                        self._competition_id, scope or SearchDocumentQuery(),
                        season_id=MemoryVersion.competition_season_id,
                        week=MemoryVersion.week,
                        recorded_at=MemoryVersion.recorded_at,
                    ),
                )
            )
            selected = session.execute(
                statement.where(MemoryVersion.id == version_id)
            ).one_or_none()
            if selected is None:
                raise TargetNotFoundError(version_id, tuple(MemoryKind))
            if history:
                statement = statement.where(
                    MemoryVersion.item_id == selected[0].item_id,
                    MemoryVersion.revision_number <= selected[0].revision_number,
                )
            else:
                statement = statement.where(MemoryVersion.id == version_id)
            rows = session.execute(
                statement.order_by(
                    MemoryVersion.revision_number.desc(), MemoryVersion.id,
                ).offset(offset).limit(limit)
            ).all()
            return tuple(
                (version.id, MemoryKind(kind), version.week) for version, kind in rows
            )

    def rebuild(self) -> SearchProjectionRebuildResult:
        """Atomically replace every historical projection in the competition."""

        with transaction_session(self._session_factory) as session:
            current = session.scalar(
                sa.select(CurrentRevision)
                .where(CurrentRevision.competition_id == self._competition_id)
                .with_for_update()
            )
            if current is None:
                raise RevisionNotFoundError(self._competition_id)

            projections = self._build_all_projections(session)
            session.execute(
                sa.delete(MemorySearchDocument).where(
                    MemorySearchDocument.competition_id == self._competition_id
                )
            )
            for version, projection in projections:
                insert_search_document(session, version, projection)
            session.flush()

            result = SearchProjectionRebuildResult(
                competition_id=self._competition_id,
                canonical_revision_id=current.current_revision_id,
                documents_rebuilt=len(projections),
            )
        return result

    def _require_revision(self, session: Session, revision_id: UUID) -> None:
        exists = session.scalar(
            sa.select(MemoryRevision.id).where(
                MemoryRevision.id == revision_id,
                MemoryRevision.competition_id == self._competition_id,
            )
        )
        if exists is None:
            raise RevisionNotFoundError(self._competition_id, revision_id)

    def _candidate(
        self,
        row: MemorySearchDocument,
        lexical_rank: float,
        query: SearchDocumentQuery,
    ) -> SearchDocumentCandidate:
        matched_entities = _text_overlap(row.entity_keys, query.entity_keys)
        matched_evidence = _uuid_overlap(
            row.evidence_version_ids,
            query.evidence_version_ids,
        )
        matched_related = _uuid_overlap(
            row.related_item_ids,
            query.related_item_ids,
        )
        matched_tags = _text_overlap(row.tags, query.tags)
        components = SearchScoreComponents(
            entity_overlap=float(len(matched_entities)),
            evidence_overlap=float(len(matched_evidence)),
            related_item_overlap=float(len(matched_related)),
            tag_overlap=float(len(matched_tags)),
            lexical_rank=lexical_rank,
            salience=float(row.salience or 0) * 0.1,
        )
        reasons: list[SearchMatchReason] = []
        if matched_entities:
            reasons.append(SearchMatchReason.ENTITY_OVERLAP)
        if matched_evidence:
            reasons.append(SearchMatchReason.EVIDENCE_OVERLAP)
        if matched_related:
            reasons.append(SearchMatchReason.RELATED_ITEM_OVERLAP)
        if matched_tags:
            reasons.append(SearchMatchReason.TAG_OVERLAP)
        if lexical_rank > 0:
            reasons.append(SearchMatchReason.LEXICAL_MATCH)
        if not query.has_discovery_signals:
            reasons.append(SearchMatchReason.BROWSE_MATCH)
        return SearchDocumentCandidate(
            version_id=row.version_id,
            item_id=row.item_id,
            kind=MemoryKind(row.kind),
            status=row.status,
            salience=row.salience,
            competition_season_id=row.competition_season_id,
            week=row.week,
            score=components.total,
            score_components=components,
            matched_entity_keys=matched_entities,
            matched_evidence_version_ids=matched_evidence,
            matched_related_item_ids=matched_related,
            matched_tags=matched_tags,
            match_reasons=tuple(reasons),
        )

    def _build_all_projections(
        self,
        session: Session,
    ) -> tuple[tuple[MemoryVersion, SearchDocumentProjection], ...]:
        projections: list[tuple[MemoryVersion, SearchDocumentProjection]] = []

        for item, version, stored in session.execute(
            fact_rows_statement().where(
                MemoryItem.competition_id == self._competition_id
            )
        ):
            fact = decode_fact(item, version, stored)
            projections.append((version, build_fact_document(fact.content)))
        for item, version, stored in session.execute(
            event_rows_statement().where(
                MemoryItem.competition_id == self._competition_id
            )
        ):
            event = decode_event(item, version, stored)
            projections.append((version, build_event_document(event.content)))
        for item, version, stored in session.execute(
            storyline_rows_statement().where(
                MemoryItem.competition_id == self._competition_id
            )
        ):
            storyline = decode_storyline(item, version, stored)
            projections.append(
                (version, build_storyline_document(storyline.content))
            )
        for item, version, stored in session.execute(
            trigger_rows_statement().where(
                MemoryItem.competition_id == self._competition_id
            )
        ):
            trigger = decode_trigger(item, version, stored)
            projections.append((version, build_trigger_document(trigger.content)))
        for item, version, identity, stored in session.execute(
            context_note_rows_statement().where(
                MemoryItem.competition_id == self._competition_id
            )
        ):
            note = decode_context_note(item, version, identity, stored)
            projections.append(
                (
                    version,
                    build_context_note_document(note.note_identity, note.content),
                )
            )

        canonical_version_ids = set(
            session.scalars(
                sa.select(MemoryVersion.id).where(
                    MemoryVersion.competition_id == self._competition_id
                )
            )
        )
        projected_version_ids = {version.id for version, _ in projections}
        if canonical_version_ids != projected_version_ids:
            missing = sorted(canonical_version_ids - projected_version_ids, key=str)
            raise ValueError(
                "cannot rebuild search projection; canonical typed rows are missing "
                f"for versions: {', '.join(map(str, missing))}"
            )
        return tuple(
            sorted(
                projections,
                key=lambda entry: (entry[1].kind.value, str(entry[0].id)),
            )
        )


def _text_overlap(
    stored: Iterable[str],
    requested: Iterable[str],
) -> tuple[str, ...]:
    return tuple(sorted(set(stored).intersection(requested)))


def _uuid_overlap(
    stored: Iterable[UUID],
    requested: Iterable[UUID],
) -> tuple[UUID, ...]:
    return tuple(sorted(set(stored).intersection(requested), key=str))
