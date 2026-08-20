"""Competition-scoped Sleeper league-season reads."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa

from backend.database.models.core import Competition, CompetitionSeason
from backend.database.models.sleeper import League as StoredLeague
from backend.database.models.sleeper import Roster as StoredRoster
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.common.codec import parse_jsonb_text
from backend.resources.sleeper_data.league_seasons.objects import (
    LeagueSeasonOverview,
    RefreshSeasonIdentity,
    SnapshotPlanningContext,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound


class LeagueSeasonManager:
    """Read latest league metadata for one competition's seasons."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def get_refresh_identity(
        self, competition_season_id: UUID
    ) -> RefreshSeasonIdentity:
        """Read bootstrap identity without requiring normalized Sleeper rows."""

        with read_only_session(self._session_factory) as session:
            season = session.scalar(
                sa.select(CompetitionSeason).where(
                    CompetitionSeason.id == competition_season_id,
                    CompetitionSeason.competition_id == self._competition_id,
                )
            )
            if season is None:
                raise DatalayerResourceNotFound(
                    "competition_season", str(competition_season_id)
                )
            return RefreshSeasonIdentity(
                competition_id=self._competition_id,
                competition_season_id=season.id,
                sleeper_league_id=season.sleeper_league_id,
                season_year=season.season_year,
            )

    def get_snapshot_planning_context(
        self, competition_season_id: UUID
    ) -> SnapshotPlanningContext:
        with read_only_session(self._session_factory) as session:
            season = session.scalar(
                sa.select(CompetitionSeason).where(
                    CompetitionSeason.id == competition_season_id,
                    CompetitionSeason.competition_id == self._competition_id,
                )
            )
            if season is None:
                raise DatalayerResourceNotFound(
                    "competition_season", str(competition_season_id)
                )
            league = session.get(StoredLeague, season.id)
            if league is None:
                raise DatalayerResourceNotFound(
                    "league_season_overview", str(season.id)
                )
            raw_rounds = league.provider_settings.get("draft_rounds")
            draft_rounds = (
                raw_rounds
                if isinstance(raw_rounds, int)
                and not isinstance(raw_rounds, bool)
                and raw_rounds >= 0
                else 0
            )
            return SnapshotPlanningContext(
                competition_id=self._competition_id,
                competition_season_id=season.id,
                sleeper_league_id=season.sleeper_league_id,
                season_year=season.season_year,
                playoff_start_week=league.playoff_start_week,
                playoff_team_count=league.playoff_team_count,
                draft_rounds=draft_rounds,
                league_average_match=league.league_average_match,
            )

    def get_season_overview(self, season_id: UUID) -> LeagueSeasonOverview:
        with read_only_session(self._session_factory) as session:
            row = session.execute(
                sa.select(
                    Competition,
                    CompetitionSeason,
                    StoredLeague,
                    sa.cast(StoredLeague.scoring_settings, sa.Text).label(
                        "scoring_text"
                    ),
                    sa.cast(StoredLeague.roster_positions, sa.Text).label(
                        "positions_text"
                    ),
                    sa.cast(StoredLeague.provider_settings, sa.Text).label(
                        "provider_text"
                    ),
                    sa.func.count(StoredRoster.season_roster_id),
                )
                .join(
                    CompetitionSeason,
                    CompetitionSeason.competition_id == Competition.id,
                )
                .join(
                    StoredLeague,
                    StoredLeague.competition_season_id == CompetitionSeason.id,
                )
                .outerjoin(
                    StoredRoster,
                    StoredRoster.competition_season_id == CompetitionSeason.id,
                )
                .where(
                    Competition.id == self._competition_id,
                    CompetitionSeason.id == season_id,
                )
                .group_by(
                    Competition.id,
                    CompetitionSeason.id,
                    StoredLeague.competition_season_id,
                )
            ).one_or_none()
            if row is None:
                raise DatalayerResourceNotFound(
                    "league_season_overview", str(season_id)
                )
            competition, season, league, scoring, positions, provider, roster_count = (
                row
            )
            parsed_positions = parse_jsonb_text(positions)
            if not isinstance(parsed_positions, list):
                raise ValueError("stored roster positions are not a list")
            return LeagueSeasonOverview(
                competition_id=competition.id,
                competition_season_id=season.id,
                competition_name=competition.display_name,
                sleeper_league_id=season.sleeper_league_id,
                season_year=season.season_year,
                sequence_number=season.sequence_number,
                league_name=league.name,
                status=league.status,
                scoring_settings=cast(dict[str, Any], parse_jsonb_text(scoring)),
                roster_positions=tuple(cast(list[str], parsed_positions)),
                provider_settings=cast(dict[str, Any], parse_jsonb_text(provider)),
                playoff_start_week=league.playoff_start_week,
                playoff_team_count=league.playoff_team_count,
                league_average_match=league.league_average_match,
                roster_count=roster_count,
                source_api_request_id=league.source_api_request_id,
            )
