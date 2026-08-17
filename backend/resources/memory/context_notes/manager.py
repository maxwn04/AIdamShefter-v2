from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa

from backend.database.models.memory import MemoryItem, MemoryVersion
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common.errors import TargetNotFoundError
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.codec import (
    context_note_rows_statement,
    decode_context_note,
)
from backend.resources.memory.context_notes.objects import ContextNote


class ContextNoteManager:
    """Competition-scoped hydration of context-note aggregates."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def exact(self, version_id: UUID) -> ContextNote:
        """Hydrate one exact note version with its stable scope/key identity."""

        statement = context_note_rows_statement().where(
            MemoryVersion.id == version_id,
            MemoryVersion.competition_id == self._competition_id,
        )
        with read_only_session(self._session_factory) as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            raise TargetNotFoundError(version_id, (MemoryKind.CONTEXT_NOTE,))
        return decode_context_note(row[0], row[1], row[2], row[3])

    def history(self, item_id: UUID) -> tuple[ContextNote, ...]:
        """Return every version of one stable note identity, newest first."""

        statement = (
            context_note_rows_statement()
            .where(
                MemoryItem.id == item_id,
                MemoryItem.competition_id == self._competition_id,
            )
            .order_by(sa.desc(MemoryVersion.revision_number))
        )
        with read_only_session(self._session_factory) as session:
            rows = session.execute(statement).all()
        if not rows:
            raise TargetNotFoundError(item_id, (MemoryKind.CONTEXT_NOTE,))
        return tuple(
            decode_context_note(row[0], row[1], row[2], row[3]) for row in rows
        )
