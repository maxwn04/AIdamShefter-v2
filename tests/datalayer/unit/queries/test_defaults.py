import sqlite3

from datalayer.sleeper_data.queries import get_week_games
from datalayer.sleeper_data.queries._resolvers import resolve_player_id
from datalayer.sleeper_data.schema.models import (
    Game,
    League,
    MatchupRow,
    Player,
    PlayerPerformance,
    Roster,
    TeamProfile,
    User,
)
from datalayer.sleeper_data.store.sqlite_store import bulk_insert, create_tables


def _seed_minimal_game(conn):
    league = League(
        league_id="123",
        season="2024",
        name="Test League",
        sport="nfl",
    )
    users = [
        User(user_id="u1", display_name="Alice"),
        User(user_id="u2", display_name="Bob"),
    ]
    rosters = [
        Roster(league_id="123", roster_id=1, owner_user_id="u1"),
        Roster(league_id="123", roster_id=2, owner_user_id="u2"),
    ]
    profiles = [
        TeamProfile(league_id="123", roster_id=1, team_name="Alpha", manager_name="A"),
        TeamProfile(league_id="123", roster_id=2, team_name="Beta", manager_name="B"),
    ]
    players = [
        Player(player_id="p1", full_name="Player One", position="QB", nfl_team="AAA"),
        Player(player_id="p2", full_name="Player Two", position="RB", nfl_team="BBB"),
    ]
    matchup = MatchupRow(
        league_id="123",
        season="2024",
        week=1,
        matchup_id=1,
        roster_id=1,
        points=100.0,
    )
    matchup_b = MatchupRow(
        league_id="123",
        season="2024",
        week=1,
        matchup_id=1,
        roster_id=2,
        points=90.0,
    )
    player_performances = [
        PlayerPerformance(
            league_id="123",
            season="2024",
            week=1,
            player_id="p1",
            roster_id=1,
            matchup_id=1,
            points=60.0,
            role="starter",
        ),
        PlayerPerformance(
            league_id="123",
            season="2024",
            week=1,
            player_id="p2",
            roster_id=1,
            matchup_id=1,
            points=40.0,
            role="bench",
        ),
        PlayerPerformance(
            league_id="123",
            season="2024",
            week=1,
            player_id="p1",
            roster_id=2,
            matchup_id=1,
            points=50.0,
            role="bench",
        ),
        PlayerPerformance(
            league_id="123",
            season="2024",
            week=1,
            player_id="p2",
            roster_id=2,
            matchup_id=1,
            points=40.0,
            role="starter",
        ),
    ]
    game = Game(
        league_id="123",
        season="2024",
        week=1,
        matchup_id=1,
        roster_id_a=1,
        roster_id_b=2,
        points_a=100.0,
        points_b=90.0,
        winner_roster_id=1,
        is_playoffs=False,
    )

    bulk_insert(conn, league.table_name, [league])
    bulk_insert(conn, users[0].table_name, users)
    bulk_insert(conn, rosters[0].table_name, rosters)
    bulk_insert(conn, profiles[0].table_name, profiles)
    bulk_insert(conn, players[0].table_name, players)
    bulk_insert(conn, matchup.table_name, [matchup, matchup_b])
    bulk_insert(conn, player_performances[0].table_name, player_performances)
    bulk_insert(conn, game.table_name, [game])


def test_get_week_games_includes_players():
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    _seed_minimal_game(conn)

    result = get_week_games(conn, "123", 1, roster_key="Alpha", include_players=True)

    assert result["found"] is True
    assert result["as_of_week"] == 1
    assert len(result["games"]) == 1
    assert result["games"][0]["team_a"] == "Alpha"
    assert result["games"][0]["team_a_players"]


def test_resolve_player_id_by_name():
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    player = Player(player_id="p1", full_name="Player One")
    bulk_insert(conn, player.table_name, [player])

    resolved = resolve_player_id(conn, "Player One")

    assert resolved["found"] is True
    assert resolved["player_id"] == "p1"
