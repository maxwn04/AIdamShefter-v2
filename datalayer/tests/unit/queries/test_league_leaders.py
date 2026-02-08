"""Tests for get_season_leaders query function."""

import sqlite3

from datalayer.sleeper_data.queries.league import get_season_leaders
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


def _make_db():
    conn = sqlite3.connect(":memory:")
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
        Player(player_id="p2", full_name="Derrick Henry", position="RB", nfl_team="BAL"),
        Player(player_id="p3", full_name="Tyreek Hill", position="WR", nfl_team="MIA"),
    ])

    perfs = [
        # Mahomes: 3 weeks on Alpha as starter — 25 + 18 + 30 = 73
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
            roster_id=1, matchup_id=1, points=30.0, role="starter",
        ),
        # Henry: 2 weeks on Beta as starter — 20 + 15 = 35
        PlayerPerformance(
            league_id=LEAGUE_ID, season="2024", week=1, player_id="p2",
            roster_id=2, matchup_id=1, points=20.0, role="starter",
        ),
        PlayerPerformance(
            league_id=LEAGUE_ID, season="2024", week=2, player_id="p2",
            roster_id=2, matchup_id=1, points=15.0, role="starter",
        ),
        # Hill: 2 weeks — week 1 starter on Alpha, week 2 bench on Alpha — 12 + 8 = 20
        PlayerPerformance(
            league_id=LEAGUE_ID, season="2024", week=1, player_id="p3",
            roster_id=1, matchup_id=1, points=12.0, role="starter",
        ),
        PlayerPerformance(
            league_id=LEAGUE_ID, season="2024", week=2, player_id="p3",
            roster_id=1, matchup_id=1, points=8.0, role="bench",
        ),
    ]
    bulk_insert(conn, "player_performances", perfs)
    return conn


def test_basic_ranking():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID)

    assert len(result) == 3
    assert result[0]["rank"] == 1
    assert result[0]["player_name"] == "Patrick Mahomes"
    assert result[0]["total_points"] == 73.0
    assert result[1]["player_name"] == "Derrick Henry"
    assert result[2]["player_name"] == "Tyreek Hill"


def test_position_filter():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, position="RB")

    assert len(result) == 1
    assert result[0]["player_name"] == "Derrick Henry"
    assert result[0]["position"] == "RB"


def test_roster_filter():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, roster_key="Beta")

    assert len(result) == 1
    assert result[0]["player_name"] == "Derrick Henry"


def test_role_filter():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, role="starter")

    # Hill has 1 starter week (12) and 1 bench week (8), only starter counts
    hill = [r for r in result if r["player_name"] == "Tyreek Hill"]
    assert len(hill) == 1
    assert hill[0]["total_points"] == 12.0
    assert hill[0]["weeks_played"] == 1


def test_week_range_filter():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, week_from=2, week_to=3)

    # Week 2-3: Mahomes 18+30=48, Henry 15, Hill 8
    assert result[0]["player_name"] == "Patrick Mahomes"
    assert result[0]["total_points"] == 48.0


def test_sort_by_avg():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, sort_by="avg")

    # Mahomes avg 73/3=24.33, Henry avg 35/2=17.5, Hill avg 20/2=10.0
    assert result[0]["player_name"] == "Patrick Mahomes"
    assert result[0]["avg_points"] == round(73.0 / 3, 2)


def test_limit():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, limit=1)

    assert len(result) == 1
    assert result[0]["rank"] == 1


def test_limit_hard_cap():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, limit=100)

    # Should return all 3 (< 30 cap), not error
    assert len(result) == 3


def test_empty_results():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, position="TE")

    assert result == []


def test_stats_accuracy():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID)

    mahomes = result[0]
    assert mahomes["total_points"] == 73.0
    assert mahomes["avg_points"] == round(73.0 / 3, 2)
    assert mahomes["weeks_played"] == 3
    assert mahomes["best_week"] == 30.0
    assert mahomes["worst_week"] == 18.0


def test_team_name_shows_most_recent():
    """team_name should reflect the most recent fantasy team."""
    conn = _make_db()
    # Mahomes is on Alpha all 3 weeks
    result = get_season_leaders(conn, LEAGUE_ID, position="QB")
    assert result[0]["team_name"] == "Alpha"


def test_roster_key_not_found():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID, roster_key="Nonexistent Team")

    assert result == []


def test_nfl_team_present():
    conn = _make_db()
    result = get_season_leaders(conn, LEAGUE_ID)

    assert result[0]["nfl_team"] == "KC"
    assert result[1]["nfl_team"] == "BAL"
