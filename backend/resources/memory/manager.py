"""Canonical memory persistence and revision-grounded read operations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from backend.database.models.memory import (
    ContextNote,
    ContextNoteVersion,
    CurrentRevision,
    EventVersion,
    FactVersion,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
    StorylineVersion,
    TriggerVersion,
)
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.memory.errors import (
    MemoryNotFound,
    MemoryScopeViolation,
    SearchProjectionUnavailable,
)
from backend.resources.memory.objects import (
    DEFAULT_EXPANSION,
    ExpansionPolicy,
    HydratedMemoryVersion,
    ItemHistory,
    MemoryListQuery,
    MemoryPage,
    MemoryQuery,
    MemoryRevision as MemoryRevisionResource,
    MemoryRevisionRef,
    MemoryKind,
    RebuildResult,
    RevisionPage,
    SearchIndexStatus,
    TypedMemoryVersion,
    decode_memory_content,
)
from backend.resources.memory.search_documents import (
    SEARCH_DOCUMENT_BUILDER_VERSION,
    SearchDocument,
    build_search_document,
    entity_search_key,
)


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    """One compact projection match returned to retrieval policy."""

    version_id: UUID
    kind: str
    match_reasons: tuple[str, ...]
    rank_components: Mapping[str, float]
    matched_entities: tuple[str, ...]


class MemoryManager:
    """Deep persistence boundary for the canonical memory aggregate."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def current_revision(self, competition_id: UUID) -> MemoryRevisionRef:
        with read_only_session(self._session_factory) as session:
            row = session.execute(
                sa.select(MemoryRevision)
                .join(
                    CurrentRevision,
                    sa.and_(
                        CurrentRevision.current_revision_id == MemoryRevision.id,
                        CurrentRevision.competition_id
                        == MemoryRevision.competition_id,
                    ),
                )
                .where(CurrentRevision.competition_id == competition_id)
            ).scalar_one_or_none()
            if row is None:
                raise MemoryNotFound(
                    f"current memory revision not found for {competition_id}"
                )
            return _revision_ref(row)

    def get_revision(
        self,
        revision_id: UUID,
        competition_id: UUID | None = None,
    ) -> MemoryRevisionRef:
        with read_only_session(self._session_factory) as session:
            row = session.get(MemoryRevision, revision_id)
            if row is None:
                raise MemoryNotFound(f"memory revision not found: {revision_id}")
            if competition_id is not None and row.competition_id != competition_id:
                raise MemoryScopeViolation(
                    f"memory revision is outside competition scope: {revision_id}"
                )
            return _revision_ref(row)

    def get_visible_item(
        self,
        revision: MemoryRevisionRef,
        item_id: UUID,
        expansion: ExpansionPolicy,
    ) -> HydratedMemoryVersion:
        with read_only_session(self._session_factory) as session:
            item = session.get(MemoryItem, item_id)
            if item is None:
                raise MemoryNotFound(f"memory item not found: {item_id}")
            if item.competition_id != revision.competition_id:
                raise MemoryScopeViolation(
                    f"memory item is outside competition scope: {item_id}"
                )
            version_id = session.scalar(
                _visible_versions(revision)
                .with_only_columns(MemoryVersion.id)
                .where(MemoryVersion.item_id == item_id)
            )
            if version_id is None:
                raise MemoryScopeViolation(
                    f"memory item is not visible at revision {revision.id}: {item_id}"
                )
            return _hydrate_visible_versions(
                session, revision, [version_id], expansion
            )[version_id]

    def get_visible_version(
        self,
        revision: MemoryRevisionRef,
        version_id: UUID,
        expansion: ExpansionPolicy,
    ) -> HydratedMemoryVersion:
        with read_only_session(self._session_factory) as session:
            return _hydrate_visible_versions(
                session, revision, [version_id], expansion
            )[version_id]

    def hydrate_visible_versions(
        self,
        revision: MemoryRevisionRef,
        version_ids: Sequence[UUID],
        expansion: ExpansionPolicy,
    ) -> Mapping[UUID, HydratedMemoryVersion]:
        if not version_ids:
            return {}
        with read_only_session(self._session_factory) as session:
            return _hydrate_visible_versions(session, revision, version_ids, expansion)

    def list_visible_items(
        self,
        revision: MemoryRevisionRef,
        query: MemoryListQuery,
    ) -> MemoryPage:
        if query.competition_id != revision.competition_id:
            raise MemoryScopeViolation(
                "list query competition does not match the pinned revision"
            )
        statement = _visible_versions(revision).join(
            MemoryItem,
            MemoryItem.id == MemoryVersion.item_id,
        )
        if query.kinds:
            statement = statement.where(
                MemoryItem.kind.in_([kind.value for kind in query.kinds])
            )
        if query.statuses:
            statement = statement.where(
                sa.or_(*(_status_matches(status.value) for status in query.statuses))
            )
        if query.cursor is not None:
            statement = statement.where(MemoryItem.id > _uuid_cursor(query.cursor))
        statement = statement.order_by(MemoryItem.id).limit(query.limit + 1)

        with read_only_session(self._session_factory) as session:
            rows = list(
                session.execute(
                    statement.with_only_columns(MemoryItem.id, MemoryVersion.id)
                )
            )
            page_rows = rows[: query.limit]
            page_ids = [row[1] for row in page_rows]
            hydrated = _hydrate_visible_versions(
                session,
                revision,
                page_ids,
                DEFAULT_EXPANSION,
            )
        next_cursor = str(page_rows[-1][0]) if len(rows) > query.limit else None
        return MemoryPage(
            revision=revision,
            items=tuple(hydrated[version_id] for version_id in page_ids),
            next_cursor=next_cursor,
        )

    def item_history(self, competition_id: UUID, item_id: UUID) -> ItemHistory:
        with read_only_session(self._session_factory) as session:
            item = session.get(MemoryItem, item_id)
            if item is None:
                raise MemoryNotFound(f"memory item not found: {item_id}")
            if item.competition_id != competition_id:
                raise MemoryScopeViolation(
                    f"memory item is outside competition scope: {item_id}"
                )
            version_ids = list(
                session.scalars(
                    sa.select(MemoryVersion.id)
                    .where(
                        MemoryVersion.item_id == item_id,
                        MemoryVersion.competition_id == competition_id,
                    )
                    .order_by(MemoryVersion.revision_number)
                )
            )
            versions = _load_typed_versions(session, version_ids)
        return ItemHistory(
            competition_id=competition_id,
            item_id=item_id,
            versions=tuple(versions[version_id] for version_id in version_ids),
        )

    def list_revisions(
        self,
        competition_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> RevisionPage:
        if not 1 <= limit <= 100:
            raise ValueError("revision page limit must be between 1 and 100")
        statement = sa.select(MemoryRevision).where(
            MemoryRevision.competition_id == competition_id
        )
        if cursor is not None:
            statement = statement.where(
                MemoryRevision.sequence_number < _sequence_cursor(cursor)
            )
        statement = statement.order_by(MemoryRevision.sequence_number.desc()).limit(
            limit + 1
        )
        with read_only_session(self._session_factory) as session:
            rows = list(session.scalars(statement))
        page_rows = rows[:limit]
        next_cursor = (
            str(page_rows[-1].sequence_number) if len(rows) > limit else None
        )
        return RevisionPage(
            competition_id=competition_id,
            revisions=tuple(_revision_resource(row) for row in page_rows),
            next_cursor=next_cursor,
        )

    def find_candidates(
        self,
        revision: MemoryRevisionRef,
        query: MemoryQuery,
    ) -> Sequence[MemoryCandidate]:
        """Find compact candidates only when the current projection is complete."""

        visible = _visible_versions(revision).with_only_columns(
            MemoryVersion.id
        ).subquery()
        with read_only_session(self._session_factory) as session:
            projection_incomplete = session.scalar(
                sa.select(
                    sa.exists(
                        sa.select(1)
                        .select_from(visible)
                        .outerjoin(
                            MemorySearchDocument,
                            MemorySearchDocument.version_id == visible.c.id,
                        )
                        .where(
                            sa.or_(
                                MemorySearchDocument.version_id.is_(None),
                                MemorySearchDocument.builder_version
                                != SEARCH_DOCUMENT_BUILDER_VERSION,
                            )
                        )
                    )
                )
            )
            if projection_incomplete:
                raise SearchProjectionUnavailable

            entity_keys = tuple(
                sorted({entity_search_key(entity) for entity in query.entities})
            )
            text_query = (
                sa.func.plainto_tsquery("english", query.text)
                if query.text is not None
                else None
            )
            lexical_rank = (
                sa.func.ts_rank_cd(
                    MemorySearchDocument.search_vector,
                    text_query,
                )
                if text_query is not None
                else sa.literal(0.0)
            ).label("lexical_rank")
            statement = (
                sa.select(MemorySearchDocument, lexical_rank)
                .join(visible, visible.c.id == MemorySearchDocument.version_id)
                .where(
                    MemorySearchDocument.builder_version
                    == SEARCH_DOCUMENT_BUILDER_VERSION
                )
            )
            if query.kinds:
                statement = statement.where(
                    MemorySearchDocument.kind.in_(
                        [kind.value for kind in query.kinds]
                    )
                )
            if query.statuses:
                statement = statement.where(
                    MemorySearchDocument.status.in_(
                        [status.value for status in query.statuses]
                    )
                )
            if query.season_id is not None:
                statement = statement.where(
                    MemorySearchDocument.competition_season_id == query.season_id
                )
            if query.week is not None:
                statement = statement.where(MemorySearchDocument.week == query.week)
            signals: list[sa.ColumnElement[bool]] = []
            if text_query is not None:
                signals.append(
                    MemorySearchDocument.search_vector.op("@@")(text_query)
                )
            if entity_keys:
                signals.append(MemorySearchDocument.entity_keys.overlap(entity_keys))
            if signals:
                statement = statement.where(sa.or_(*signals))
            statement = statement.order_by(
                lexical_rank.desc(),
                MemorySearchDocument.salience.desc().nullslast(),
                MemorySearchDocument.version_id,
            ).limit(min(query.limit * 4, 400))
            rows = session.execute(statement).all()

        return tuple(
            _candidate_from_document(
                document,
                float(lexical_score),
                entity_keys,
                has_text=query.text is not None,
            )
            for document, lexical_score in rows
        )

    def scan_visible_candidates(
        self,
        revision: MemoryRevisionRef,
        query: MemoryQuery,
        limit: int,
    ) -> Sequence[MemoryCandidate]:
        """Bounded canonical fallback used only while the projection needs repair."""

        statement = _visible_versions(revision).join(
            MemoryItem,
            MemoryItem.id == MemoryVersion.item_id,
        )
        if query.kinds:
            statement = statement.where(
                MemoryItem.kind.in_([kind.value for kind in query.kinds])
            )
        if query.season_id is not None:
            statement = statement.where(
                MemoryVersion.competition_season_id == query.season_id
            )
        if query.week is not None:
            statement = statement.where(MemoryVersion.week == query.week)
        statement = statement.order_by(
            MemoryVersion.recorded_at.desc(), MemoryVersion.id
        ).limit(500)

        with read_only_session(self._session_factory) as session:
            version_ids = list(
                session.scalars(statement.with_only_columns(MemoryVersion.id))
            )
            versions = _load_typed_versions(session, version_ids)

        entity_keys = tuple(
            sorted({entity_search_key(entity) for entity in query.entities})
        )
        candidates: list[MemoryCandidate] = []
        for version_id in version_ids:
            document = build_search_document(versions[version_id])
            if query.statuses and document.status not in {
                status.value for status in query.statuses
            }:
                continue
            lexical_match = _fallback_text_matches(query.text, document.document_text)
            entity_match = bool(set(entity_keys) & set(document.entity_keys))
            if (query.text is not None or entity_keys) and not (
                lexical_match or entity_match
            ):
                continue
            candidates.append(
                _candidate_from_document(
                    document,
                    0.5 if lexical_match else 0.0,
                    entity_keys,
                    has_text=query.text is not None,
                )
            )
            if len(candidates) >= limit:
                break
        return tuple(candidates)

    def search_index_status(self, competition_id: UUID) -> SearchIndexStatus:
        with read_only_session(self._session_factory) as session:
            total = session.scalar(
                sa.select(sa.func.count())
                .select_from(MemoryVersion)
                .where(MemoryVersion.competition_id == competition_id)
            ) or 0
            indexed = session.scalar(
                sa.select(sa.func.count())
                .select_from(MemorySearchDocument)
                .where(
                    MemorySearchDocument.competition_id == competition_id,
                    MemorySearchDocument.builder_version
                    == SEARCH_DOCUMENT_BUILDER_VERSION,
                )
            ) or 0
            missing = session.scalar(
                sa.select(sa.func.count())
                .select_from(MemoryVersion)
                .outerjoin(
                    MemorySearchDocument,
                    MemorySearchDocument.version_id == MemoryVersion.id,
                )
                .where(
                    MemoryVersion.competition_id == competition_id,
                    MemorySearchDocument.version_id.is_(None),
                )
            ) or 0
            stale = session.scalar(
                sa.select(sa.func.count())
                .select_from(MemorySearchDocument)
                .where(
                    MemorySearchDocument.competition_id == competition_id,
                    MemorySearchDocument.builder_version
                    != SEARCH_DOCUMENT_BUILDER_VERSION,
                )
            ) or 0
        return SearchIndexStatus(
            competition_id=competition_id,
            builder_version=SEARCH_DOCUMENT_BUILDER_VERSION,
            canonical_version_count=total,
            indexed_document_count=indexed,
            missing_document_count=missing,
            stale_document_count=stale,
        )

    def rebuild_search_index(
        self,
        competition_id: UUID,
        *,
        batch_size: int = 200,
    ) -> RebuildResult:
        """Rebuild projection rows from immutable canonical versions in batches."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        rebuilt = 0
        cursor: UUID | None = None
        while True:
            with read_only_session(self._session_factory) as session:
                statement = (
                    sa.select(MemoryVersion.id)
                    .where(MemoryVersion.competition_id == competition_id)
                    .order_by(MemoryVersion.id)
                    .limit(batch_size)
                )
                if cursor is not None:
                    statement = statement.where(MemoryVersion.id > cursor)
                version_ids = list(session.scalars(statement))
                versions = _load_typed_versions(session, version_ids)
            if not version_ids:
                break
            self._write_search_documents(
                [
                    build_search_document(versions[version_id])
                    for version_id in version_ids
                ]
            )
            rebuilt += len(version_ids)
            cursor = version_ids[-1]
        return RebuildResult(
            competition_id=competition_id,
            builder_version=SEARCH_DOCUMENT_BUILDER_VERSION,
            rebuilt_document_count=rebuilt,
        )

    def _write_search_documents(self, documents: Sequence[SearchDocument]) -> None:
        """Atomically install deterministic projection rows for exact versions."""

        if not documents:
            return
        with transaction_session(self._session_factory) as session:
            _persist_search_documents(session, documents)


def _revision_ref(revision: MemoryRevision) -> MemoryRevisionRef:
    return MemoryRevisionRef(
        id=revision.id,
        competition_id=revision.competition_id,
        sequence_number=revision.sequence_number,
        state_content_hash=revision.state_content_hash,
    )


def _revision_resource(revision: MemoryRevision) -> MemoryRevisionResource:
    return MemoryRevisionResource(
        id=revision.id,
        competition_id=revision.competition_id,
        sequence_number=revision.sequence_number,
        state_content_hash=revision.state_content_hash,
        previous_revision_id=revision.previous_revision_id,
        producing_generation_id=revision.producing_generation_id,
        competition_season_id=revision.competition_season_id,
        week=revision.week,
        knowledge_cutoff_at=revision.knowledge_cutoff_at,
        created_at=revision.created_at,
    )


def _visible_versions(revision: MemoryRevisionRef) -> sa.Select[Any]:
    introduced = aliased(MemoryRevision, name="introduced_revision")
    retired = aliased(MemoryRevision, name="retired_revision")
    return (
        sa.select(MemoryVersion)
        .join(
            introduced,
            sa.and_(
                introduced.id == MemoryVersion.introduced_revision_id,
                introduced.competition_id == MemoryVersion.competition_id,
            ),
        )
        .outerjoin(
            retired,
            sa.and_(
                retired.id == MemoryVersion.retired_revision_id,
                retired.competition_id == MemoryVersion.competition_id,
            ),
        )
        .where(
            MemoryVersion.competition_id == revision.competition_id,
            introduced.sequence_number <= revision.sequence_number,
            sa.or_(
                MemoryVersion.retired_revision_id.is_(None),
                retired.sequence_number > revision.sequence_number,
            ),
        )
    )


def _hydrate_visible_versions(
    session: Session,
    revision: MemoryRevisionRef,
    version_ids: Sequence[UUID],
    expansion: ExpansionPolicy,
) -> dict[UUID, HydratedMemoryVersion]:
    unique_ids = tuple(dict.fromkeys(version_ids))
    if not unique_ids:
        return {}
    visible_ids = set(
        session.scalars(
            _visible_versions(revision)
            .with_only_columns(MemoryVersion.id)
            .where(MemoryVersion.id.in_(unique_ids))
        )
    )
    missing = [version_id for version_id in unique_ids if version_id not in visible_ids]
    if missing:
        _raise_invisible_version(session, revision, missing[0])

    versions = _load_typed_versions(session, unique_ids)
    evidence_ids: set[UUID] = set()
    related_item_ids: set[UUID] = set()
    if expansion.include_evidence:
        for version in versions.values():
            if version.kind == MemoryKind.STORYLINE:
                evidence_ids.update(
                    reference.version_id for reference in version.content.evidence
                )
            elif version.kind == MemoryKind.FACT:
                evidence_ids.update(version.content.originating_event_version_ids)
    if expansion.include_related_items:
        for version in versions.values():
            if version.kind == MemoryKind.STORYLINE:
                related_item_ids.update(
                    reference.item_id
                    for reference in version.content.related_storylines
                )
            elif version.kind == MemoryKind.TRIGGER:
                related_item_ids.update(
                    item_id
                    for item_id in (
                        version.content.target_storyline_item_id,
                        version.content.origin_event_item_id,
                    )
                    if item_id is not None
                )

    evidence = _load_evidence_versions(session, revision, evidence_ids)
    related = _load_visible_items(session, revision, related_item_ids)
    hydrated: dict[UUID, HydratedMemoryVersion] = {}
    for version_id in unique_ids:
        version = versions[version_id]
        hydrated[version_id] = HydratedMemoryVersion(
            version=version,
            evidence=tuple(
                evidence[evidence_id]
                for evidence_id in _evidence_ids(version)
                if evidence_id in evidence
            ),
            related_items=tuple(
                related[item_id]
                for item_id in _related_item_ids(version)
                if item_id in related
            ),
        )
    return hydrated


def _load_typed_versions(
    session: Session,
    version_ids: Sequence[UUID],
) -> dict[UUID, TypedMemoryVersion]:
    if not version_ids:
        return {}
    rows = session.execute(
        sa.select(MemoryVersion, MemoryItem)
        .join(MemoryItem, MemoryItem.id == MemoryVersion.item_id)
        .where(MemoryVersion.id.in_(version_ids))
    ).all()
    envelopes = {version.id: (version, item) for version, item in rows}
    if len(envelopes) != len(set(version_ids)):
        missing = next(
            version_id for version_id in version_ids if version_id not in envelopes
        )
        raise MemoryNotFound(f"memory version not found: {missing}")

    ids_by_kind: dict[MemoryKind, list[UUID]] = {}
    for version, item in envelopes.values():
        try:
            kind = MemoryKind(item.kind)
        except ValueError as error:
            raise ValueError(f"unsupported stored memory kind: {item.kind}") from error
        ids_by_kind.setdefault(kind, []).append(version.id)

    typed_rows: dict[UUID, object] = {}
    table_by_kind = {
        MemoryKind.STORYLINE: StorylineVersion,
        MemoryKind.FACT: FactVersion,
        MemoryKind.EVENT: EventVersion,
        MemoryKind.TRIGGER: TriggerVersion,
        MemoryKind.CONTEXT_NOTE: ContextNoteVersion,
    }
    for kind, ids in ids_by_kind.items():
        typed_rows.update(
            {
                row.version_id: row
                for row in session.scalars(
                    sa.select(table_by_kind[kind]).where(
                        table_by_kind[kind].version_id.in_(ids)
                    )
                )
            }
        )

    context_identities = {
        row.item_id: row
        for row in session.scalars(
            sa.select(ContextNote).where(
                ContextNote.item_id.in_(
                    [
                        item.id
                        for _, item in envelopes.values()
                        if item.kind == MemoryKind.CONTEXT_NOTE.value
                    ]
                )
            )
        )
    }
    decoded: dict[UUID, TypedMemoryVersion] = {}
    for version_id, (envelope, item) in envelopes.items():
        typed_row = typed_rows.get(version_id)
        if typed_row is None:
            raise MemoryNotFound(f"typed memory content not found: {version_id}")
        kind = MemoryKind(item.kind)
        content = decode_memory_content(
            kind,
            envelope.content_schema_version,
            _content_payload(kind, typed_row),
        )
        identity_row = context_identities.get(item.id)
        decoded[version_id] = TypedMemoryVersion(
            version_id=envelope.id,
            item_id=envelope.item_id,
            competition_id=envelope.competition_id,
            kind=kind,
            revision_number=envelope.revision_number,
            content_schema_version=envelope.content_schema_version,
            introduced_revision_id=envelope.introduced_revision_id,
            retired_revision_id=envelope.retired_revision_id,
            competition_season_id=envelope.competition_season_id,
            week=envelope.week,
            occurred_at=envelope.occurred_at,
            creating_generation_id=envelope.creating_generation_id,
            creating_tool_call_id=envelope.creating_tool_call_id,
            change_reason=envelope.change_reason,
            recorded_at=envelope.recorded_at,
            content=content,
            context_note_identity=(
                {
                    "scope": identity_row.scope,
                    "note_key": identity_row.note_key,
                    "competition_season_id": identity_row.competition_season_id,
                    "franchise_id": identity_row.franchise_id,
                }
                if identity_row is not None
                else None
            ),
        )
    return decoded


def _content_payload(kind: MemoryKind, row: object) -> dict[str, Any]:
    if kind == MemoryKind.STORYLINE:
        return {
            "headline": row.headline,
            "summary": row.summary,
            "status": row.status,
            "arc_type": row.arc_type,
            "salience": row.salience,
            "tags": row.tags,
            "subjects": row.subjects,
            "evidence": row.evidence,
            "related_storylines": row.related_storylines,
            "callback_condition": row.callback_condition,
            "resolution_summary": row.resolution_summary,
        }
    if kind == MemoryKind.FACT:
        return {
            "claim": row.claim,
            "category": row.category,
            "numbers": row.structured_numbers or {},
            "confidence": row.confidence,
            "status": row.status,
            "subjects": row.subjects,
            "originating_event_version_ids": row.originating_event_version_ids,
            "primary_tool_call_id": row.primary_tool_call_id,
            "primary_api_request_id": row.primary_api_request_id,
            "source_hints": row.additional_source_hints,
        }
    if kind == MemoryKind.EVENT:
        return {
            "event_type": row.event_type,
            "headline": row.headline,
            "summary": row.summary,
            "salience": row.salience,
            "confidence": row.confidence,
            "status": row.status,
            "details": row.details,
            "primary_tool_call_id": row.primary_tool_call_id,
            "primary_api_request_id": row.primary_api_request_id,
            "source_hints": row.additional_source_hints,
        }
    if kind == MemoryKind.TRIGGER:
        return {
            "trigger_type": row.trigger_type,
            "status": row.status,
            "fire_policy": row.fire_policy,
            "target_storyline_item_id": row.target_storyline_item_id,
            "origin_event_item_id": row.origin_event_item_id,
            "target_competition_season_id": row.target_competition_season_id,
            "target_week": row.target_week,
            "target_at": row.target_at,
            "condition": row.condition,
            "resolution_reason": row.resolution_reason,
        }
    return {
        "narrative": row.narrative_text,
        "outlook": row.outlook,
        "status": row.status,
        "tags": row.tags,
    }


def _load_evidence_versions(
    session: Session,
    revision: MemoryRevisionRef,
    version_ids: set[UUID],
) -> dict[UUID, TypedMemoryVersion]:
    if not version_ids:
        return {}
    introduced = aliased(MemoryRevision)
    eligible_ids = set(
        session.scalars(
            sa.select(MemoryVersion.id)
            .join(introduced, introduced.id == MemoryVersion.introduced_revision_id)
            .where(
                MemoryVersion.id.in_(version_ids),
                MemoryVersion.competition_id == revision.competition_id,
                introduced.sequence_number <= revision.sequence_number,
            )
        )
    )
    return _load_typed_versions(session, tuple(eligible_ids))


def _load_visible_items(
    session: Session,
    revision: MemoryRevisionRef,
    item_ids: set[UUID],
) -> dict[UUID, TypedMemoryVersion]:
    if not item_ids:
        return {}
    rows = session.execute(
        _visible_versions(revision)
        .with_only_columns(MemoryVersion.item_id, MemoryVersion.id)
        .where(MemoryVersion.item_id.in_(item_ids))
    ).all()
    version_by_item = {item_id: version_id for item_id, version_id in rows}
    versions = _load_typed_versions(session, tuple(version_by_item.values()))
    return {
        item_id: versions[version_id]
        for item_id, version_id in version_by_item.items()
    }


def _evidence_ids(version: TypedMemoryVersion) -> tuple[UUID, ...]:
    if version.kind == MemoryKind.STORYLINE:
        return tuple(reference.version_id for reference in version.content.evidence)
    if version.kind == MemoryKind.FACT:
        return tuple(version.content.originating_event_version_ids)
    return ()


def _related_item_ids(version: TypedMemoryVersion) -> tuple[UUID, ...]:
    if version.kind == MemoryKind.STORYLINE:
        return tuple(
            reference.item_id for reference in version.content.related_storylines
        )
    if version.kind == MemoryKind.TRIGGER:
        return tuple(
            item_id
            for item_id in (
                version.content.target_storyline_item_id,
                version.content.origin_event_item_id,
            )
            if item_id is not None
        )
    return ()


def _raise_invisible_version(
    session: Session,
    revision: MemoryRevisionRef,
    version_id: UUID,
) -> None:
    stored = session.get(MemoryVersion, version_id)
    if stored is None:
        raise MemoryNotFound(f"memory version not found: {version_id}")
    if stored.competition_id != revision.competition_id:
        raise MemoryScopeViolation(
            f"memory version is outside competition scope: {version_id}"
        )
    raise MemoryScopeViolation(
        f"memory version is not visible at revision {revision.id}: {version_id}"
    )


def _status_matches(status: str) -> sa.ColumnElement[bool]:
    tables = (
        StorylineVersion,
        FactVersion,
        EventVersion,
        TriggerVersion,
        ContextNoteVersion,
    )
    return sa.or_(
        *(
            sa.exists(
                sa.select(1).where(
                    table.version_id == MemoryVersion.id,
                    table.status == status,
                )
            )
            for table in tables
        )
    )


def _uuid_cursor(cursor: str) -> UUID:
    try:
        return UUID(cursor)
    except ValueError as error:
        raise ValueError("invalid memory item cursor") from error


def _sequence_cursor(cursor: str) -> int:
    try:
        sequence = int(cursor)
    except ValueError as error:
        raise ValueError("invalid memory revision cursor") from error
    if sequence < 0:
        raise ValueError("invalid memory revision cursor")
    return sequence


def _candidate_from_document(
    document: MemorySearchDocument | SearchDocument,
    lexical_score: float,
    query_entity_keys: Sequence[str],
    *,
    has_text: bool,
) -> MemoryCandidate:
    matched_entities = tuple(
        sorted(set(query_entity_keys) & set(document.entity_keys))
    )
    reasons: list[str] = []
    components: dict[str, float] = {}
    if lexical_score > 0:
        reasons.append("lexical_match")
        components["lexical"] = lexical_score
    if matched_entities:
        reasons.append("entity_overlap")
        components["entity"] = 1.0
    if document.salience is not None:
        components["salience"] = document.salience / 25
    if not reasons and not has_text and not query_entity_keys:
        reasons.append("filter_match")
        components["baseline"] = 0.0
    return MemoryCandidate(
        version_id=document.version_id,
        kind=document.kind,
        match_reasons=tuple(reasons),
        rank_components=components,
        matched_entities=matched_entities,
    )


def _fallback_text_matches(query_text: str | None, document_text: str) -> bool:
    if query_text is None:
        return False
    terms = query_text.casefold().split()
    searchable = document_text.casefold()
    return all(term in searchable for term in terms)


def _persist_search_documents(
    session: Session,
    documents: Sequence[SearchDocument],
) -> None:
    """Persist projections in the transaction already owned by the caller."""

    if not documents:
        return
    insert = pg_insert(MemorySearchDocument).values(
        [document.persistence_values() for document in documents]
    )
    mutable_columns = {
        name: getattr(insert.excluded, name)
        for name in (
            "item_id",
            "competition_id",
            "kind",
            "status",
            "salience",
            "competition_season_id",
            "week",
            "entity_keys",
            "evidence_version_ids",
            "related_item_ids",
            "tags",
            "document_text",
            "builder_version",
            "content_hash",
        )
    }
    mutable_columns["indexed_at"] = sa.func.now()
    session.execute(
        insert.on_conflict_do_update(
            index_elements=[MemorySearchDocument.version_id],
            set_=mutable_columns,
        )
    )
