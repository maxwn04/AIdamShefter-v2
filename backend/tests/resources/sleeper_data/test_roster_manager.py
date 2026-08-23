from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import Engine

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.sleeper_data.players.objects import Player
from backend.resources.sleeper_data.rosters import (
    RosterManager,
    RosterManagerAssignment,
    RosterPlayer,
    SeasonRosterIdentity,
    SeasonRosterState,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound
from backend.tests.resources.sleeper_data.conftest import (
    ProjectedSeason,
    manager_context,
    seed_domain,
)


def test_roster_read_hydrates_frozen_nested_resources_and_decimal_json(
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    manager = RosterManager(
        session_factory,
        manager_context(projected_season.domain),
    )

    roster = manager.get_roster(projected_season.domain.roster_ids[0])

    assert isinstance(roster, SeasonRosterState)
    assert roster.season_roster_id == projected_season.domain.roster_ids[0]
    assert roster.competition_season_id == projected_season.domain.season_id
    assert roster.franchise_id == projected_season.domain.franchise_ids[0]
    assert roster.sleeper_roster_id == "1"
    assert roster.franchise_name == "Sleeper Resource Team 1"
    assert roster.settings == {"waiver_position": 1}
    assert roster.metadata == {"streak": "W2"}
    assert (roster.record_string, roster.wins, roster.losses, roster.ties) == (
        "2-0",
        2,
        0,
        0,
    )
    assert roster.points_for == Decimal("200.7500")
    assert roster.points_against == Decimal("180.5000")
    assert roster.source_api_request_id == projected_season.roster_request_id

    assert roster.managers == (
        RosterManagerAssignment(
            sleeper_user_id=projected_season.user_ids[0],
            display_name="Manager One",
            role="owner",
            source_order=0,
        ),
    )
    assert len(roster.players) == 1
    membership = roster.players[0]
    assert isinstance(membership, RosterPlayer)
    assert membership.role == "starter"
    assert isinstance(membership.player, Player)
    assert membership.player.sleeper_player_id == projected_season.player_ids[0]
    assert membership.player.full_name == "Alpha Quarterback"
    assert membership.player.position == "QB"
    assert membership.player.nfl_team == "SEA"
    assert membership.player.active is True
    assert membership.player.age == 25
    assert membership.player.years_experience == 3
    assert membership.player.metadata == {"rating": Decimal("9.75")}
    assert membership.player.source_api_request_id == projected_season.player_request_id

    with pytest.raises(ValidationError, match="frozen"):
        setattr(roster, "wins", 99)
    with pytest.raises(ValidationError, match="frozen"):
        setattr(membership.player, "full_name", "Changed")


def test_roster_read_reports_not_found_and_enforces_competition_scope(
    database_engine: Engine,
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    manager = RosterManager(
        session_factory,
        manager_context(projected_season.domain),
    )
    other_domain = seed_domain(database_engine, label="Other")
    other_manager = RosterManager(
        create_session_factory(database_engine),
        manager_context(other_domain),
    )

    with pytest.raises(DatalayerResourceNotFound, match="season_roster"):
        manager.get_roster(uuid4())
    with pytest.raises(DatalayerResourceNotFound, match="season_roster"):
        other_manager.get_roster(projected_season.domain.roster_ids[0])


def test_roster_identity_list_is_stable_ordered_and_competition_scoped(
    database_engine: Engine,
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    domain = projected_season.domain
    manager = RosterManager(session_factory, manager_context(domain))

    identities = manager.list_roster_identities(domain.season_id)

    assert identities == tuple(
        SeasonRosterIdentity(
            competition_id=domain.competition_id,
            competition_season_id=domain.season_id,
            season_roster_id=domain.roster_ids[index],
            franchise_id=domain.franchise_ids[index],
            sleeper_roster_id=str(index + 1),
        )
        for index in range(2)
    )
    other = seed_domain(database_engine, label="Identity Scope")
    other_manager = RosterManager(
        create_session_factory(database_engine),
        manager_context(other),
    )
    assert other_manager.list_roster_identities(domain.season_id) == ()
