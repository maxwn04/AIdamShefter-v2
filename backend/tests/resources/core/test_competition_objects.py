import pytest
from pydantic import ValidationError

from backend.resources.core import (
    CompetitionQuery,
    CompetitionSeasonQuery,
    CreateCompetition,
    CreateCompetitionSeason,
)


def test_competition_commands_normalize_nonblank_strings() -> None:
    competition = CreateCompetition(display_name="  The League  ")
    season = CreateCompetitionSeason(
        season_year=2026,
        sleeper_league_id="  sleeper-2026  ",
    )

    assert competition.display_name == "The League"
    assert season.sleeper_league_id == "sleeper-2026"


@pytest.mark.parametrize(
    ("factory", "values"),
    [
        (CreateCompetition, {"display_name": "  "}),
        (
            CreateCompetitionSeason,
            {"season_year": 2026, "sleeper_league_id": "  "},
        ),
        (
            CreateCompetitionSeason,
            {"season_year": "2026", "sleeper_league_id": "league"},
        ),
        (
            CreateCompetitionSeason,
            {"season_year": 1899, "sleeper_league_id": "league"},
        ),
        (
            CreateCompetitionSeason,
            {"season_year": 10000, "sleeper_league_id": "league"},
        ),
        (CompetitionQuery, {"limit": 0}),
        (CompetitionQuery, {"limit": 201}),
        (CompetitionQuery, {"offset": -1}),
        (CompetitionSeasonQuery, {"limit": 0}),
        (CompetitionSeasonQuery, {"limit": 201}),
        (CompetitionSeasonQuery, {"offset": -1}),
    ],
)
def test_core_contracts_reject_invalid_boundaries(factory, values) -> None:
    with pytest.raises(ValidationError):
        factory(**values)
