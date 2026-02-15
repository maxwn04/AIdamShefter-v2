"""Tests for player query functions."""

import pytest
from sqlalchemy import create_engine

from datalayer.sleeper_data.queries.player import get_player_weekly_log
from datalayer.sleeper_data.schema.models import (
    League,
    Player,
    PlayerPerformance,
    Roster,
    TeamProfile,
    User,
)
from datalayer.sleeper_data.store.sqlite_store import bulk_insert, create_tables

LEAGUE_ID = "test-league"


@pytest.fixture
def db_conn():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        _seed_db(conn)
        yield conn


def _seed_db(conn):
    create_tables(conn)

    bulk_insert(conn, "leagues", [
        League(league_id=LEAGUE_ID, season="2024", name="Test", sport="nfl"),
    ])
    bulk_insert(conn, "users", [
        User(user_id="u1", display_name="Alice"),
        User(user_id="u2", display_name="Bob"),
    ])
    bulk_insert(conn, "rosters", [
        Roster(league_id=LEAGUE_ID, roster_id=1, owner_user_id="u1"),
        Roster(league_id=LEAGUE_ID, roster_id=2, owner_user_id="u2"),
    ])
    bulk_insert(conn, "team_profiles", [
        TeamProfile(league_id=LEAGUE_ID, roster_id=1, team_name="Alpha", manager_name="A"),
        TeamProfile(league_id=LEAGUE_ID, roster_id=2, team_name="Beta", manager_name="B"),
    ])
    bulk_insert(conn, "players", [
        Player(player_id="p1", full_name="Patrick Mahomes", position="QB", nfl_team="KC"),
    ])
    # 3 weeks of performances
    perfs = [
        PlayerPerformance(
            league_id=LEAGUE_ID, season="2024", week=1, player_id="p1",
            roster_id=1, matchup_id=1, points=25.0, role="starter",
        ),
        PlayerPerformance(
            league_id=LEAGUE_ID, season="2024", week=2, player_id="p1",
            roster_id=1, matchup_id=1, points=18.0, role="starter",
        ),
        PlayerPerformance(
            league_id=LEAGUE_ID, season="2024", week=3, player_id="p1",
            roster_id=2, matchup_id=1, points=30.0, role="starter",
        ),
    ]
    bulk_insert(conn, "player_performances", perfs)


def test_full_season(db_conn):
    result = get_player_weekly_log(db_conn, LEAGUE_ID, "Patrick Mahomes")

    assert result["found"] is True
    assert result["player_name"] == "Patrick Mahomes"
    assert result["weeks_played"] == 3
    assert result["total_points"] == 73.0
    assert result["avg_points"] == round(73.0 / 3, 2)
    assert len(result["performances"]) == 3
    assert "week_from" not in result
    assert "week_to" not in result


def test_with_week_range(db_conn):
    result = get_player_weekly_log(db_conn, LEAGUE_ID, "Patrick Mahomes", week_from=2, week_to=3)

    assert result["found"] is True
    assert result["weeks_played"] == 2
    assert result["total_points"] == 48.0
    assert result["week_from"] == 2
    assert result["week_to"] == 3


def test_with_only_week_from(db_conn):
    result = get_player_weekly_log(db_conn, LEAGUE_ID, "Patrick Mahomes", week_from=2)

    assert result["found"] is True
    assert result["weeks_played"] == 2
    assert result["total_points"] == 48.0
    assert result["week_from"] == 2
    assert "week_to" not in result


def test_with_only_week_to(db_conn):
    result = get_player_weekly_log(db_conn, LEAGUE_ID, "Patrick Mahomes", week_to=1)

    assert result["found"] is True
    assert result["weeks_played"] == 1
    assert result["total_points"] == 25.0
    assert "week_from" not in result
    assert result["week_to"] == 1


def test_player_not_found(db_conn):
    result = get_player_weekly_log(db_conn, LEAGUE_ID, "Nobody Real")

    assert result["found"] is False


def test_team_name_present(db_conn):
    """Verify the fantasy team name appears in each performance row."""
    result = get_player_weekly_log(db_conn, LEAGUE_ID, "Patrick Mahomes")

    teams = [p["team_name"] for p in result["performances"]]
    assert teams == ["Alpha", "Alpha", "Beta"]
