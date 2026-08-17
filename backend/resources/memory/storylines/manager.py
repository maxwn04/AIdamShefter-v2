from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa

from backend.database.models.memory import MemoryItem, MemoryVersion
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common.errors import TargetNotFoundError
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.storylines.codec import (
    decode_storyline,
    storyline_rows_statement,
)
from backend.resources.memory.storylines.objects import Storyline


class StorylineManager:
    """Competition-scoped hydration of immutable storyline versions."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def exact(self, version_id: UUID) -> Storyline:
        """Hydrate one exact storyline version, including retired history."""

        statement = storyline_rows_statement().where(
            MemoryVersion.id == version_id,
            MemoryVersion.competition_id == self._competition_id,
        )
        with read_only_session(self._session_factory) as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            raise TargetNotFoundError(version_id, (MemoryKind.STORYLINE,))
        return decode_storyline(row[0], row[1], row[2])

    def history(self, item_id: UUID) -> tuple[Storyline, ...]:
        """Return every immutable version of one storyline item, newest first."""

        statement = (
            storyline_rows_statement()
            .where(
                MemoryItem.id == item_id,
                MemoryItem.competition_id == self._competition_id,
            )
            .order_by(sa.desc(MemoryVersion.revision_number))
        )
        with read_only_session(self._session_factory) as session:
            rows = session.execute(statement).all()
        if not rows:
            raise TargetNotFoundError(item_id, (MemoryKind.STORYLINE,))
        return tuple(decode_storyline(row[0], row[1], row[2]) for row in rows)
