from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa

from backend.database.models.memory import CurrentRevision, MemoryRevision
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common.errors import RevisionNotFoundError
from backend.resources.memory.revisions.objects import CanonicalRevision


class RevisionManager:
    """Competition-scoped reads over the linear canonical revision history."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory: SessionFactory = session_factory
        self._competition_id: UUID = context.scope.competition_id

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
