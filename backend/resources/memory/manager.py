"""Canonical memory persistence and revision-grounded read operations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from backend.database.models.core import CompetitionSeason, Franchise, SeasonRoster
from backend.database.models.memory import (
    ContextNote,
    CurrentRevision,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
)
from backend.database.models.reporting import Generation, ToolCall
from backend.database.models.sleeper import ApiRequest, LeagueUser, Player, User
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.memory.errors import (
    CanonicalStateHashMismatch,
    InvalidMemoryContent,
    InvalidMemoryCursor,
    InvalidMemoryQuery,
    InvalidMemoryReference,
    MemoryNotFound,
    MemoryScopeViolation,
    SearchProjectionUnavailable,
    StaleCanonicalRevision,
)
from backend.resources.memory.content_codec import (
    decode_stored_content,
    encode_stored_content,
    typed_content_model,
    typed_content_models,
)
from backend.resources.memory.cursors import (
    decode_item_cursor,
    decode_revision_cursor,
    encode_item_cursor,
    encode_revision_cursor,
)
from backend.resources.memory.objects import (
    CreateItem,
    ContextNoteIdentity,
    DEFAULT_EXPANSION,
    ExpansionPolicy,
    HydratedMemoryVersion,
    ItemHistory,
    MemoryContent,
    MemoryListQuery,
    MemoryPage,
    MemoryQuery,
    MemoryRevision as MemoryRevisionResource,
    MemoryRevisionRef,
    MemoryKind,
    MemoryMutationBundle,
    RebuildResult,
    ReplaceItem,
    RevisionCommitted,
    RevisionPage,
    SearchIndexStatus,
    TypedMemoryVersion,
    MutationItemResult,
    MutationResult,
    NoChange,
)
from backend.resources.memory.search_documents import (
    SEARCH_DOCUMENT_BUILDER_VERSION,
    SearchDocument,
    build_search_document,
    entity_search_key,
)


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    """Raw persistence signals consumed by service-owned retrieval policy."""

    version_id: UUID
    lexical_match: bool
    matched_entities: tuple[str, ...]
    matched_evidence_version_ids: tuple[UUID, ...]
    matched_related_item_ids: tuple[UUID, ...]
    salience: int | None
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class _PreparedVersion:
    operation_index: int
    client_key: str | None
    item_id: UUID
    version_id: UUID
    content: MemoryContent
    context_note_identity: ContextNoteIdentity | None
    revision_number: int
    replaced_version_id: UUID | None
    change_reason: str | None


_EXPECTED_IDENTITY_CONSTRAINTS = frozenset(
    {
        "pk_memory_items",
        "pk_memory_versions",
        "uq_memory_items_id_competition",
        "uq_memory_versions_id_competition",
        "uq_memory_versions_item_revision",
        "uq_context_notes_competition_key",
        "uq_context_notes_season_key",
        "uq_context_notes_franchise_key",
    }
)

_MIN_CANDIDATES_PER_SIGNAL = 20
_MAX_CANDIDATES_PER_SIGNAL = 200
_CANDIDATES_PER_RESULT = 2
_MAX_FALLBACK_VISIBLE_SCAN = 5_000
_MAX_FALLBACK_CANDIDATES = 800


class MemoryManager:
    """Deep persistence boundary for the canonical memory aggregate."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def apply(self, bundle: MemoryMutationBundle) -> MutationResult:
        """Validate and atomically commit one complete canonical mutation bundle."""

        try:
            with transaction_session(self._session_factory) as session:
                generation = session.get(Generation, bundle.producing_generation_id)
                if generation is None:
                    raise MemoryNotFound(
                        f"producing generation not found: {bundle.producing_generation_id}"
                    )
                existing = _revision_for_generation(session, generation.id)
                if existing is not None:
                    return _committed_result(session, existing)

                current = session.scalar(
                    sa.select(CurrentRevision)
                    .where(CurrentRevision.competition_id == generation.competition_id)
                    .with_for_update()
                )
                if current is None:
                    raise MemoryNotFound(
                        "current memory revision not found for producing generation"
                    )

                # A concurrent retry may have committed while this transaction waited
                # for the competition pointer lock.
                existing = _revision_for_generation(session, generation.id)
                if existing is not None:
                    return _committed_result(session, existing)

                current_revision = session.get(
                    MemoryRevision, current.current_revision_id
                )
                if current_revision is None:
                    raise MemoryNotFound(
                        f"current memory revision not found: {current.current_revision_id}"
                    )
                if generation.input_memory_revision_id is None:
                    if not bundle.operations:
                        return NoChange(
                            revision=_revision_ref(current_revision),
                            reason="mutation bundle contains no operations",
                        )
                    raise InvalidMemoryReference(
                        "producing generation does not have a canonical memory input",
                        details={"generation_id": str(generation.id)},
                    )
                pinned_base = session.get(
                    MemoryRevision, generation.input_memory_revision_id
                )
                if pinned_base is None:
                    raise MemoryNotFound(
                        "generation input memory revision was not found"
                    )
                if pinned_base.competition_id != generation.competition_id:
                    raise MemoryScopeViolation(
                        "generation input memory revision is outside its competition"
                    )
                base_ref = _revision_ref(pinned_base)
                if not bundle.operations:
                    return NoChange(
                        revision=base_ref,
                        reason="mutation bundle contains no operations",
                    )

                prepared = _prepare_mutation(
                    session,
                    bundle,
                    generation,
                    base_ref,
                )
                if not prepared:
                    return NoChange(
                        revision=base_ref,
                        reason="mutation bundle does not change canonical memory",
                    )
                if current.current_revision_id != generation.input_memory_revision_id:
                    current_ref = _revision_ref(current_revision)
                    surviving_indexes = {
                        item.operation_index for item in prepared
                    }
                    surviving_bundle = MemoryMutationBundle(
                        producing_generation_id=bundle.producing_generation_id,
                        operations=tuple(
                            operation
                            for index, operation in enumerate(bundle.operations)
                            if index in surviving_indexes
                        ),
                    )
                    current_prepared = _prepare_mutation(
                        session,
                        surviving_bundle,
                        generation,
                        current_ref,
                    )
                    if not current_prepared:
                        return NoChange(
                            revision=current_ref,
                            reason="mutation transitions are already represented",
                        )
                    raise StaleCanonicalRevision(
                        "canonical memory advanced after the generation was pinned",
                        details={
                            "generation_id": str(generation.id),
                            "expected_revision_id": str(
                                generation.input_memory_revision_id
                            ),
                            "current_revision_id": str(current.current_revision_id),
                        },
                    )

                revision_id = uuid4()
                recorded_at = datetime.now(UTC)
                revision = MemoryRevision(
                    id=revision_id,
                    competition_id=generation.competition_id,
                    sequence_number=pinned_base.sequence_number + 1,
                    previous_revision_id=pinned_base.id,
                    producing_generation_id=generation.id,
                    competition_season_id=generation.competition_season_id,
                    week=generation.domain_cutoff_week,
                    knowledge_cutoff_at=generation.knowledge_cutoff_at,
                    state_content_hash=_resulting_state_hash(
                        session,
                        base_ref,
                        prepared,
                    ),
                    created_at=recorded_at,
                )
                session.add(revision)
                session.flush()

                _persist_prepared_versions(
                    session,
                    prepared,
                    generation,
                    revision_id,
                    recorded_at,
                )
                stored_hash = _stored_state_hash(
                    session,
                    MemoryRevisionRef(
                        id=revision_id,
                        competition_id=generation.competition_id,
                        sequence_number=revision.sequence_number,
                        state_content_hash=revision.state_content_hash,
                    ),
                )
                if stored_hash != revision.state_content_hash:
                    raise CanonicalStateHashMismatch(
                        "stored canonical memory does not match its resulting-state hash",
                    )
                typed_versions = _typed_prepared_versions(
                    prepared,
                    generation,
                    revision_id,
                    recorded_at,
                )
                _persist_search_documents(
                    session,
                    [build_search_document(version) for version in typed_versions],
                )

                current.current_revision_id = revision_id
                current.lock_version += 1
                current.updated_at = recorded_at
                session.flush()

                return _committed_result(session, revision)
        except IntegrityError as error:
            if _integrity_constraint(error) not in _EXPECTED_IDENTITY_CONSTRAINTS:
                raise
            raise InvalidMemoryReference(
                "memory mutation conflicts with a persisted canonical identity",
                details={"generation_id": str(bundle.producing_generation_id)},
            ) from error

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
            cursor = decode_item_cursor(query.cursor)
            if cursor.revision_id != revision.id:
                raise InvalidMemoryCursor(
                    "memory item cursor belongs to a different revision",
                    details={
                        "cursor_revision_id": str(cursor.revision_id),
                        "revision_id": str(revision.id),
                    },
                )
            statement = statement.where(MemoryItem.id > cursor.item_id)
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
        next_cursor = (
            encode_item_cursor(revision.id, page_rows[-1][0])
            if len(rows) > query.limit
            else None
        )
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
            raise InvalidMemoryQuery(
                "revision page limit must be between 1 and 100",
                details={"limit": limit},
            )
        statement = sa.select(MemoryRevision).where(
            MemoryRevision.competition_id == competition_id
        )
        if cursor is not None:
            decoded_cursor = decode_revision_cursor(cursor)
            if decoded_cursor.competition_id != competition_id:
                raise InvalidMemoryCursor(
                    "memory revision cursor belongs to a different competition",
                    details={
                        "cursor_competition_id": str(decoded_cursor.competition_id),
                        "competition_id": str(competition_id),
                    },
                )
            statement = statement.where(
                MemoryRevision.sequence_number < decoded_cursor.sequence_number
            )
        statement = statement.order_by(MemoryRevision.sequence_number.desc()).limit(
            limit + 1
        )
        with read_only_session(self._session_factory) as session:
            rows = list(session.scalars(statement))
        page_rows = rows[:limit]
        next_cursor = (
            encode_revision_cursor(
                competition_id,
                page_rows[-1].sequence_number,
            )
            if len(rows) > limit
            else None
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
            MemoryVersion.id,
            MemoryVersion.recorded_at,
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
            evidence_version_ids = tuple(
                sorted(query.evidence_version_ids, key=str)
            )
            related_item_ids = tuple(sorted(query.related_item_ids, key=str))
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
            lexical_match = (
                MemorySearchDocument.search_vector.op("@@")(text_query)
                if text_query is not None
                else sa.false()
            ).label("lexical_match")
            entity_match = (
                MemorySearchDocument.entity_keys.overlap(entity_keys)
                if entity_keys
                else sa.false()
            ).label("entity_match")
            evidence_match = (
                MemorySearchDocument.evidence_version_ids.overlap(
                    evidence_version_ids
                )
                if evidence_version_ids
                else sa.false()
            ).label("evidence_match")
            related_match = (
                MemorySearchDocument.related_item_ids.overlap(related_item_ids)
                if related_item_ids
                else sa.false()
            ).label("related_match")
            statement = (
                sa.select(
                    MemorySearchDocument,
                    lexical_match,
                    entity_match,
                    evidence_match,
                    related_match,
                    visible.c.recorded_at,
                )
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
            signal_queries: list[
                tuple[sa.ColumnElement[bool], tuple[sa.ColumnElement[Any], ...]]
            ] = []
            if text_query is not None:
                signal_queries.append(
                    (
                        MemorySearchDocument.search_vector.op("@@")(text_query),
                        (lexical_rank.desc(), visible.c.recorded_at.desc()),
                    )
                )
            if entity_keys:
                signal_queries.append(
                    (entity_match, (visible.c.recorded_at.desc(),))
                )
            if evidence_version_ids:
                signal_queries.append(
                    (evidence_match, (visible.c.recorded_at.desc(),))
                )
            if related_item_ids:
                signal_queries.append(
                    (related_match, (visible.c.recorded_at.desc(),))
                )

            if signal_queries:
                per_signal_limit = min(
                    max(
                        query.limit * _CANDIDATES_PER_RESULT,
                        _MIN_CANDIDATES_PER_SIGNAL,
                    ),
                    _MAX_CANDIDATES_PER_SIGNAL,
                )
                candidate_ids: set[UUID] = set()
                for condition, ordering in signal_queries:
                    candidate_ids.update(
                        session.scalars(
                            statement.where(condition)
                            .with_only_columns(MemorySearchDocument.version_id)
                            .order_by(*ordering, MemorySearchDocument.version_id)
                            .limit(per_signal_limit)
                        )
                    )
                if not candidate_ids:
                    return ()
                statement = statement.where(
                    MemorySearchDocument.version_id.in_(candidate_ids)
                )
            else:
                statement = statement.order_by(
                    visible.c.recorded_at.desc(),
                    MemorySearchDocument.version_id,
                ).limit(_MAX_CANDIDATES_PER_SIGNAL)
            rows = session.execute(
                statement.order_by(MemorySearchDocument.version_id)
            ).all()

        return tuple(
            _candidate_from_document(
                document,
                bool(lexical_matched),
                entity_keys,
                evidence_version_ids,
                related_item_ids,
                recorded_at,
            )
            for (
                document,
                lexical_matched,
                _entity_match,
                _evidence_match,
                _related_match,
                recorded_at,
            ) in rows
        )

    def scan_visible_candidates(
        self,
        revision: MemoryRevisionRef,
        query: MemoryQuery,
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
        if query.statuses:
            statement = statement.where(
                sa.or_(*(_status_matches(status.value) for status in query.statuses))
            )
        statement = statement.order_by(
            MemoryVersion.recorded_at.desc(), MemoryVersion.id
        ).limit(_MAX_FALLBACK_VISIBLE_SCAN)

        with read_only_session(self._session_factory) as session:
            version_ids = list(
                session.scalars(statement.with_only_columns(MemoryVersion.id))
            )
            versions = _load_typed_versions(session, version_ids)

        entity_keys = tuple(
            sorted({entity_search_key(entity) for entity in query.entities})
        )
        evidence_version_ids = tuple(sorted(query.evidence_version_ids, key=str))
        related_item_ids = tuple(sorted(query.related_item_ids, key=str))
        candidates: dict[UUID, MemoryCandidate] = {}
        selected_per_signal = {
            "lexical": 0,
            "entity": 0,
            "evidence": 0,
            "related": 0,
        }
        has_retrieval_signal = bool(
            query.text is not None
            or entity_keys
            or evidence_version_ids
            or related_item_ids
        )
        for version_id in version_ids:
            version = versions[version_id]
            document = build_search_document(version)
            lexical_match = _fallback_text_matches(query.text, document.document_text)
            entity_match = bool(set(entity_keys) & set(document.entity_keys))
            evidence_match = bool(
                set(evidence_version_ids) & set(document.evidence_version_ids)
            )
            related_match = bool(
                set(related_item_ids) & set(document.related_item_ids)
            )
            if (
                query.text is not None
                or entity_keys
                or evidence_version_ids
                or related_item_ids
            ) and not (
                lexical_match or entity_match or evidence_match or related_match
            ):
                continue
            matched_signals = tuple(
                name
                for name, matched in (
                    ("lexical", lexical_match),
                    ("entity", entity_match),
                    ("evidence", evidence_match),
                    ("related", related_match),
                )
                if matched
            )
            selected = not has_retrieval_signal and (
                len(candidates) < _MAX_FALLBACK_CANDIDATES
            )
            for signal in matched_signals:
                if selected_per_signal[signal] < _MAX_CANDIDATES_PER_SIGNAL:
                    selected_per_signal[signal] += 1
                    selected = True
            if selected:
                candidates[version_id] = _candidate_from_document(
                    document,
                    lexical_match,
                    entity_keys,
                    evidence_version_ids,
                    related_item_ids,
                    version.recorded_at,
                )
        return tuple(candidates.values())

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


def _revision_for_generation(
    session: Session,
    generation_id: UUID,
) -> MemoryRevision | None:
    return session.scalar(
        sa.select(MemoryRevision).where(
            MemoryRevision.producing_generation_id == generation_id
        )
    )


def _committed_result(
    session: Session,
    revision: MemoryRevision,
) -> RevisionCommitted:
    rows = session.execute(
        sa.select(MemoryVersion, MemoryItem)
        .join(MemoryItem, MemoryItem.id == MemoryVersion.item_id)
        .where(MemoryVersion.introduced_revision_id == revision.id)
        .order_by(MemoryVersion.item_id, MemoryVersion.id)
    )
    return RevisionCommitted(
        revision=_revision_ref(revision),
        items=tuple(
            MutationItemResult(
                client_key=(item.agent_key if version.revision_number == 1 else None),
                item_id=version.item_id,
                version_id=version.id,
            )
            for version, item in rows
        )
    )


def _prepare_mutation(
    session: Session,
    bundle: MemoryMutationBundle,
    generation: Generation,
    base: MemoryRevisionRef,
) -> tuple[_PreparedVersion, ...]:
    creates = [
        (index, operation)
        for index, operation in enumerate(bundle.operations)
        if isinstance(operation, CreateItem)
    ]
    replacements = [
        (index, operation)
        for index, operation in enumerate(bundle.operations)
        if isinstance(operation, ReplaceItem)
    ]
    _reject_duplicate_values(
        "client key",
        [operation.client_key for _, operation in creates],
    )
    _reject_duplicate_values(
        "generated item ID",
        [operation.item_id for _, operation in creates],
    )
    _reject_duplicate_values(
        "generated version ID",
        [operation.version_id for _, operation in creates],
    )
    _reject_duplicate_values(
        "replacement target",
        [operation.item_id for _, operation in replacements],
    )
    create_item_ids = {operation.item_id for _, operation in creates}
    replaced_item_ids = {operation.item_id for _, operation in replacements}
    overlap = create_item_ids & replaced_item_ids
    if overlap:
        _invalid_reference(
            "an item cannot be created and replaced in the same bundle",
            next(iter(overlap)),
        )

    represented_creates = _represented_create_indexes(
        session,
        creates,
        generation.competition_id,
        base,
    )

    stored_targets = {
        row.id: row
        for row in session.scalars(
            sa.select(MemoryItem).where(MemoryItem.id.in_(replaced_item_ids))
        )
    }
    for _, operation in replacements:
        target = stored_targets.get(operation.item_id)
        if target is None:
            _invalid_reference("replacement target does not exist", operation.item_id)
        if target.competition_id != generation.competition_id:
            raise MemoryScopeViolation(
                "replacement target is outside the producing competition",
                details={"item_id": str(operation.item_id)},
            )
        if target.kind != operation.content.kind:
            raise InvalidMemoryContent(
                "replacement content kind does not match its stable item",
                details={
                    "item_id": str(operation.item_id),
                    "target_kind": target.kind,
                    "content_kind": operation.content.kind,
                },
            )

    visible_rows = session.execute(
        _visible_versions(base)
        .with_only_columns(MemoryVersion.item_id, MemoryVersion.id)
        .where(MemoryVersion.item_id.in_(replaced_item_ids))
    ).all()
    visible_by_item = {item_id: version_id for item_id, version_id in visible_rows}
    for item_id in replaced_item_ids:
        if item_id not in visible_by_item:
            _invalid_reference(
                "replacement target is not visible at the generation input revision",
                item_id,
            )
    current_versions = _load_typed_versions(
        session,
        tuple(visible_by_item.values()),
    )

    prepared: list[_PreparedVersion] = [
        _PreparedVersion(
            operation_index=index,
            client_key=operation.client_key,
            item_id=operation.item_id,
            version_id=operation.version_id,
            content=operation.content,
            context_note_identity=operation.context_note_identity,
            revision_number=1,
            replaced_version_id=None,
            change_reason=None,
        )
        for index, operation in creates
        if index not in represented_creates
    ]
    for index, operation in replacements:
        previous = current_versions[visible_by_item[operation.item_id]]
        if _canonical_content(previous.content) == _canonical_content(
            operation.content
        ):
            continue
        prepared.append(
            _PreparedVersion(
                operation_index=index,
                client_key=None,
                item_id=operation.item_id,
                version_id=uuid4(),
                content=operation.content,
                context_note_identity=previous.context_note_identity,
                revision_number=previous.revision_number + 1,
                replaced_version_id=previous.version_id,
                change_reason=operation.change_reason,
            )
        )

    prepared.sort(key=lambda item: item.operation_index)
    _validate_memory_references(
        session,
        generation.competition_id,
        base,
        prepared,
    )
    _validate_scoped_resources(session, generation, prepared)
    _validate_context_note_keys(
        session,
        generation.competition_id,
        base,
        prepared,
    )
    return tuple(prepared)


def _represented_create_indexes(
    session: Session,
    creates: Sequence[tuple[int, CreateItem]],
    competition_id: UUID,
    revision: MemoryRevisionRef,
) -> set[int]:
    if not creates:
        return set()
    item_ids = {operation.item_id for _, operation in creates}
    version_ids = {operation.version_id for _, operation in creates}
    stored_items = {
        row.id: row
        for row in session.scalars(
            sa.select(MemoryItem).where(MemoryItem.id.in_(item_ids))
        )
    }
    stored_versions = {
        row.id: row
        for row in session.scalars(
            sa.select(MemoryVersion).where(MemoryVersion.id.in_(version_ids))
        )
    }
    visible_rows = session.execute(
        _visible_versions(revision)
        .with_only_columns(MemoryVersion.item_id, MemoryVersion.id)
        .where(
            sa.or_(
                MemoryVersion.item_id.in_(item_ids),
                MemoryVersion.id.in_(version_ids),
            )
        )
    ).all()
    visible_item_ids = {item_id for item_id, _ in visible_rows}
    visible_version_ids = {version_id for _, version_id in visible_rows}
    represented: set[int] = set()
    for index, operation in creates:
        item = stored_items.get(operation.item_id)
        version = stored_versions.get(operation.version_id)
        for stored in (item, version):
            if stored is not None and stored.competition_id != competition_id:
                raise MemoryScopeViolation(
                    "generated memory identity exists in another competition",
                    details={"reference_id": str(operation.item_id)},
                )
        item_visible = operation.item_id in visible_item_ids
        version_visible = operation.version_id in visible_version_ids
        if not item_visible and not version_visible:
            continue
        if (
            item is None
            or version is None
            or not item_visible
            or not version_visible
            or version.item_id != operation.item_id
            or item.kind != operation.content.kind
        ):
            _invalid_reference(
                "generated memory identity conflicts with canonical state",
                operation.item_id,
            )
        stored_content = _load_typed_versions(session, [version.id])[version.id]
        if (
            _canonical_content(stored_content.content)
            != _canonical_content(operation.content)
            or stored_content.context_note_identity != operation.context_note_identity
        ):
            _invalid_reference(
                "generated memory identity has different canonical content",
                operation.item_id,
            )
        represented.add(index)
    return represented


def _reject_duplicate_values(label: str, values: Sequence[object]) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise InvalidMemoryReference(
                f"duplicate {label} in mutation bundle",
                details={"value": str(value)},
            )
        seen.add(value)


def _invalid_reference(message: str, reference_id: UUID) -> None:
    raise InvalidMemoryReference(
        message,
        details={"reference_id": str(reference_id)},
    )


def _validate_memory_references(
    session: Session,
    competition_id: UUID,
    base: MemoryRevisionRef,
    prepared: Sequence[_PreparedVersion],
) -> None:
    new_version_kinds = {
        item.version_id: MemoryKind(item.content.kind) for item in prepared
    }
    new_item_kinds = {item.item_id: MemoryKind(item.content.kind) for item in prepared}
    exact_references: dict[UUID, MemoryKind] = {}
    item_references: dict[UUID, MemoryKind] = {}
    for item in prepared:
        content = item.content
        if content.kind == MemoryKind.STORYLINE.value:
            for reference in content.evidence:
                _register_expected_kind(
                    exact_references,
                    reference.version_id,
                    MemoryKind(reference.kind),
                )
            for reference in content.related_storylines:
                _register_expected_kind(
                    item_references,
                    reference.item_id,
                    MemoryKind.STORYLINE,
                )
        elif content.kind == MemoryKind.FACT.value:
            for version_id in content.originating_event_version_ids:
                _register_expected_kind(
                    exact_references,
                    version_id,
                    MemoryKind.EVENT,
                )
        elif content.kind == MemoryKind.TRIGGER.value:
            if content.target_storyline_item_id is not None:
                _register_expected_kind(
                    item_references,
                    content.target_storyline_item_id,
                    MemoryKind.STORYLINE,
                )
            if content.origin_event_item_id is not None:
                _register_expected_kind(
                    item_references,
                    content.origin_event_item_id,
                    MemoryKind.EVENT,
                )

    persisted_version_ids = set(exact_references) - set(new_version_kinds)
    persisted_versions = {
        row.id: (row, memory_item)
        for row, memory_item in session.execute(
            sa.select(MemoryVersion, MemoryItem)
            .join(MemoryItem, MemoryItem.id == MemoryVersion.item_id)
            .where(MemoryVersion.id.in_(persisted_version_ids))
        )
    }
    introduced = aliased(MemoryRevision)
    available_version_ids = set(
        session.scalars(
            sa.select(MemoryVersion.id)
            .join(introduced, introduced.id == MemoryVersion.introduced_revision_id)
            .where(
                MemoryVersion.id.in_(persisted_version_ids),
                introduced.sequence_number <= base.sequence_number,
            )
        )
    )
    for version_id, expected_kind in exact_references.items():
        if version_id in new_version_kinds:
            actual_kind = new_version_kinds[version_id]
        else:
            stored = persisted_versions.get(version_id)
            if stored is None:
                _invalid_reference("referenced memory version does not exist", version_id)
            envelope, memory_item = stored
            if envelope.competition_id != competition_id:
                raise MemoryScopeViolation(
                    "referenced memory version is outside the producing competition",
                    details={"version_id": str(version_id)},
                )
            if version_id not in available_version_ids:
                _invalid_reference(
                    "referenced memory version was not available at the generation input",
                    version_id,
                )
            actual_kind = MemoryKind(memory_item.kind)
        if actual_kind is not expected_kind:
            raise InvalidMemoryReference(
                "referenced memory version has the wrong kind",
                details={
                    "version_id": str(version_id),
                    "expected_kind": expected_kind.value,
                    "actual_kind": actual_kind.value,
                },
            )

    persisted_item_ids = set(item_references) - set(new_item_kinds)
    persisted_items = {
        row.id: row
        for row in session.scalars(
            sa.select(MemoryItem).where(MemoryItem.id.in_(persisted_item_ids))
        )
    }
    visible_item_ids = set(
        session.scalars(
            _visible_versions(base)
            .with_only_columns(MemoryVersion.item_id)
            .where(MemoryVersion.item_id.in_(persisted_item_ids))
        )
    )
    for item_id, expected_kind in item_references.items():
        if item_id in new_item_kinds:
            actual_kind = new_item_kinds[item_id]
        else:
            stored = persisted_items.get(item_id)
            if stored is None:
                _invalid_reference("referenced memory item does not exist", item_id)
            if stored.competition_id != competition_id:
                raise MemoryScopeViolation(
                    "referenced memory item is outside the producing competition",
                    details={"item_id": str(item_id)},
                )
            if item_id not in visible_item_ids:
                _invalid_reference(
                    "referenced memory item is not visible at the generation input",
                    item_id,
                )
            actual_kind = MemoryKind(stored.kind)
        if actual_kind is not expected_kind:
            raise InvalidMemoryReference(
                "referenced memory item has the wrong kind",
                details={
                    "item_id": str(item_id),
                    "expected_kind": expected_kind.value,
                    "actual_kind": actual_kind.value,
                },
            )


def _register_expected_kind(
    references: dict[UUID, MemoryKind],
    reference_id: UUID,
    expected_kind: MemoryKind,
) -> None:
    previous = references.get(reference_id)
    if previous is not None and previous is not expected_kind:
        raise InvalidMemoryReference(
            "memory reference has contradictory kind expectations",
            details={
                "reference_id": str(reference_id),
                "first_kind": previous.value,
                "second_kind": expected_kind.value,
            },
        )
    references[reference_id] = expected_kind


def _validate_scoped_resources(
    session: Session,
    generation: Generation,
    prepared: Sequence[_PreparedVersion],
) -> None:
    ids_by_model: dict[type[Any], set[UUID]] = {
        CompetitionSeason: {generation.competition_season_id},
        Franchise: set(),
        SeasonRoster: set(),
    }
    player_ids: set[str] = set()
    user_ids: set[str] = set()
    tool_call_ids: set[UUID] = set()
    api_request_ids: set[UUID] = set()
    for item in prepared:
        subjects = getattr(item.content, "subjects", ())
        for subject in subjects:
            if subject.kind == "franchise":
                ids_by_model[Franchise].add(subject.id)
            elif subject.kind == "season_roster":
                ids_by_model[SeasonRoster].add(subject.id)
            elif subject.kind == "competition_season":
                ids_by_model[CompetitionSeason].add(subject.id)
            elif subject.kind == "player":
                player_ids.add(subject.id)
            elif subject.kind == "sleeper_user":
                user_ids.add(subject.id)
        if item.content.kind == MemoryKind.EVENT.value:
            details = item.content.details
            for name in (
                "sender_franchise_id",
                "receiver_franchise_id",
                "winner_franchise_id",
                "loser_franchise_id",
                "franchise_id",
            ):
                value = getattr(details, name, None)
                if value is not None:
                    ids_by_model[Franchise].add(value)
            for asset in getattr(details, "assets", ()):
                player_id = getattr(asset, "player_id", None)
                if player_id is not None:
                    player_ids.add(player_id)
                roster_id = getattr(asset, "original_season_roster_id", None)
                if roster_id is not None:
                    ids_by_model[SeasonRoster].add(roster_id)
            for name in ("added_player_id", "dropped_player_id"):
                player_id = getattr(details, name, None)
                if player_id is not None:
                    player_ids.add(player_id)
        if item.content.kind == MemoryKind.TRIGGER.value:
            season_id = item.content.target_competition_season_id
            if season_id is not None:
                ids_by_model[CompetitionSeason].add(season_id)
            subject = getattr(item.content.condition, "subject", None)
            if subject is not None:
                if subject.kind == "franchise":
                    ids_by_model[Franchise].add(subject.id)
                elif subject.kind == "season_roster":
                    ids_by_model[SeasonRoster].add(subject.id)
                elif subject.kind == "competition_season":
                    ids_by_model[CompetitionSeason].add(subject.id)
                elif subject.kind == "player":
                    player_ids.add(subject.id)
                elif subject.kind == "sleeper_user":
                    user_ids.add(subject.id)
        tool_call_id = getattr(item.content, "primary_tool_call_id", None)
        if tool_call_id is not None:
            tool_call_ids.add(tool_call_id)
        api_request_id = getattr(item.content, "primary_api_request_id", None)
        if api_request_id is not None:
            api_request_ids.add(api_request_id)
        identity = item.context_note_identity
        if identity is not None:
            if identity.competition_season_id is not None:
                ids_by_model[CompetitionSeason].add(identity.competition_season_id)
            if identity.franchise_id is not None:
                ids_by_model[Franchise].add(identity.franchise_id)

    for model, resource_ids in ids_by_model.items():
        if not resource_ids:
            continue
        stored = {
            row.id: row
            for row in session.scalars(sa.select(model).where(model.id.in_(resource_ids)))
        }
        for resource_id in resource_ids:
            row = stored.get(resource_id)
            if row is None:
                _invalid_reference("referenced scoped resource does not exist", resource_id)
            if row.competition_id != generation.competition_id:
                raise MemoryScopeViolation(
                    "referenced resource is outside the producing competition",
                    details={"reference_id": str(resource_id)},
                )
    _validate_player_references(session, player_ids)
    _validate_user_references(
        session,
        generation.competition_season_id,
        user_ids,
    )
    _validate_source_receipts(
        session,
        generation,
        tool_call_ids,
        api_request_ids,
    )
    for item in prepared:
        identity = item.context_note_identity
        if (
            identity is not None
            and identity.competition_season_id is not None
            and identity.competition_season_id != generation.competition_season_id
        ):
            raise InvalidMemoryReference(
                "context-note season must match the producing generation season",
                details={"item_id": str(item.item_id)},
            )


def _validate_player_references(session: Session, player_ids: set[str]) -> None:
    if not player_ids:
        return
    stored_ids = set(
        session.scalars(
            sa.select(Player.sleeper_player_id).where(
                Player.sleeper_player_id.in_(player_ids)
            )
        )
    )
    missing = player_ids - stored_ids
    if missing:
        raise InvalidMemoryReference(
            "referenced Sleeper player does not exist",
            details={"player_id": min(missing)},
        )


def _validate_user_references(
    session: Session,
    competition_season_id: UUID,
    user_ids: set[str],
) -> None:
    if not user_ids:
        return
    stored_ids = set(
        session.scalars(
            sa.select(User.sleeper_user_id).where(
                User.sleeper_user_id.in_(user_ids)
            )
        )
    )
    missing = user_ids - stored_ids
    if missing:
        raise InvalidMemoryReference(
            "referenced Sleeper user does not exist",
            details={"sleeper_user_id": min(missing)},
        )
    member_ids = set(
        session.scalars(
            sa.select(LeagueUser.sleeper_user_id).where(
                LeagueUser.competition_season_id == competition_season_id,
                LeagueUser.sleeper_user_id.in_(user_ids),
            )
        )
    )
    outside_scope = user_ids - member_ids
    if outside_scope:
        raise MemoryScopeViolation(
            "referenced Sleeper user is outside the producing season",
            details={"sleeper_user_id": min(outside_scope)},
        )


def _validate_source_receipts(
    session: Session,
    generation: Generation,
    tool_call_ids: set[UUID],
    api_request_ids: set[UUID],
) -> None:
    tool_calls = {
        row.id: row
        for row in session.scalars(
            sa.select(ToolCall).where(ToolCall.id.in_(tool_call_ids))
        )
    }
    for tool_call_id in tool_call_ids:
        tool_call = tool_calls.get(tool_call_id)
        if tool_call is None:
            _invalid_reference("primary tool-call receipt does not exist", tool_call_id)
        if tool_call.generation_id != generation.id:
            raise MemoryScopeViolation(
                "primary tool-call receipt belongs to another generation",
                details={"tool_call_id": str(tool_call_id)},
            )

    api_requests = {
        row.id: row
        for row in session.scalars(
            sa.select(ApiRequest).where(ApiRequest.id.in_(api_request_ids))
        )
    }
    for api_request_id in api_request_ids:
        api_request = api_requests.get(api_request_id)
        if api_request is None:
            _invalid_reference("primary API-request receipt does not exist", api_request_id)
        if api_request.competition_season_id != generation.competition_season_id:
            raise MemoryScopeViolation(
                "primary API-request receipt is outside the producing season",
                details={"api_request_id": str(api_request_id)},
            )


def _validate_context_note_keys(
    session: Session,
    competition_id: UUID,
    revision: MemoryRevisionRef,
    prepared: Sequence[_PreparedVersion],
) -> None:
    identities = [
        (item.item_id, item.context_note_identity)
        for item in prepared
        if item.replaced_version_id is None and item.context_note_identity is not None
    ]
    keys: list[tuple[object, ...]] = []
    for _, identity in identities:
        keys.append(
            (
                identity.scope.value,
                identity.competition_season_id,
                identity.franchise_id,
                identity.note_key,
            )
        )
    _reject_duplicate_values("context-note identity", keys)
    for item_id, identity in identities:
        statement = sa.select(ContextNote.item_id).where(
            ContextNote.competition_id == competition_id,
            ContextNote.scope == identity.scope.value,
            ContextNote.note_key == identity.note_key,
        )
        if identity.competition_season_id is not None:
            statement = statement.where(
                ContextNote.competition_season_id == identity.competition_season_id
            )
        if identity.franchise_id is not None:
            statement = statement.where(ContextNote.franchise_id == identity.franchise_id)
        existing_item_id = session.scalar(statement)
        if existing_item_id is not None and session.scalar(
            sa.select(
                sa.exists(
                    _visible_versions(revision)
                    .with_only_columns(MemoryVersion.id)
                    .where(MemoryVersion.item_id == existing_item_id)
                )
            )
        ):
            _invalid_reference("context-note identity already exists", item_id)


def _resulting_state_hash(
    session: Session,
    base: MemoryRevisionRef,
    prepared: Sequence[_PreparedVersion],
) -> str:
    visible_ids = list(
        session.scalars(_visible_versions(base).with_only_columns(MemoryVersion.id))
    )
    current: dict[UUID, tuple[MemoryContent, ContextNoteIdentity | None]] = {
        version.item_id: (version.content, version.context_note_identity)
        for version in _load_typed_versions(session, visible_ids).values()
    }
    for item in prepared:
        current[item.item_id] = (item.content, item.context_note_identity)
    return _state_hash(current)


def _stored_state_hash(session: Session, revision: MemoryRevisionRef) -> str:
    visible_ids = list(
        session.scalars(_visible_versions(revision).with_only_columns(MemoryVersion.id))
    )
    stored = {
        version.item_id: (version.content, version.context_note_identity)
        for version in _load_typed_versions(session, visible_ids).values()
    }
    return _state_hash(stored)


def _state_hash(
    state_by_item: Mapping[
        UUID,
        tuple[MemoryContent, ContextNoteIdentity | None],
    ],
) -> str:
    state = [
        {
            "item_id": str(item_id),
            "content": content.model_dump(mode="json"),
            "context_note_identity": (
                identity.model_dump(mode="json")
                if identity is not None
                else None
            ),
        }
        for item_id, (content, identity) in sorted(
            state_by_item.items(), key=lambda pair: pair[0].hex
        )
    ]
    return sha256(_canonical_json_bytes(state)).hexdigest()


def _persist_prepared_versions(
    session: Session,
    prepared: Sequence[_PreparedVersion],
    generation: Generation,
    revision_id: UUID,
    recorded_at: datetime,
) -> None:
    creates = [item for item in prepared if item.replaced_version_id is None]
    session.add_all(
        [
            MemoryItem(
                id=item.item_id,
                competition_id=generation.competition_id,
                kind=item.content.kind,
                agent_key=item.client_key,
                created_at=recorded_at,
            )
            for item in creates
        ]
    )
    # The context-note FK is composite and has no ORM relationship edge; make the
    # stable items visible before adding their one-to-one identities.
    session.flush()
    session.add_all(
        [
            ContextNote(
                item_id=item.item_id,
                competition_id=generation.competition_id,
                scope=item.context_note_identity.scope.value,
                competition_season_id=item.context_note_identity.competition_season_id,
                franchise_id=item.context_note_identity.franchise_id,
                note_key=item.context_note_identity.note_key,
            )
            for item in creates
            if item.context_note_identity is not None
        ]
    )
    replaced_ids = [
        item.replaced_version_id
        for item in prepared
        if item.replaced_version_id is not None
    ]
    if replaced_ids:
        session.execute(
            sa.update(MemoryVersion)
            .where(
                MemoryVersion.id.in_(replaced_ids),
                MemoryVersion.retired_revision_id.is_(None),
            )
            .values(retired_revision_id=revision_id)
        )
    session.add_all(
        [
            MemoryVersion(
                id=item.version_id,
                item_id=item.item_id,
                competition_id=generation.competition_id,
                revision_number=item.revision_number,
                content_schema_version=item.content.schema_version,
                introduced_revision_id=revision_id,
                retired_revision_id=None,
                competition_season_id=generation.competition_season_id,
                week=generation.domain_cutoff_week,
                occurred_at=None,
                creating_generation_id=generation.id,
                creating_tool_call_id=None,
                change_reason=item.change_reason,
                recorded_at=recorded_at,
            )
            for item in prepared
        ]
    )
    session.flush()
    session.add_all(
        [
            encode_stored_content(
                item.version_id,
                generation.competition_id,
                generation.id,
                item.content,
            )
            for item in prepared
        ]
    )
    session.flush()


def _typed_prepared_versions(
    prepared: Sequence[_PreparedVersion],
    generation: Generation,
    revision_id: UUID,
    recorded_at: datetime,
) -> tuple[TypedMemoryVersion, ...]:
    return tuple(
        _typed_prepared_version(
            item,
            competition_id=generation.competition_id,
            competition_season_id=generation.competition_season_id,
            week=generation.domain_cutoff_week,
            generation_id=generation.id,
            revision_id=revision_id,
            recorded_at=recorded_at,
        )
        for item in prepared
    )


def _typed_prepared_version(
    item: _PreparedVersion,
    *,
    competition_id: UUID,
    competition_season_id: UUID | None,
    week: int | None,
    generation_id: UUID,
    revision_id: UUID,
    recorded_at: datetime,
) -> TypedMemoryVersion:
    return TypedMemoryVersion(
        version_id=item.version_id,
        item_id=item.item_id,
        competition_id=competition_id,
        kind=MemoryKind(item.content.kind),
        content=item.content,
        content_schema_version=item.content.schema_version,
        revision_number=item.revision_number,
        introduced_revision_id=revision_id,
        competition_season_id=competition_season_id,
        week=week,
        creating_generation_id=generation_id,
        change_reason=item.change_reason,
        recorded_at=recorded_at,
        context_note_identity=item.context_note_identity,
    )


def _canonical_content(content: MemoryContent) -> bytes:
    return _canonical_json_bytes(content.model_dump(mode="json"))


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _integrity_constraint(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


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
    for kind, ids in ids_by_kind.items():
        model = typed_content_model(kind)
        typed_rows.update(
            {
                row.version_id: row
                for row in session.scalars(
                    sa.select(model).where(model.version_id.in_(ids))
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
        content = decode_stored_content(
            kind,
            envelope.content_schema_version,
            typed_row,
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
    return sa.or_(
        *(
            sa.exists(
                sa.select(1).where(
                    table.version_id == MemoryVersion.id,
                    table.status == status,
                )
            )
            for table in typed_content_models()
        )
    )


def _candidate_from_document(
    document: MemorySearchDocument | SearchDocument,
    lexical_match: bool,
    query_entity_keys: Sequence[str],
    query_evidence_version_ids: Sequence[UUID],
    query_related_item_ids: Sequence[UUID],
    recorded_at: datetime,
) -> MemoryCandidate:
    matched_entities = tuple(
        sorted(set(query_entity_keys) & set(document.entity_keys))
    )
    matched_evidence = tuple(
        sorted(
            set(query_evidence_version_ids) & set(document.evidence_version_ids),
            key=str,
        )
    )
    matched_related = tuple(
        sorted(
            set(query_related_item_ids) & set(document.related_item_ids),
            key=str,
        )
    )
    return MemoryCandidate(
        version_id=document.version_id,
        lexical_match=lexical_match,
        matched_entities=matched_entities,
        matched_evidence_version_ids=matched_evidence,
        matched_related_item_ids=matched_related,
        salience=document.salience,
        recorded_at=recorded_at,
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
