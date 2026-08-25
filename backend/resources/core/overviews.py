"""Set-based product projections for competition and season screens."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

import sqlalchemy as sa
from pydantic import AwareDatetime, Field
from sqlalchemy.orm import Session

from backend.database.models.core import Competition as StoredCompetition
from backend.database.models.core import CompetitionSeason as StoredCompetitionSeason
from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.models.sleeper import DataSnapshot as StoredDataSnapshot
from backend.database.models.sleeper import League as StoredLeague
from backend.database.models.sleeper import RefreshRun as StoredRefreshRun
from backend.database.models.sleeper import Roster as StoredRoster
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources._contracts import ContractModel
from backend.resources.core.competition_seasons.objects import (
    CompetitionSeason,
    CompetitionSeasonQuery,
)
from backend.resources.core.competitions.objects import Competition, CompetitionQuery
from backend.resources.core.errors import CoreResourceNotFound
from backend.resources.sleeper_data import LeagueSeasonOverview
from backend.services.datalayer.contracts import RefreshStatus


NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]


class LatestRefreshSummary(ContractModel):
    status: RefreshStatus
    requested_through_week: int | None
    completed_at: AwareDatetime
    request_count: NonNegativeInt
    succeeded_request_count: NonNegativeInt
    failed_request_count: NonNegativeInt


class CompetitionActivitySummary(ContractModel):
    season_count: NonNegativeInt
    latest_season: CompetitionSeason | None
    latest_terminal_refresh: LatestRefreshSummary | None
    latest_successful_refresh_at: AwareDatetime | None
    latest_ready_snapshot_at: AwareDatetime | None
    latest_submitted_article_at: AwareDatetime | None


class CompetitionOverview(ContractModel):
    competition: Competition
    summary: CompetitionActivitySummary


class CompetitionOverviewPage(ContractModel):
    items: tuple[CompetitionOverview, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


class CompetitionSeasonActivitySummary(ContractModel):
    league_name: str | None
    league_status: str | None
    latest_terminal_refresh: LatestRefreshSummary | None
    latest_successful_refresh_at: AwareDatetime | None
    latest_ready_snapshot_at: AwareDatetime | None


class CompetitionSeasonOverview(ContractModel):
    season: CompetitionSeason
    summary: CompetitionSeasonActivitySummary


class CompetitionSeasonOverviewPage(ContractModel):
    items: tuple[CompetitionSeasonOverview, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


class CompetitionSeasonDetail(CompetitionSeasonOverview):
    normalized_overview: LeagueSeasonOverview | None


class CompetitionOverviewReader:
    """Read product summaries without issuing one query per projected row."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_competitions(
        self,
        query: CompetitionQuery,
    ) -> CompetitionOverviewPage:
        conditions: list[sa.ColumnElement[bool]] = []
        if not query.include_archived:
            conditions.append(StoredCompetition.archived_at.is_(None))
        with read_only_session(self._session_factory) as session:
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredCompetition)
                    .where(*conditions)
                ),
            )
            rows = session.execute(
                _competition_statement()
                .where(*conditions)
                .order_by(
                    sa.func.lower(StoredCompetition.display_name).asc(),
                    StoredCompetition.id.asc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return CompetitionOverviewPage(
                items=tuple(_decode_competition(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def get_competition(self, competition_id: UUID) -> CompetitionOverview:
        with read_only_session(self._session_factory) as session:
            row = session.execute(
                _competition_statement().where(
                    StoredCompetition.id == competition_id
                )
            ).one_or_none()
            if row is None:
                raise CoreResourceNotFound("competition", competition_id)
            return _decode_competition(row)

    def list_seasons(
        self,
        competition_id: UUID,
        query: CompetitionSeasonQuery,
    ) -> CompetitionSeasonOverviewPage:
        with read_only_session(self._session_factory) as session:
            _require_competition(session, competition_id)
            condition = StoredCompetitionSeason.competition_id == competition_id
            total = cast(
                int,
                session.scalar(
                    sa.select(sa.func.count())
                    .select_from(StoredCompetitionSeason)
                    .where(condition)
                ),
            )
            rows = session.execute(
                _season_statement()
                .where(condition)
                .order_by(
                    StoredCompetitionSeason.sequence_number.desc(),
                    StoredCompetitionSeason.id.asc(),
                )
                .limit(query.limit)
                .offset(query.offset)
            ).all()
            return CompetitionSeasonOverviewPage(
                items=tuple(_decode_season(row) for row in rows),
                total=total,
                limit=query.limit,
                offset=query.offset,
            )

    def get_season(
        self,
        competition_id: UUID,
        season_id: UUID,
    ) -> CompetitionSeasonDetail:
        with read_only_session(self._session_factory) as session:
            row = session.execute(
                _season_detail_statement().where(
                    StoredCompetitionSeason.competition_id == competition_id,
                    StoredCompetitionSeason.id == season_id,
                )
            ).one_or_none()
            if row is None:
                raise CoreResourceNotFound("competition_season", season_id)
            projected = _decode_season(row)
            league = row._mapping[StoredLeague]
            normalized = None
            if league is not None:
                normalized = LeagueSeasonOverview(
                    competition_id=competition_id,
                    competition_season_id=projected.season.id,
                    competition_name=row._mapping["competition_name"],
                    sleeper_league_id=projected.season.sleeper_league_id,
                    season_year=projected.season.season_year,
                    sequence_number=projected.season.sequence_number,
                    league_name=league.name,
                    status=league.status,
                    scoring_settings=league.scoring_settings,
                    roster_positions=tuple(league.roster_positions),
                    provider_settings=league.provider_settings,
                    playoff_start_week=league.playoff_start_week,
                    playoff_team_count=league.playoff_team_count,
                    league_average_match=league.league_average_match,
                    roster_count=row._mapping["roster_count"],
                    source_api_request_id=league.source_api_request_id,
                )
            return CompetitionSeasonDetail(
                season=projected.season,
                summary=projected.summary,
                normalized_overview=normalized,
            )


def _competition_statement() -> sa.Select[tuple[StoredCompetition]]:
    season_count = (
        sa.select(sa.func.count())
        .select_from(StoredCompetitionSeason)
        .where(StoredCompetitionSeason.competition_id == StoredCompetition.id)
        .correlate(StoredCompetition)
        .scalar_subquery()
    )
    def latest_season_value(
        column: sa.ColumnElement[object],
    ) -> sa.ScalarSelect[object]:
        return (
            sa.select(column)
            .where(StoredCompetitionSeason.competition_id == StoredCompetition.id)
            .order_by(
                StoredCompetitionSeason.sequence_number.desc(),
                StoredCompetitionSeason.id.desc(),
            )
            .limit(1)
            .correlate(StoredCompetition)
            .scalar_subquery()
        )

    latest_season_id = latest_season_value(StoredCompetitionSeason.id)
    terminal = _latest_refresh_subquery(
        StoredRefreshRun.competition_id == StoredCompetition.id,
        StoredRefreshRun.status != RefreshStatus.RUNNING.value,
    ).correlate(StoredCompetition)
    latest_success = _latest_timestamp(
        StoredRefreshRun.completed_at,
        StoredRefreshRun.id,
        StoredRefreshRun.competition_id == StoredCompetition.id,
        StoredRefreshRun.status == RefreshStatus.SUCCEEDED.value,
    ).correlate(StoredCompetition)
    latest_snapshot = _latest_timestamp(
        StoredDataSnapshot.completed_at,
        StoredDataSnapshot.id,
        StoredDataSnapshot.competition_id == StoredCompetition.id,
        StoredDataSnapshot.status == "ready",
    ).correlate(StoredCompetition)
    latest_article = _latest_timestamp(
        StoredGeneration.completed_at,
        StoredGeneration.id,
        StoredGeneration.competition_id == StoredCompetition.id,
        StoredGeneration.status == "succeeded",
        StoredGeneration.submitted_artifact_version_id.is_not(None),
    ).correlate(StoredCompetition)
    return sa.select(
        StoredCompetition,
        season_count.label("season_count"),
        latest_season_id.label("latest_season_id"),
        latest_season_value(StoredCompetitionSeason.season_year).label(
            "latest_season_year"
        ),
        latest_season_value(StoredCompetitionSeason.sequence_number).label(
            "latest_season_sequence_number"
        ),
        latest_season_value(StoredCompetitionSeason.sleeper_league_id).label(
            "latest_season_sleeper_league_id"
        ),
        latest_season_value(StoredCompetitionSeason.created_at).label(
            "latest_season_created_at"
        ),
        *(_refresh_scalar(terminal, column) for column in _REFRESH_COLUMNS),
        latest_success.scalar_subquery().label("latest_successful_refresh_at"),
        latest_snapshot.scalar_subquery().label("latest_ready_snapshot_at"),
        latest_article.scalar_subquery().label("latest_submitted_article_at"),
    )


def _season_statement() -> sa.Select[tuple[StoredCompetitionSeason]]:
    terminal = _latest_refresh_subquery(
        StoredRefreshRun.competition_season_id == StoredCompetitionSeason.id,
        StoredRefreshRun.status != RefreshStatus.RUNNING.value,
    ).correlate(StoredCompetitionSeason)
    latest_success = _latest_timestamp(
        StoredRefreshRun.completed_at,
        StoredRefreshRun.id,
        StoredRefreshRun.competition_season_id == StoredCompetitionSeason.id,
        StoredRefreshRun.status == RefreshStatus.SUCCEEDED.value,
    ).correlate(StoredCompetitionSeason)
    latest_snapshot = _latest_timestamp(
        StoredDataSnapshot.completed_at,
        StoredDataSnapshot.id,
        StoredDataSnapshot.primary_competition_season_id
        == StoredCompetitionSeason.id,
        StoredDataSnapshot.status == "ready",
    ).correlate(StoredCompetitionSeason)
    return (
        sa.select(
            StoredCompetitionSeason,
            StoredLeague.name.label("league_name"),
            StoredLeague.status.label("league_status"),
            *(_refresh_scalar(terminal, column) for column in _REFRESH_COLUMNS),
            latest_success.scalar_subquery().label("latest_successful_refresh_at"),
            latest_snapshot.scalar_subquery().label("latest_ready_snapshot_at"),
        )
        .outerjoin(
            StoredLeague,
            StoredLeague.competition_season_id == StoredCompetitionSeason.id,
        )
    )


def _season_detail_statement() -> sa.Select[tuple[StoredCompetitionSeason]]:
    roster_count = (
        sa.select(sa.func.count())
        .select_from(StoredRoster)
        .where(StoredRoster.competition_season_id == StoredCompetitionSeason.id)
        .correlate(StoredCompetitionSeason)
        .scalar_subquery()
    )
    return (
        _season_statement()
        .add_columns(
            StoredLeague,
            StoredCompetition.display_name.label("competition_name"),
            roster_count.label("roster_count"),
        )
        .join(
            StoredCompetition,
            StoredCompetition.id == StoredCompetitionSeason.competition_id,
        )
    )


_REFRESH_COLUMNS = (
    "status",
    "requested_through_week",
    "completed_at",
    "request_count",
    "succeeded_request_count",
    "failed_request_count",
)


def _latest_refresh_subquery(
    *conditions: sa.ColumnElement[bool],
) -> sa.Select[tuple[StoredRefreshRun]]:
    return (
        sa.select(StoredRefreshRun)
        .where(*conditions, StoredRefreshRun.completed_at.is_not(None))
        .order_by(StoredRefreshRun.completed_at.desc(), StoredRefreshRun.id.desc())
        .limit(1)
    )


def _refresh_scalar(
    latest: sa.Select[tuple[StoredRefreshRun]],
    column: str,
) -> sa.Label[object]:
    selected = latest.with_only_columns(getattr(StoredRefreshRun, column))
    return selected.scalar_subquery().label(f"latest_refresh_{column}")


def _latest_timestamp(
    timestamp: sa.ColumnElement[object],
    identity: sa.ColumnElement[object],
    *conditions: sa.ColumnElement[bool],
) -> sa.Select[tuple[object]]:
    return (
        sa.select(timestamp)
        .where(*conditions, timestamp.is_not(None))
        .order_by(timestamp.desc(), identity.desc())
        .limit(1)
    )


def _decode_competition(row: sa.Row[object]) -> CompetitionOverview:
    stored = cast(StoredCompetition, row[0])
    mapping = row._mapping
    latest_id = mapping["latest_season_id"]
    latest_season = None
    if latest_id is not None:
        # The complete identity is fetched without another query by a scalar row
        # encoded from the same deterministic latest-season ordering.
        latest_season = CompetitionSeason(
            id=latest_id,
            competition_id=stored.id,
            season_year=mapping["latest_season_year"],
            sequence_number=mapping["latest_season_sequence_number"],
            sleeper_league_id=mapping["latest_season_sleeper_league_id"],
            created_at=mapping["latest_season_created_at"],
        )
    return CompetitionOverview(
        competition=_decode_competition_identity(stored),
        summary=CompetitionActivitySummary(
            season_count=mapping["season_count"],
            latest_season=latest_season,
            latest_terminal_refresh=_decode_latest_refresh(mapping),
            latest_successful_refresh_at=mapping["latest_successful_refresh_at"],
            latest_ready_snapshot_at=mapping["latest_ready_snapshot_at"],
            latest_submitted_article_at=mapping["latest_submitted_article_at"],
        ),
    )


def _decode_season(row: sa.Row[object]) -> CompetitionSeasonOverview:
    stored = cast(StoredCompetitionSeason, row[0])
    mapping = row._mapping
    return CompetitionSeasonOverview(
        season=_decode_season_identity(stored),
        summary=CompetitionSeasonActivitySummary(
            league_name=mapping["league_name"],
            league_status=mapping["league_status"],
            latest_terminal_refresh=_decode_latest_refresh(mapping),
            latest_successful_refresh_at=mapping["latest_successful_refresh_at"],
            latest_ready_snapshot_at=mapping["latest_ready_snapshot_at"],
        ),
    )


def _decode_latest_refresh(mapping: sa.RowMapping) -> LatestRefreshSummary | None:
    completed_at = mapping["latest_refresh_completed_at"]
    if completed_at is None:
        return None
    return LatestRefreshSummary(
        status=RefreshStatus(mapping["latest_refresh_status"]),
        requested_through_week=mapping["latest_refresh_requested_through_week"],
        completed_at=completed_at,
        request_count=mapping["latest_refresh_request_count"],
        succeeded_request_count=mapping["latest_refresh_succeeded_request_count"],
        failed_request_count=mapping["latest_refresh_failed_request_count"],
    )


def _decode_competition_identity(stored: StoredCompetition) -> Competition:
    return Competition(
        id=stored.id,
        display_name=stored.display_name,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
        archived_at=stored.archived_at,
    )


def _decode_season_identity(stored: StoredCompetitionSeason) -> CompetitionSeason:
    return CompetitionSeason(
        id=stored.id,
        competition_id=stored.competition_id,
        season_year=stored.season_year,
        sequence_number=stored.sequence_number,
        sleeper_league_id=stored.sleeper_league_id,
        created_at=stored.created_at,
    )


def _require_competition(session: Session, competition_id: UUID) -> None:
    found = session.scalar(
        sa.select(StoredCompetition.id).where(StoredCompetition.id == competition_id)
    )
    if found is None:
        raise CoreResourceNotFound("competition", competition_id)


__all__ = [
    "CompetitionActivitySummary",
    "CompetitionOverview",
    "CompetitionOverviewPage",
    "CompetitionOverviewReader",
    "CompetitionSeasonActivitySummary",
    "CompetitionSeasonDetail",
    "CompetitionSeasonOverview",
    "CompetitionSeasonOverviewPage",
    "LatestRefreshSummary",
]
