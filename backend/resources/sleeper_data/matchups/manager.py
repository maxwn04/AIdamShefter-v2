"""Competition-scoped current matchup reads."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa

from backend.database.models.core import CompetitionSeason, Franchise, SeasonRoster
from backend.database.models.sleeper import Matchup as StoredMatchup
from backend.database.models.sleeper import Player as StoredPlayer
from backend.database.models.sleeper import (
    PlayerPerformance as StoredPlayerPerformance,
)
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.matchups.objects import Matchup, PlayerPerformance
from backend.services.datalayer.errors import (
    DatalayerResourceNotFound,
    InvalidDatalayerRequest,
)


class MatchupManager:
    """Read latest matchup observations within one competition."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def list_matchups(self, season_id: UUID, week: int) -> tuple[Matchup, ...]:
        if not 1 <= week <= 18:
            raise InvalidDatalayerRequest("week must be between 1 and 18")
        with read_only_session(self._session_factory) as session:
            season_exists = session.scalar(
                sa.select(sa.literal(True)).where(
                    sa.exists().where(
                        CompetitionSeason.id == season_id,
                        CompetitionSeason.competition_id == self._competition_id,
                    )
                )
            )
            if not season_exists:
                raise DatalayerResourceNotFound("competition_season", str(season_id))
            matchup_rows = session.execute(
                sa.select(StoredMatchup, SeasonRoster, Franchise)
                .join(SeasonRoster, SeasonRoster.id == StoredMatchup.season_roster_id)
                .join(Franchise, Franchise.id == SeasonRoster.franchise_id)
                .where(
                    StoredMatchup.competition_season_id == season_id,
                    StoredMatchup.week == week,
                )
                .order_by(
                    StoredMatchup.sleeper_matchup_id, SeasonRoster.sleeper_roster_id
                )
            ).all()
            performance_rows = session.execute(
                sa.select(StoredPlayerPerformance, StoredPlayer)
                .join(
                    StoredPlayer,
                    StoredPlayer.sleeper_player_id
                    == StoredPlayerPerformance.sleeper_player_id,
                )
                .where(
                    StoredPlayerPerformance.competition_season_id == season_id,
                    StoredPlayerPerformance.week == week,
                )
                .order_by(
                    StoredPlayerPerformance.season_roster_id,
                    StoredPlayerPerformance.sleeper_player_id,
                )
            ).all()
            by_roster: dict[UUID, list[PlayerPerformance]] = defaultdict(list)
            for performance, player in performance_rows:
                by_roster[performance.season_roster_id].append(
                    PlayerPerformance(
                        sleeper_player_id=performance.sleeper_player_id,
                        full_name=player.full_name,
                        points=performance.points,
                        role=cast(Any, performance.role),
                    )
                )
            return tuple(
                Matchup(
                    season_roster_id=identity.id,
                    sleeper_roster_id=identity.sleeper_roster_id,
                    franchise_id=identity.franchise_id,
                    franchise_name=franchise.display_name,
                    week=stored.week,
                    sleeper_matchup_id=stored.sleeper_matchup_id,
                    points=stored.points,
                    player_performances=tuple(by_roster[identity.id]),
                    source_api_request_id=stored.source_api_request_id,
                )
                for stored, identity, franchise in matchup_rows
            )
