from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.memory import (
    CurrentRevision,
    MemoryItem,
    MemoryRevision,
    MemoryVersion,
)
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common.errors import (
    CanonicalStateHashMismatchError,
    RevisionNotFoundError,
)
from backend.resources.memory.revisions.hashing import (
    StateHashItem,
    compute_state_content_hash,
    state_hash_item,
)
from backend.resources.memory.revisions.objects import CanonicalRevision
from backend.resources.memory.revisions.writers import (
    CanonicalResourceWrite,
    CanonicalWriteBundle,
    StateReader,
    advance_current_revision,
    build_version_envelopes,
    lock_current_revision,
    persist_version_envelopes,
    validate_reference_targets,
)


class RevisionManager:
    """Competition-scoped reads over the linear canonical revision history."""

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

    def current(self) -> CanonicalRevision:
        """Return the competition's current canonical revision."""

        statement = (
            sa.select(MemoryRevision)
            .join(
                CurrentRevision,
                sa.and_(
                    CurrentRevision.current_revision_id == MemoryRevision.id,
                    CurrentRevision.competition_id == MemoryRevision.competition_id,
                ),
            )
            .where(CurrentRevision.competition_id == self._competition_id)
        )
        with read_only_session(self._session_factory) as session:
            row = session.scalar(statement)
        if row is None:
            raise RevisionNotFoundError(self._competition_id)
        return _to_revision(row)

    def pin(self, revision_id: UUID) -> CanonicalRevision:
        """Resolve one exact revision without leaking cross-competition state."""

        statement = sa.select(MemoryRevision).where(
            MemoryRevision.id == revision_id,
            MemoryRevision.competition_id == self._competition_id,
        )
        with read_only_session(self._session_factory) as session:
            row = session.scalar(statement)
        if row is None:
            raise RevisionNotFoundError(self._competition_id, revision_id)
        return _to_revision(row)

    def history(self) -> tuple[CanonicalRevision, ...]:
        """Return the complete revision history, newest state first."""

        statement = (
            sa.select(MemoryRevision)
            .where(MemoryRevision.competition_id == self._competition_id)
            .order_by(MemoryRevision.sequence_number.desc())
        )
        with read_only_session(self._session_factory) as session:
            rows = session.scalars(statement).all()
        return tuple(_to_revision(row) for row in rows)

    def commit(
        self,
        bundle: CanonicalWriteBundle,
    ) -> CanonicalRevision | None:
        """Commit one complete typed bundle as a single canonical transition."""

        if bundle.competition_id != self._competition_id:
            raise ValueError("mutation bundle is outside the manager competition")
        if not bundle.writes:
            return None

        state_readers = _state_readers()
        with transaction_session(self._session_factory) as session:
            parent = lock_current_revision(
                session,
                self._competition_id,
                bundle.expected_revision_id,
            )
            parent_state = _read_state(
                session,
                self._competition_id,
                state_readers,
            )
            validate_reference_targets(session, self._competition_id, bundle.writes)
            revision = MemoryRevision(
                id=uuid4(),
                competition_id=self._competition_id,
                sequence_number=parent.next_sequence_number,
                previous_revision_id=parent.current_revision_id,
                producing_generation_id=bundle.generation_id,
                competition_season_id=bundle.competition_season_id,
                week=bundle.week,
                knowledge_cutoff_at=bundle.knowledge_cutoff_at,
                state_content_hash="pending",
            )
            resolved, retired = build_version_envelopes(session, revision, bundle)
            expected_hash = compute_state_content_hash(
                self._competition_id,
                _resulting_state(parent_state, resolved),
            )
            revision.state_content_hash = expected_hash
            persist_version_envelopes(
                session,
                revision,
                new_items=(
                    item
                    for write, item, _ in resolved
                    if write.operation == "create"
                ),
                new_versions=(version for _, _, version in resolved),
                retired_versions=retired,
            )
            for write, item, version in sorted(
                resolved,
                key=lambda entry: entry[0].dependency_order,
            ):
                write.persist_typed(session, item, version)
                session.flush()

            actual_hash = compute_state_content_hash(
                self._competition_id,
                _read_state(session, self._competition_id, state_readers),
            )
            if actual_hash != expected_hash:
                raise CanonicalStateHashMismatchError(expected_hash, actual_hash)
            advance_current_revision(
                session,
                self._competition_id,
                parent,
                revision.id,
            )
            session.flush()

        return _to_revision(revision)


def _to_revision(row: MemoryRevision) -> CanonicalRevision:
    return CanonicalRevision(
        revision_id=row.id,
        competition_id=row.competition_id,
        sequence_number=row.sequence_number,
        previous_revision_id=row.previous_revision_id,
        producing_generation_id=row.producing_generation_id,
        competition_season_id=row.competition_season_id,
        week=row.week,
        knowledge_cutoff_at=row.knowledge_cutoff_at,
        state_content_hash=row.state_content_hash,
        created_at=row.created_at,
    )


def _read_state(
    session: Session,
    competition_id: UUID,
    state_readers: tuple[StateReader, ...],
) -> tuple[StateHashItem, ...]:
    return tuple(
        item
        for reader in state_readers
        for item in reader(session, competition_id)
    )


def _state_readers() -> tuple[StateReader, ...]:
    # Lazy imports avoid the codecs -> revision hashing package initialization
    # cycle while keeping the complete state-reader registry revision-owned.
    from backend.resources.memory.context_notes.shared import read_context_note_state
    from backend.resources.memory.events.shared import read_event_state
    from backend.resources.memory.facts.shared import read_fact_state
    from backend.resources.memory.storylines.shared import read_storyline_state
    from backend.resources.memory.triggers.shared import read_trigger_state

    return (
        read_fact_state,
        read_event_state,
        read_storyline_state,
        read_trigger_state,
        read_context_note_state,
    )


def _resulting_state(
    parent_state: tuple[StateHashItem, ...],
    resolved: tuple[
        tuple[CanonicalResourceWrite, MemoryItem, MemoryVersion], ...
    ],
) -> tuple[StateHashItem, ...]:
    writes_by_item = {entry[0].item_id for entry in resolved}
    previous_by_item = {item.item_id: item for item in parent_state}
    result = [item for item in parent_state if item.item_id not in writes_by_item]
    for write, item, version in resolved:
        previous = previous_by_item.get(write.item_id)
        note_identity = write.context_note_identity
        if note_identity is None and previous is not None:
            note_identity = previous.context_note_identity
        result.append(
            state_hash_item(
                item_id=item.id,
                kind=write.kind,
                agent_key=item.agent_key,
                version_id=version.id,
                revision_number=version.revision_number,
                content_schema_version=version.content_schema_version,
                competition_season_id=version.competition_season_id,
                week=version.week,
                occurred_at=version.occurred_at,
                content=write.stored_content,
                context_note_identity=note_identity,
            )
        )
    return tuple(result)
