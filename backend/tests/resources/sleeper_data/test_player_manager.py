from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import Engine

from backend.database.sessions import SessionFactory
from backend.resources.sleeper_data.players import Player, PlayerManager, PlayerSearch
from backend.tests.resources.sleeper_data.conftest import (
    ProjectedSeason,
    manager_context,
    seed_domain,
)


def test_player_search_applies_case_insensitive_filters_and_preserves_decimal_json(
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    manager = PlayerManager(session_factory, manager_context(projected_season.domain))

    by_name = manager.search_players(PlayerSearch(text=" QUARTER "))
    filtered = manager.search_players(
        PlayerSearch(position=" rb ", nfl_team=" sea ", active=False)
    )

    assert by_name.total == 1
    assert isinstance(by_name.items[0], Player)
    assert by_name.items[0].sleeper_player_id == "p1"
    assert by_name.items[0].metadata == {"rating": Decimal("9.75")}
    assert by_name.items[0].source_api_request_id == projected_season.player_request_id
    assert [player.sleeper_player_id for player in filtered.items] == ["p3"]


def test_player_search_orders_and_paginates_global_catalog(
    database_engine: Engine,
    session_factory: SessionFactory,
    projected_season: ProjectedSeason,
) -> None:
    manager = PlayerManager(session_factory, manager_context(projected_season.domain))

    page = manager.search_players(PlayerSearch(limit=2, offset=1))

    assert (page.total, page.limit, page.offset) == (4, 2, 1)
    assert [player.sleeper_player_id for player in page.items] == ["p2", "p3"]
    assert [player.full_name for player in page.items] == [
        "Beta Runner",
        "Beta Runner",
    ]

    other = seed_domain(database_engine, label="Other")
    global_page = PlayerManager(session_factory, manager_context(other)).search_players(
        PlayerSearch(limit=200)
    )
    assert global_page.total == 4
    assert [player.sleeper_player_id for player in global_page.items] == [
        "p1",
        "p2",
        "p3",
        "p4",
    ]


@pytest.mark.parametrize(
    "values",
    (
        {"text": " "},
        {"position": "\t"},
        {"nfl_team": ""},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"active": 1},
    ),
)
def test_player_search_rejects_invalid_filters_and_pagination(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PlayerSearch.model_validate(values)
