import pytest
from pydantic import ValidationError

import backend.resources.sleeper_data as sleeper_data
from backend.resources.sleeper_data import (
    ApiRequestManager,
    LeagueSeasonManager,
    MatchupManager,
    NormalizedScopeManager,
    PlayerManager,
    PlayerSearch,
    RefreshRunManager,
    RosterManager,
    TransactionManager,
)


def test_all_resource_managers_are_exported_from_distinct_owning_modules() -> None:
    managers = (
        RefreshRunManager,
        ApiRequestManager,
        NormalizedScopeManager,
        LeagueSeasonManager,
        RosterManager,
        MatchupManager,
        TransactionManager,
        PlayerManager,
    )
    exported_managers = {
        name: getattr(sleeper_data, name)
        for name in sleeper_data.__all__
        if name.endswith("Manager")
    }

    assert set(exported_managers.values()) == set(managers)
    assert len({manager.__module__ for manager in managers}) == len(managers)
    assert all(manager.__module__.endswith(".manager") for manager in managers)
    assert "SleeperDataManager" not in sleeper_data.__all__
    assert not hasattr(sleeper_data, "SleeperDataManager")


@pytest.mark.parametrize("field", ("text", "position", "nfl_team"))
def test_player_search_rejects_blank_filters(field: str) -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        PlayerSearch(**{field: " "})


@pytest.mark.parametrize(
    ("field", "value"),
    (("limit", 0), ("limit", 201), ("offset", -1)),
)
def test_player_search_rejects_unsafe_pagination(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        PlayerSearch(**{field: value})
