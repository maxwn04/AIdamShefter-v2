from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import Franchise
from backend.resources.core import (
    ApplyRosterMappings,
    CompetitionManager,
    CreateCompetition,
    CreateCompetitionSeason,
    CreateFranchiseTarget,
    ExistingFranchiseTarget,
    RosterMappingAssignment,
    RosterMappingConflict,
    RosterMappingManager,
)
from backend.resources.core.competition_seasons import CompetitionSeasonManager
from backend.tests.resources.core.conftest import competition_context, global_context


def test_mapping_manager_creates_and_idempotently_reads_mappings(
    database_engine: Engine,
    session_factory,
) -> None:
    competition = CompetitionManager(session_factory, global_context()).create(
        CreateCompetition(display_name="Identity League")
    )
    seasons = CompetitionSeasonManager(
        session_factory, competition_context(competition.id)
    )
    season = seasons.create(
        CreateCompetitionSeason(season_year=2026, sleeper_league_id="identity-1")
    )
    manager = RosterMappingManager(
        session_factory, competition_context(competition.id)
    )
    command = ApplyRosterMappings(
        competition_season_id=season.id,
        assignments=(
            RosterMappingAssignment(
                sleeper_roster_id="1",
                target=CreateFranchiseTarget(display_name="Alpha"),
            ),
        ),
    )

    created = manager.apply(command)
    repeated = manager.apply(command)

    assert len(created.franchises) == 1
    assert repeated.mappings == created.mappings
    with pytest.raises(RosterMappingConflict, match="cannot be changed"):
        manager.apply(
            ApplyRosterMappings(
                competition_season_id=season.id,
                assignments=(
                    RosterMappingAssignment(
                        sleeper_roster_id="1",
                        target=CreateFranchiseTarget(display_name="Different"),
                    ),
                ),
            )
        )


def test_mapping_manager_rejects_remap_and_cross_competition_franchise(
    database_engine: Engine,
    session_factory,
) -> None:
    competition = CompetitionManager(session_factory, global_context()).create(
        CreateCompetition(display_name="Primary")
    )
    other = CompetitionManager(session_factory, global_context()).create(
        CreateCompetition(display_name="Other")
    )
    season = CompetitionSeasonManager(
        session_factory, competition_context(competition.id)
    ).create(CreateCompetitionSeason(season_year=2026, sleeper_league_id="primary"))
    other_franchise_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Franchise),
            {
                "id": other_franchise_id,
                "competition_id": other.id,
                "display_name": "Other Team",
            },
        )
    manager = RosterMappingManager(
        session_factory, competition_context(competition.id)
    )

    with pytest.raises(RosterMappingConflict, match="does not belong"):
        manager.apply(
            ApplyRosterMappings(
                competition_season_id=season.id,
                assignments=(
                    RosterMappingAssignment(
                        sleeper_roster_id="1",
                        target=ExistingFranchiseTarget(
                            franchise_id=other_franchise_id
                        ),
                    ),
                ),
            )
        )


def test_first_season_bootstrap_does_not_run_for_later_season(
    database_engine: Engine,
    session_factory,
) -> None:
    competition = CompetitionManager(session_factory, global_context()).create(
        CreateCompetition(display_name="Dynasty")
    )
    seasons = CompetitionSeasonManager(
        session_factory, competition_context(competition.id)
    )
    seasons.create(CreateCompetitionSeason(season_year=2025, sleeper_league_id="d1"))
    later = seasons.create(
        CreateCompetitionSeason(season_year=2026, sleeper_league_id="d2")
    )
    manager = RosterMappingManager(
        session_factory, competition_context(competition.id)
    )

    catalog = manager.bootstrap_first_season(
        later.id,
        (
            RosterMappingAssignment(
                sleeper_roster_id="1",
                target=CreateFranchiseTarget(display_name="Should not exist"),
            ),
        ),
    )

    assert catalog.sequence_number == 2
    assert catalog.mappings == ()
