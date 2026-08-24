"""Competition-scoped persistence for franchise and roster mappings."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.core import (
    Competition,
    CompetitionSeason,
    Franchise,
    SeasonRoster,
)
from backend.database.sessions import SessionFactory, read_only_session, transaction_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.core.errors import (
    CompetitionArchivedConflict,
    CoreResourceNotFound,
    RosterMappingConflict,
)
from backend.resources.core.roster_mappings.objects import (
    ApplyRosterMappings,
    CreateFranchiseTarget,
    FranchiseIdentity,
    RosterIdentityCatalog,
    SeasonRosterIdentity,
)


class RosterMappingManager:
    """Own immutable season-roster mappings and durable franchise creation."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def get_catalog(self, competition_season_id: UUID) -> RosterIdentityCatalog:
        with read_only_session(self._session_factory) as session:
            competition, season = self._load_scope(session, competition_season_id)
            return self._catalog(session, competition, season)

    def apply(self, command: ApplyRosterMappings) -> RosterIdentityCatalog:
        with transaction_session(self._session_factory) as session:
            competition, season = self._load_scope(
                session,
                command.competition_season_id,
                lock=True,
            )
            if competition.archived_at is not None:
                raise CompetitionArchivedConflict(competition.id)
            if not command.assignments:
                raise RosterMappingConflict(
                    "roster mapping assignments must not be empty"
                )
            sleeper_ids = [item.sleeper_roster_id for item in command.assignments]
            if len(set(sleeper_ids)) != len(sleeper_ids):
                raise RosterMappingConflict(
                    "each Sleeper roster must appear exactly once"
                )

            existing_rows = {
                row.sleeper_roster_id: row
                for row in session.scalars(
                    sa.select(SeasonRoster).where(
                        SeasonRoster.competition_season_id == season.id,
                        SeasonRoster.competition_id == self._competition_id,
                    )
                )
            }
            requested_existing_ids = [
                item.target.franchise_id
                for item in command.assignments
                if item.target.kind == "existing"
            ]
            if len(set(requested_existing_ids)) != len(requested_existing_ids):
                raise RosterMappingConflict(
                    "a franchise can be mapped only once in a season"
                )
            franchises = {
                row.id: row
                for row in session.scalars(
                    sa.select(Franchise).where(
                        Franchise.competition_id == self._competition_id,
                        Franchise.id.in_(requested_existing_ids),
                    )
                )
            }
            for franchise_id in requested_existing_ids:
                franchise = franchises.get(franchise_id)
                if franchise is None:
                    raise RosterMappingConflict(
                        "a selected franchise does not belong to this competition"
                    )
                if franchise.archived_at is not None:
                    raise RosterMappingConflict(
                        "archived franchises cannot receive new season mappings"
                    )

            for assignment in command.assignments:
                current = existing_rows.get(assignment.sleeper_roster_id)
                if current is not None:
                    target = assignment.target
                    same_existing = (
                        target.kind == "existing"
                        and current.franchise_id == target.franchise_id
                    )
                    current_franchise = session.get(Franchise, current.franchise_id)
                    same_new = (
                        isinstance(target, CreateFranchiseTarget)
                        and current_franchise is not None
                        and current_franchise.display_name == target.display_name
                    )
                    if not same_existing and not same_new:
                        raise RosterMappingConflict(
                            "existing season-roster mappings cannot be changed"
                        )
                    continue
                target = assignment.target
                if isinstance(target, CreateFranchiseTarget):
                    franchise = Franchise(
                        id=uuid4(),
                        competition_id=self._competition_id,
                        display_name=target.display_name,
                    )
                    session.add(franchise)
                    session.flush()
                    franchise_id = franchise.id
                else:
                    franchise_id = target.franchise_id
                session.add(
                    SeasonRoster(
                        id=uuid4(),
                        competition_id=self._competition_id,
                        competition_season_id=season.id,
                        franchise_id=franchise_id,
                        sleeper_roster_id=assignment.sleeper_roster_id,
                    )
                )
            session.flush()
            return self._catalog(session, competition, season)

    def bootstrap_first_season(
        self,
        competition_season_id: UUID,
        assignments: Sequence[RosterMappingAssignment],
    ) -> RosterIdentityCatalog:
        catalog = self.get_catalog(competition_season_id)
        if catalog.sequence_number != 1 or catalog.mappings:
            return catalog
        return self.apply(
            ApplyRosterMappings(
                competition_season_id=competition_season_id,
                assignments=tuple(assignments),
            )
        )

    def _load_scope(
        self,
        session: Session,
        competition_season_id: UUID,
        *,
        lock: bool = False,
    ) -> tuple[Competition, CompetitionSeason]:
        statement = (
            sa.select(Competition, CompetitionSeason)
            .join(
                CompetitionSeason,
                CompetitionSeason.competition_id == Competition.id,
            )
            .where(
                Competition.id == self._competition_id,
                CompetitionSeason.id == competition_season_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=(Competition, CompetitionSeason))
        row = session.execute(statement).one_or_none()
        if row is None:
            raise CoreResourceNotFound("competition_season", competition_season_id)
        return row[0], row[1]

    def _catalog(
        self,
        session: Session,
        competition: Competition,
        season: CompetitionSeason,
    ) -> RosterIdentityCatalog:
        franchises = session.scalars(
            sa.select(Franchise)
            .where(Franchise.competition_id == self._competition_id)
            .order_by(Franchise.display_name, Franchise.id)
        ).all()
        mappings = session.scalars(
            sa.select(SeasonRoster)
            .where(
                SeasonRoster.competition_id == self._competition_id,
                SeasonRoster.competition_season_id == season.id,
            )
            .order_by(SeasonRoster.sleeper_roster_id, SeasonRoster.id)
        ).all()
        return RosterIdentityCatalog(
            competition_id=self._competition_id,
            competition_season_id=season.id,
            sequence_number=season.sequence_number,
            competition_archived=competition.archived_at is not None,
            franchises=tuple(
                FranchiseIdentity(
                    id=row.id,
                    competition_id=row.competition_id,
                    display_name=row.display_name,
                    archived_at=row.archived_at,
                )
                for row in franchises
            ),
            mappings=tuple(
                SeasonRosterIdentity(
                    id=row.id,
                    competition_season_id=row.competition_season_id,
                    franchise_id=row.franchise_id,
                    sleeper_roster_id=row.sleeper_roster_id,
                )
                for row in mappings
            ),
        )


__all__ = ["RosterMappingManager"]
