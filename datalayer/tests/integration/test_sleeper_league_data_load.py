from datalayer.sleeper_data.sleeper_league_data import SleeperLeagueData


def test_load_pipeline_and_queries(monkeypatch_sleeper_api, sleeper_config):
    data = SleeperLeagueData(config=sleeper_config)
    data.load()

    assert data.conn is not None

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
