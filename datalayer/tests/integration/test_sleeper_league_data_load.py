from datalayer.sleeper_data.sleeper_league_data import SleeperLeagueData


def test_load_pipeline_and_queries(monkeypatch_sleeper_api, sleeper_config):
    data = SleeperLeagueData(config=sleeper_config)
    data.load()

    assert data.engine is not None

    snapshot = data.get_league_snapshot()
    assert snapshot["found"] is True
    assert snapshot["as_of_week"] == 2
    assert len(snapshot["standings"]) == 2
    assert len(snapshot["games"]) == 1
    assert len(snapshot["transactions"]) >= 1

    dossier = data.get_team_dossier("Alpha", week=2)
    assert dossier["found"] is True
    assert dossier["team"]["team_name"] == "Alpha"

    roster = data.get_roster_current("Alpha")
    assert roster["found"] is True
    assert "roster" in roster
    assert "starters" in roster["roster"]
    assert "bench" in roster["roster"]


def test_load_populates_bracket_data(monkeypatch_sleeper_api, sleeper_config):
    data = SleeperLeagueData(config=sleeper_config)
    data.load()

    # Verify bracket data is in the database
    result = data.run_sql("SELECT COUNT(*) as cnt FROM playoff_matchups")
    assert result["rows"][0][0] > 0

    # Verify bracket query works
    bracket = data.get_playoff_bracket()
    assert bracket["found"] is True
    assert "winners" in bracket["brackets"]

    winners = bracket["brackets"]["winners"]
    assert 1 in winners["rounds"]
    assert len(winners["rounds"][1]) == 1

    matchup = winners["rounds"][1][0]
    assert matchup["status"] == "complete"
    assert matchup["team_1"] == "Alpha"
    assert matchup["team_2"] == "Beta"
    assert matchup["winner"] == "Alpha"
    assert matchup["loser"] == "Beta"


def test_get_playoff_bracket_filtered(monkeypatch_sleeper_api, sleeper_config):
    data = SleeperLeagueData(config=sleeper_config)
    data.load()

    bracket = data.get_playoff_bracket(bracket_type="winners")
    assert bracket["found"] is True
    assert "winners" in bracket["brackets"]
    assert "losers" not in bracket["brackets"]


def test_get_team_playoff_path(monkeypatch_sleeper_api, sleeper_config):
    data = SleeperLeagueData(config=sleeper_config)
    data.load()

    path = data.get_team_playoff_path("Alpha")
    assert path["found"] is True
    assert path["team_name"] == "Alpha"
    assert path["bracket_type"] == "winners"
    assert len(path["matchups"]) >= 1
    assert path["matchups"][0]["result"] == "win"
    assert path["matchups"][0]["opponent"] == "Beta"


def test_get_team_playoff_path_not_found(monkeypatch_sleeper_api, sleeper_config):
    data = SleeperLeagueData(config=sleeper_config)
    data.load()

    path = data.get_team_playoff_path("NonexistentTeam")
    assert path["found"] is False
