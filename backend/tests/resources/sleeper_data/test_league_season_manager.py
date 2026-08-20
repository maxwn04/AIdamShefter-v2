from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine

from backend.database.sessions import SessionFactory
from backend.resources.sleeper_data.league_seasons import (
    LeagueSeasonManager,
    LeagueSeasonOverview,
    RefreshSeasonIdentity,
    SnapshotPlanningContext,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound
from backend.tests.resources.sleeper_data.conftest import (
    ProjectedSeason,
    manager_context,
    seed_domain,
)


def test_refresh_identity_does_not_require_normalized_league(
    database_engine: Engine,
    session_factory: SessionFactory,
) -> None:
    domain = seed_domain(database_engine, label="Bootstrap")
    manager = LeagueSeasonManager(session_factory, manager_context(domain))

    identity = manager.get_refresh_identity(domain.season_id)

    assert isinstance(identity, RefreshSeasonIdentity)
    assert identity.model_dump() == {
        "competition_id": domain.competition_id,
        "competition_season_id": domain.season_id,
        "sleeper_league_id": domain.sleeper_league_id,
        "season_year": 2026,
    }

    with pytest.raises(DatalayerResourceNotFound, match="competition_season"):
        manager.get_refresh_identity(uuid4())


def test_snapshot_planning_context_uses_latest_league_metadata(
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    domain = projected_season.domain
    manager = LeagueSeasonManager(session_factory, manager_context(domain))

    context = manager.get_snapshot_planning_context(domain.season_id)

    assert isinstance(context, SnapshotPlanningContext)
    assert context.model_dump() == {
        "competition_id": domain.competition_id,
        "competition_season_id": domain.season_id,
        "sleeper_league_id": domain.sleeper_league_id,
        "season_year": 2026,
        "playoff_start_week": 15,
        "playoff_team_count": 2,
        "draft_rounds": 2,
        "league_average_match": 1,
    }


def test_season_overview_preserves_decimal_json_and_counts_current_rosters(
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    domain = projected_season.domain
    manager = LeagueSeasonManager(session_factory, manager_context(domain))

    overview = manager.get_season_overview(domain.season_id)

    assert isinstance(overview, LeagueSeasonOverview)
    assert overview.competition_id == domain.competition_id
    assert overview.competition_season_id == domain.season_id
    assert overview.competition_name == "Sleeper Resource League"
    assert overview.league_name == "Projected League"
    assert overview.status == "in_season"
    assert overview.scoring_settings == {"passing_bonus": Decimal("1.125")}
    assert overview.roster_positions == ("QB", "RB")
    assert overview.provider_settings == {"draft_rounds": 2}
    assert overview.roster_count == 2
    assert overview.source_api_request_id == projected_season.league_request_id


def test_league_season_reads_enforce_competition_scope_and_not_found(
    database_engine: Engine,
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    other = seed_domain(database_engine, label="Other")
    other_manager = LeagueSeasonManager(session_factory, manager_context(other))

    with pytest.raises(DatalayerResourceNotFound, match="competition_season"):
        other_manager.get_snapshot_planning_context(projected_season.domain.season_id)
    with pytest.raises(DatalayerResourceNotFound, match="league_season_overview"):
        other_manager.get_snapshot_planning_context(other.season_id)
    with pytest.raises(DatalayerResourceNotFound, match="league_season_overview"):
        other_manager.get_season_overview(other.season_id)
    with pytest.raises(DatalayerResourceNotFound, match="league_season_overview"):
        LeagueSeasonManager(
            session_factory, manager_context(projected_season.domain)
        ).get_season_overview(uuid4())
