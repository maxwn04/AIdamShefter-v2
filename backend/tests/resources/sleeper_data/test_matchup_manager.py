from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import Engine

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.sleeper_data.matchups import (
    Matchup,
    MatchupManager,
    PlayerPerformance,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound
from backend.tests.resources.sleeper_data.conftest import (
    ProjectedSeason,
    manager_context,
    seed_domain,
)


def test_matchup_read_returns_exact_week_with_typed_player_performances(
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    manager = MatchupManager(
        session_factory,
        manager_context(projected_season.domain),
    )

    matchups = manager.list_matchups(
        projected_season.domain.season_id,
        projected_season.week,
    )

    assert len(matchups) == 2
    assert all(isinstance(matchup, Matchup) for matchup in matchups)
    by_roster = {matchup.sleeper_roster_id: matchup for matchup in matchups}
    first = by_roster["1"]
    second = by_roster["2"]
    assert first.season_roster_id == projected_season.domain.roster_ids[0]
    assert first.franchise_id == projected_season.domain.franchise_ids[0]
    assert first.franchise_name == "Sleeper Resource Team 1"
    assert first.week == projected_season.week
    assert first.sleeper_matchup_id == 1
    assert first.points == Decimal("101.5000")
    assert first.source_api_request_id == projected_season.matchup_request_id
    assert first.player_performances == (
        PlayerPerformance(
            sleeper_player_id=projected_season.player_ids[0],
            full_name="Alpha Quarterback",
            points=Decimal("25.1250"),
            role="starter",
        ),
    )
    assert second.season_roster_id == projected_season.domain.roster_ids[1]
    assert second.franchise_id == projected_season.domain.franchise_ids[1]
    assert second.points == Decimal("87.2500")
    assert second.player_performances == ()
    assert second.source_api_request_id == projected_season.matchup_request_id

    assert (
        manager.list_matchups(
            projected_season.domain.season_id,
            projected_season.week + 1,
        )
        == ()
    )
    with pytest.raises(ValidationError, match="frozen"):
        setattr(first, "points", Decimal("0"))


def test_matchup_read_reports_not_found_and_enforces_competition_scope(
    database_engine: Engine,
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    manager = MatchupManager(
        session_factory,
        manager_context(projected_season.domain),
    )
    other_domain = seed_domain(database_engine, label="Other")
    other_manager = MatchupManager(
        create_session_factory(database_engine),
        manager_context(other_domain),
    )

    with pytest.raises(DatalayerResourceNotFound, match="competition_season"):
        manager.list_matchups(uuid4(), projected_season.week)
    with pytest.raises(DatalayerResourceNotFound, match="competition_season"):
        other_manager.list_matchups(
            projected_season.domain.season_id,
            projected_season.week,
        )
