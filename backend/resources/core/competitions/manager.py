"""Global lifecycle manager for durable competition identities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models.core import Competition as StoredCompetition
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import GlobalScope, ManagerContext
from backend.resources.core.competitions.objects import (
    ArchiveCompetition,
    Competition,
    CompetitionPage,
    CompetitionQuery,
    CreateCompetition,
    RenameCompetition,
)
from backend.resources.core.errors import (
    CompetitionArchivedConflict,
    CompetitionConcurrencyConflict,
    CoreResourceNotFound,
)


class CompetitionManager:
    """Own competition creation, active listing, renaming, and archival."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[GlobalScope],
    ) -> None:
        self._session_factory = session_factory
        self._context = context

    def create(self, command: CreateCompetition) -> Competition:
        try:
            with transaction_session(self._session_factory) as session:
                stored = StoredCompetition(
                    id=uuid4(),
                    display_name=command.display_name,
                )
                session.add(stored)
                session.flush()
                return _decode(stored)
        except IntegrityError as error:
            raise CompetitionConcurrencyConflict(
                "competition identity is already allocated",
                constraint_name=_constraint_name(error),
            ) from None

    def get(self, competition_id: UUID) -> Competition:
        with read_only_session(self._session_factory) as session:
            return _decode(_load(session, competition_id))

    def list(self, query: CompetitionQuery) -> CompetitionPage:
        with read_only_session(self._session_factory) as session:
            conditions: list[sa.ColumnElement[bool]] = []
            if not query.include_archived:
                conditions.append(StoredCompetition.archived_at.is_(None))
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredCompetition)
                    .where(*conditions)
                ),
            )
            rows = session.scalars(
                sa.select(StoredCompetition)
                .where(*conditions)
                .order_by(
                    sa.func.lower(StoredCompetition.display_name).asc(),
                    StoredCompetition.id.asc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return CompetitionPage(
                items=tuple(_decode(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def rename(self, command: RenameCompetition) -> Competition:
        with transaction_session(self._session_factory) as session:
            stored = _load(session, command.competition_id, lock=True)
            _require_active(stored)
            if stored.display_name == command.display_name:
                return _decode(stored)
            stored.display_name = command.display_name
            stored.updated_at = datetime.now(UTC)
            session.flush()
            return _decode(stored)

    def archive(self, command: ArchiveCompetition) -> Competition:
        with transaction_session(self._session_factory) as session:
            stored = _load(session, command.competition_id, lock=True)
            if stored.archived_at is not None:
                return _decode(stored)
            archived_at = datetime.now(UTC)
            stored.archived_at = archived_at
            stored.updated_at = archived_at
            session.flush()
            return _decode(stored)


def _load(
    session: Session,
    competition_id: UUID,
    *,
    lock: bool = False,
) -> StoredCompetition:
    statement = sa.select(StoredCompetition).where(
        StoredCompetition.id == competition_id
    )
    if lock:
        statement = statement.with_for_update()
    stored = session.scalar(statement)
    if stored is None:
        raise CoreResourceNotFound("competition", competition_id)
    return stored


def _require_active(stored: StoredCompetition) -> None:
    if stored.archived_at is not None:
        raise CompetitionArchivedConflict(stored.id)


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return cast(str | None, getattr(diagnostic, "constraint_name", None))


def _decode(stored: StoredCompetition) -> Competition:
    return Competition(
        id=stored.id,
        display_name=stored.display_name,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
        archived_at=stored.archived_at,
    )


__all__ = ["CompetitionManager"]
