"""Competition-scoped manager for durable season identities."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models.core import Competition as StoredCompetition
from backend.database.models.core import CompetitionSeason as StoredCompetitionSeason
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.core.competition_seasons.objects import (
    CompetitionSeason,
    CompetitionSeasonPage,
    CompetitionSeasonQuery,
    CreateCompetitionSeason,
)
from backend.resources.core.errors import (
    CompetitionArchivedConflict,
    CompetitionConcurrencyConflict,
    CompetitionSeasonYearExists,
    CoreResourceNotFound,
    SleeperLeagueIdExists,
)


_SEASON_YEAR_CONSTRAINT = "uq_competition_seasons_competition_id_season_year"
_SEQUENCE_CONSTRAINT = "uq_competition_seasons_competition_id_sequence_number"
_SLEEPER_LEAGUE_ID_CONSTRAINT = "uq_competition_seasons_sleeper_league_id"


class CompetitionSeasonManager:
    """Own immutable season attachment and competition-scoped reads."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    @property
    def competition_id(self) -> UUID:
        return self._competition_id

    def create(self, command: CreateCompetitionSeason) -> CompetitionSeason:
        try:
            with transaction_session(self._session_factory) as session:
                competition = _load_competition(
                    session,
                    self._competition_id,
                    lock=True,
                )
                if competition.archived_at is not None:
                    raise CompetitionArchivedConflict(competition.id)
                current_sequence = session.scalar(
                    sa.select(
                        sa.func.coalesce(
                            sa.func.max(StoredCompetitionSeason.sequence_number),
                            0,
                        )
                    ).where(
                        StoredCompetitionSeason.competition_id
                        == self._competition_id
                    )
                )
                stored = StoredCompetitionSeason(
                    id=uuid4(),
                    competition_id=self._competition_id,
                    season_year=command.season_year,
                    sequence_number=cast(int, current_sequence) + 1,
                    sleeper_league_id=command.sleeper_league_id,
                )
                session.add(stored)
                session.flush()
                return _decode(stored)
        except IntegrityError as error:
            constraint_name = _constraint_name(error)
            if constraint_name == _SEASON_YEAR_CONSTRAINT:
                raise CompetitionSeasonYearExists(
                    self._competition_id,
                    command.season_year,
                ) from None
            if constraint_name == _SLEEPER_LEAGUE_ID_CONSTRAINT:
                raise SleeperLeagueIdExists(command.sleeper_league_id) from None
            message = (
                "competition season sequence allocation conflicted"
                if constraint_name == _SEQUENCE_CONSTRAINT
                else "competition season identity is already allocated"
            )
            raise CompetitionConcurrencyConflict(
                message,
                constraint_name=constraint_name,
            ) from None

    def get(self, competition_season_id: UUID) -> CompetitionSeason:
        with read_only_session(self._session_factory) as session:
            stored = session.scalar(
                sa.select(StoredCompetitionSeason).where(
                    StoredCompetitionSeason.id == competition_season_id,
                    StoredCompetitionSeason.competition_id == self._competition_id,
                )
            )
            if stored is None:
                raise CoreResourceNotFound(
                    "competition_season",
                    competition_season_id,
                )
            return _decode(stored)

    def list(self, query: CompetitionSeasonQuery) -> CompetitionSeasonPage:
        with read_only_session(self._session_factory) as session:
            _load_competition(session, self._competition_id)
            condition = (
                StoredCompetitionSeason.competition_id == self._competition_id
            )
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredCompetitionSeason)
                    .where(condition)
                ),
            )
            rows = session.scalars(
                sa.select(StoredCompetitionSeason)
                .where(condition)
                .order_by(
                    StoredCompetitionSeason.sequence_number.desc(),
                    StoredCompetitionSeason.id.asc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return CompetitionSeasonPage(
                items=tuple(_decode(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )


def _load_competition(
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


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return cast(str | None, getattr(diagnostic, "constraint_name", None))


def _decode(stored: StoredCompetitionSeason) -> CompetitionSeason:
    return CompetitionSeason(
        id=stored.id,
        competition_id=stored.competition_id,
        season_year=stored.season_year,
        sequence_number=stored.sequence_number,
        sleeper_league_id=stored.sleeper_league_id,
        created_at=stored.created_at,
    )


__all__ = ["CompetitionSeasonManager"]
