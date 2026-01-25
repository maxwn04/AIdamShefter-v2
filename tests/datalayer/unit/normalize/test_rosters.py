from datalayer.sleeper_data.normalize.rosters import normalize_roster_players


def test_normalize_roster_players_role_priority():
    raw_rosters = [
        {
            "roster_id": 1,
            "players": ["p1", "p2"],
            "starters": ["p1"],
            "taxi": ["p3"],
            "reserve": [],
            "ir": [],
        }
    ]

    players = normalize_roster_players(raw_rosters, league_id="123")

    roles = {(row.player_id, row.role) for row in players}
    assert ("p1", "starter") in roles
    assert ("p2", "bench") in roles
    assert ("p3", "taxi") in roles
