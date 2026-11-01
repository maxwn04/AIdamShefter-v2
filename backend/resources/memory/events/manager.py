from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa

from backend.database.models.memory import EventVersion, MemoryItem, MemoryVersion
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common.errors import TargetNotFoundError
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.events.codec import decode_event, event_rows_statement
from backend.resources.memory.events.objects import Event
from backend.resources.memory.events.source_identity import SleeperTradeIdentity
from backend.resources.memory.revisions.shared import visible_versions_statement
from backend.resources.memory.search_documents.objects import SearchDocumentQuery
from backend.resources.memory.search_documents.query import temporal_conditions


class EventManager:
    """Competition-scoped hydration of immutable event versions."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def trade_at_source(
        self, identity: SleeperTradeIdentity, revision_id: UUID, *, through_week: int,
    ) -> tuple[Event, ...]:
        """Exact write lookup at the input pin; never a relevance search or merge."""
        visible = visible_versions_statement(self._competition_id, revision_id).subquery()
        scope = SearchDocumentQuery(
            through_competition_season_id=identity.competition_season_id,
            through_week=through_week,
        )
        eligible = sa.and_(*temporal_conditions(
            self._competition_id, scope,
            introduced_revision_id=MemoryVersion.introduced_revision_id,
            season_id=MemoryVersion.competition_season_id,
            week=MemoryVersion.week,
            recorded_at=MemoryVersion.recorded_at,
        ))
        # Keep pin-visible matches outside the reporting window in this internal
        # identity check. Filtering them out would incorrectly authorize create.
        statement = (
            event_rows_statement()
            .add_columns(eligible.label("within_reporting_scope"))
            .join(visible, visible.c.id == MemoryVersion.id)
            .where(
                MemoryVersion.competition_id == self._competition_id,
                MemoryVersion.competition_season_id == identity.competition_season_id,
                EventVersion.event_type == "trade",
                EventVersion.additional_source_hints["transaction_id"].astext == identity.transaction_id,
            )
        )
        with read_only_session(self._session_factory) as session:
            rows = session.execute(statement).all()
        matches: list[Event] = []
        for item, version, stored, within_scope in rows:
            hints = stored.additional_source_hints
            if hints.get("provider", "sleeper") != "sleeper":
                continue
            # Missing/conflicting legacy identity fails closed; do not create a
            # fresh identity merely because an old receipt cannot be interpreted.
            source = SleeperTradeIdentity.from_hints(hints, version.competition_season_id)
            if source != identity:
                continue
            if not within_scope:
                raise ValueError(
                    "A matching source transaction is outside this generation's reporting boundary; "
                    "no event was selected or created."
                )
            matches.append(decode_event(item, version, stored))
        return tuple(matches)

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

    def visible_at(self, item_id: UUID, revision_id: UUID) -> Event:
        """Hydrate the version of one stable event visible at a revision."""

        visible = visible_versions_statement(
            self._competition_id,
            revision_id,
        ).subquery("visible_event_versions")
        statement = event_rows_statement().join(
            visible,
            visible.c.id == MemoryVersion.id,
        ).where(
            MemoryItem.id == item_id,
            MemoryItem.competition_id == self._competition_id,
        )
        with read_only_session(self._session_factory) as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            raise TargetNotFoundError(item_id, (MemoryKind.EVENT,))
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
