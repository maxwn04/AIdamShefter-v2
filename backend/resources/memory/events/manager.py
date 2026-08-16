from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa

from backend.database.models.memory import MemoryItem, MemoryVersion
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common.errors import TargetNotFoundError
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.events.codec import decode_event, event_rows_statement
from backend.resources.memory.events.objects import Event


class EventManager:
    """Competition-scoped hydration of immutable event versions."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def exact(self, version_id: UUID) -> Event:
        """Hydrate one exact event version, including retired history."""

        statement = event_rows_statement().where(
            MemoryVersion.id == version_id,
            MemoryVersion.competition_id == self._competition_id,
        )
        with read_only_session(self._session_factory) as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            raise TargetNotFoundError(version_id, (MemoryKind.EVENT,))
        return decode_event(row[0], row[1], row[2])

    def history(self, item_id: UUID) -> tuple[Event, ...]:
        """Return every immutable version of one event item, newest first."""

        statement = (
            event_rows_statement()
            .where(
                MemoryItem.id == item_id,
                MemoryItem.competition_id == self._competition_id,
            )
            .order_by(sa.desc(MemoryVersion.revision_number))
        )
        with read_only_session(self._session_factory) as session:
            rows = session.execute(statement).all()
        if not rows:
            raise TargetNotFoundError(item_id, (MemoryKind.EVENT,))
        return tuple(decode_event(row[0], row[1], row[2]) for row in rows)
