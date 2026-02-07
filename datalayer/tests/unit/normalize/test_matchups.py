from datalayer.sleeper_data.normalize.matchups import derive_games, normalize_matchups
from datalayer.sleeper_data.schema.models import MatchupRow


def test_derive_games_pairs_two_rows():
    rows = [
        MatchupRow(
            league_id="123",
            season="2024",
            week=1,
            matchup_id=10,
            roster_id=1,
            points=100.0,
        ),
        MatchupRow(
            league_id="123",
            season="2024",
            week=1,
            matchup_id=10,
            roster_id=2,
            points=90.0,
        ),
        MatchupRow(
            league_id="123",
            season="2024",
            week=1,
            matchup_id=11,
            roster_id=3,
            points=80.0,
        ),
    ]

    games = derive_games(rows, is_playoffs=False)

    assert len(games) == 1
    game = games[0]
    assert game.matchup_id == 10
    assert game.winner_roster_id == 1


def test_normalize_matchups_emits_player_performances():
    raw_matchups = [
        {
            "matchup_id": 5,
            "roster_id": 7,
            "points": 123.4,
            "players": ["p1", "p2"],
            "starters": ["p1"],
            "players_points": {"p1": 45.5},
        }
    ]

    matchup_rows, player_performances = normalize_matchups(
        raw_matchups, league_id="league", season="2024", week=2
    )

    assert len(matchup_rows) == 1
    assert matchup_rows[0].matchup_id == 5
    assert matchup_rows[0].roster_id == 7

    assert len(player_performances) == 2
    by_player = {row.player_id: row for row in player_performances}
    assert by_player["p1"].points == 45.5
    assert by_player["p1"].role == "starter"
    assert by_player["p2"].points == 0.0
    assert by_player["p2"].role == "bench"
