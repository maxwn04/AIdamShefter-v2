from datalayer.sleeper_data.normalize.bracket import normalize_bracket


def test_normalize_bracket_seeded_matchup():
    raw = [{"r": 1, "m": 1, "t1": 3, "t2": 6, "w": 3, "l": 6}]
    result = normalize_bracket(
        raw, league_id="123", season="2024", bracket_type="winners"
    )
    assert len(result) == 1
    m = result[0]
    assert m.round == 1
    assert m.matchup_id == 1
    assert m.t1_roster_id == 3
    assert m.t2_roster_id == 6
    assert m.winner_roster_id == 3
    assert m.loser_roster_id == 6
    assert m.bracket_type == "winners"
    assert m.t1_from_matchup_id is None
    assert m.t1_from_outcome is None
    assert m.placement is None


def test_normalize_bracket_progression_matchup():
    raw = [
        {
            "r": 2,
            "m": 3,
            "t1": 1,
            "t2": None,
            "t1_from": {"w": 1},
            "t2_from": {"l": 2},
            "w": None,
            "l": None,
            "p": 1,
        }
    ]
    result = normalize_bracket(
        raw, league_id="123", season="2024", bracket_type="winners"
    )
    assert len(result) == 1
    m = result[0]
    assert m.round == 2
    assert m.matchup_id == 3
    assert m.t1_roster_id == 1
    assert m.t2_roster_id is None
    assert m.t1_from_matchup_id == 1
    assert m.t1_from_outcome == "w"
    assert m.t2_from_matchup_id == 2
    assert m.t2_from_outcome == "l"
    assert m.winner_roster_id is None
    assert m.loser_roster_id is None
    assert m.placement == 1


def test_normalize_bracket_empty():
    result = normalize_bracket(
        [], league_id="123", season="2024", bracket_type="losers"
    )
    assert result == []


def test_normalize_bracket_skips_missing_fields():
    raw = [
        {"r": 1, "m": 1, "t1": 1, "t2": 2},
        {"r": None, "m": 2, "t1": 3, "t2": 4},
        {"r": 1, "m": None, "t1": 5, "t2": 6},
        {"t1": 7, "t2": 8},
    ]
    result = normalize_bracket(
        raw, league_id="123", season="2024", bracket_type="winners"
    )
    assert len(result) == 1
    assert result[0].matchup_id == 1
