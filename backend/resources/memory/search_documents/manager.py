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
from backend.resources.memory.common.errors import RevisionNotFoundError
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.codec import (
    context_note_rows_statement,
    decode_context_note,
)
from backend.resources.memory.events.codec import decode_event, event_rows_statement
from backend.resources.memory.facts.codec import decode_fact, fact_rows_statement
from backend.resources.memory.search_documents.builders import (
    build_context_note_document,
    build_event_document,
    build_fact_document,
    build_storyline_document,
    build_trigger_document,
)
from backend.resources.memory.search_documents.objects import (
    SearchDocumentCandidate,
    SearchDocumentProjection,
    SearchDocumentQuery,
    SearchMatchReason,
    SearchProjectionRebuildResult,
    SearchScoreComponents,
)
from backend.resources.memory.search_documents.query import query_search_documents
from backend.resources.memory.search_documents.shared import insert_search_document
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
    ) -> None:
        self._session_factory: SessionFactory = session_factory
        self._competition_id: UUID = context.scope.competition_id

    @property
    def competition_id(self) -> UUID:
        return self._competition_id

    def search(
        self,
        revision_id: UUID,
        query: SearchDocumentQuery,
    ) -> tuple[SearchDocumentCandidate, ...]:
        """Return compact candidates visible at one exact canonical revision."""

        with read_only_session(self._session_factory) as session:
            self._require_revision(session, revision_id)
            rows = query_search_documents(
                session,
                self._competition_id,
                revision_id,
                query,
            )
        candidates = tuple(self._candidate(row, rank, query) for row, rank in rows)
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.kind.value,
                str(candidate.version_id),
            ),
        )
        return tuple(ordered[: query.limit])

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
