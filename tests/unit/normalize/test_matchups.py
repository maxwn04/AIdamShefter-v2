from datalayer.sleeper_data.normalize.matchups import derive_games
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
            starters_json=None,
            players_json=None,
            players_points_json=None,
        ),
        MatchupRow(
            league_id="123",
            season="2024",
            week=1,
            matchup_id=10,
            roster_id=2,
            points=90.0,
            starters_json=None,
            players_json=None,
            players_points_json=None,
        ),
        MatchupRow(
            league_id="123",
            season="2024",
            week=1,
            matchup_id=11,
            roster_id=3,
            points=80.0,
            starters_json=None,
            players_json=None,
            players_points_json=None,
        ),
    ]

    games = derive_games(rows, is_playoffs=False)

    assert len(games) == 1
    game = games[0]
    assert game.matchup_id == 10
    assert game.winner_roster_id == 1
