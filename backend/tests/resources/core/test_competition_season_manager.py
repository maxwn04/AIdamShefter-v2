from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest

from backend.database.sessions import SessionFactory
from backend.resources.core import (
    ArchiveCompetition,
    CompetitionArchivedConflict,
    CompetitionManager,
    CompetitionSeasonManager,
    CompetitionSeasonQuery,
    CompetitionSeasonYearExists,
    CoreResourceNotFound,
    CreateCompetition,
    CreateCompetitionSeason,
    SleeperLeagueIdExists,
)
from backend.tests.resources.core.conftest import competition_context


def _season_manager(
    session_factory: SessionFactory,
    competition_id: UUID,
) -> CompetitionSeasonManager:
    return CompetitionSeasonManager(
        session_factory,
        competition_context(competition_id),
    )


def test_create_get_list_and_scope_seasons(
    session_factory: SessionFactory,
    competition_manager: CompetitionManager,
) -> None:
    competition = competition_manager.create(CreateCompetition(display_name="Main"))
    other = competition_manager.create(CreateCompetition(display_name="Other"))
    manager = _season_manager(session_factory, competition.id)

    first = manager.create(
        CreateCompetitionSeason(
            season_year=2025,
            sleeper_league_id=" sleeper-2025 ",
        )
    )
    second = manager.create(
        CreateCompetitionSeason(
            season_year=2026,
            sleeper_league_id="sleeper-2026",
        )
    )

    page = manager.list(CompetitionSeasonQuery(limit=1))
    next_page = manager.list(CompetitionSeasonQuery(limit=1, offset=1))
    assert first.sequence_number == 1
    assert first.sleeper_league_id == "sleeper-2025"
    assert second.sequence_number == 2
    assert page.total == 2
    assert page.items == (second,)
    assert next_page.items == (first,)
    assert manager.get(first.id) == first
    with pytest.raises(CoreResourceNotFound, match="competition_season"):
        _season_manager(session_factory, other.id).get(first.id)


def test_duplicate_year_and_global_sleeper_id_are_distinct_typed_conflicts(
    session_factory: SessionFactory,
    competition_manager: CompetitionManager,
) -> None:
    first_competition = competition_manager.create(
        CreateCompetition(display_name="First")
    )
    second_competition = competition_manager.create(
        CreateCompetition(display_name="Second")
    )
    first_manager = _season_manager(session_factory, first_competition.id)
    second_manager = _season_manager(session_factory, second_competition.id)
    first_manager.create(
        CreateCompetitionSeason(
            season_year=2026,
            sleeper_league_id="shared-sleeper-id",
        )
    )

    with pytest.raises(CompetitionSeasonYearExists) as year_error:
        first_manager.create(
            CreateCompetitionSeason(
                season_year=2026,
                sleeper_league_id="different-sleeper-id",
            )
        )
    assert year_error.value.competition_id == first_competition.id
    assert year_error.value.season_year == 2026

    with pytest.raises(SleeperLeagueIdExists) as sleeper_error:
        second_manager.create(
            CreateCompetitionSeason(
                season_year=2025,
                sleeper_league_id="shared-sleeper-id",
            )
        )
    assert sleeper_error.value.sleeper_league_id == "shared-sleeper-id"


def test_archived_competitions_keep_historical_reads_but_reject_new_seasons(
    session_factory: SessionFactory,
    competition_manager: CompetitionManager,
) -> None:
    competition = competition_manager.create(
        CreateCompetition(display_name="Archive Test")
    )
    manager = _season_manager(session_factory, competition.id)
    season = manager.create(
        CreateCompetitionSeason(
            season_year=2026,
            sleeper_league_id="archive-season",
        )
    )
    competition_manager.archive(ArchiveCompetition(competition_id=competition.id))

    assert manager.get(season.id) == season
    assert manager.list(CompetitionSeasonQuery()).items == (season,)
    with pytest.raises(CompetitionArchivedConflict):
        manager.create(
            CreateCompetitionSeason(
                season_year=2027,
                sleeper_league_id="archived-new-season",
            )
        )


def test_missing_competition_scope_is_typed_for_list_and_create(
    session_factory: SessionFactory,
) -> None:
    manager = _season_manager(session_factory, uuid4())

    with pytest.raises(CoreResourceNotFound, match="competition"):
        manager.list(CompetitionSeasonQuery())
    with pytest.raises(CoreResourceNotFound, match="competition"):
        manager.create(
            CreateCompetitionSeason(
                season_year=2026,
                sleeper_league_id="missing-scope",
            )
        )


def test_concurrent_creates_allocate_distinct_sequences(
    session_factory: SessionFactory,
    competition_manager: CompetitionManager,
) -> None:
    competition = competition_manager.create(
        CreateCompetition(display_name="Concurrent")
    )
    manager = _season_manager(session_factory, competition.id)
    commands = (
        CreateCompetitionSeason(
            season_year=2025,
            sleeper_league_id="concurrent-2025",
        ),
        CreateCompetitionSeason(
            season_year=2026,
            sleeper_league_id="concurrent-2026",
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        created = tuple(pool.map(manager.create, commands))

    assert {season.sequence_number for season in created} == {1, 2}
    assert manager.list(CompetitionSeasonQuery()).total == 2
