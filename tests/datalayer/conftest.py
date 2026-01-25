import json
from pathlib import Path

import pytest

from datalayer.sleeper_data.config import SleeperConfig


@pytest.fixture
def sleeper_fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "sleeper"


@pytest.fixture
def load_fixture(sleeper_fixture_dir: Path):
    def _load(name: str):
        path = sleeper_fixture_dir / name
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    return _load


@pytest.fixture
def sleeper_fixtures(load_fixture):
    return {
        "league": load_fixture("league.json"),
        "users": load_fixture("users.json"),
        "rosters": load_fixture("rosters.json"),
        "matchups_by_week": {
            1: load_fixture("matchups_week1.json"),
            2: load_fixture("matchups_week2.json"),
        },
        "transactions_by_week": {
            1: load_fixture("transactions_week1.json"),
            2: load_fixture("transactions_week2.json"),
        },
        "players": load_fixture("players.json"),
        "traded_picks": load_fixture("traded_picks.json"),
        "state": load_fixture("state.json"),
    }


@pytest.fixture
def sleeper_config() -> SleeperConfig:
    return SleeperConfig(league_id="123", week_override=None)


@pytest.fixture
def monkeypatch_sleeper_api(monkeypatch, sleeper_fixtures):
    import datalayer.sleeper_data.sleeper_league_data as sld

    monkeypatch.setattr(sld, "get_league", lambda league_id, client=None: sleeper_fixtures["league"])
    monkeypatch.setattr(
        sld,
        "get_league_users",
        lambda league_id, client=None: sleeper_fixtures["users"],
    )
    monkeypatch.setattr(
        sld,
        "get_league_rosters",
        lambda league_id, client=None: sleeper_fixtures["rosters"],
    )
    monkeypatch.setattr(
        sld,
        "get_state",
        lambda sport, client=None: sleeper_fixtures["state"],
    )
    monkeypatch.setattr(
        sld,
        "get_matchups",
        lambda league_id, week, client=None: sleeper_fixtures["matchups_by_week"].get(
            week, []
        ),
    )
    monkeypatch.setattr(
        sld,
        "api_get_transactions",
        lambda league_id, week, client=None: sleeper_fixtures["transactions_by_week"].get(
            week, []
        ),
    )
    monkeypatch.setattr(
        sld,
        "get_players",
        lambda sport, client=None: sleeper_fixtures["players"],
    )
    monkeypatch.setattr(
        sld,
        "get_traded_picks",
        lambda league_id, client=None: sleeper_fixtures["traded_picks"],
    )

    return sleeper_fixtures
