from datalayer.sleeper_data.config import SleeperConfig
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


def test_from_file_loads_snapshot_for_queries(
    monkeypatch_sleeper_api, sleeper_config, tmp_path
):
    data = SleeperLeagueData(config=sleeper_config)
    data.load()
    snapshot_path = tmp_path / "league.sqlite"
    data.save_to_file(str(snapshot_path))

    snapshot = SleeperLeagueData.from_file(snapshot_path)

    assert snapshot.league_id == "123"
    assert snapshot.effective_week == 2

    standings = snapshot.get_standings(week=2)
    assert standings["found"] is True
    assert standings["as_of_week"] == 2

    dossier = snapshot.get_team_dossier("Alpha", week=2)
    assert dossier["found"] is True
    assert dossier["team"]["team_name"] == "Alpha"


def test_brackets_not_loaded_before_playoffs(monkeypatch_sleeper_api, sleeper_config):
    """Brackets should not be loaded when effective_week < playoff_week_start."""
    data = SleeperLeagueData(config=sleeper_config)
    data.load()

    # effective_week=2, playoff_week_start=15 — brackets should be skipped
    result = data.run_sql("SELECT COUNT(*) as cnt FROM playoff_matchups")
    assert result["rows"][0][0] == 0

    bracket = data.get_playoff_bracket()
    assert bracket["found"] is False


def test_brackets_loaded_during_playoffs(monkeypatch_sleeper_api):
    """Brackets should be loaded when effective_week >= playoff_week_start."""
    # playoff_week_start=15 in fixture, so override to week 15
    config = SleeperConfig(league_id="123", week_override=15)
    data = SleeperLeagueData(config=config)
    data.load()

    result = data.run_sql("SELECT COUNT(*) as cnt FROM playoff_matchups")
    assert result["rows"][0][0] > 0

    bracket = data.get_playoff_bracket()
    assert bracket["found"] is True
    assert "winners" in bracket["brackets"]


def test_get_playoff_bracket_filtered(monkeypatch_sleeper_api):
    """Bracket filtering works when brackets are loaded."""
    config = SleeperConfig(league_id="123", week_override=15)
    data = SleeperLeagueData(config=config)
    data.load()

    bracket = data.get_playoff_bracket(bracket_type="winners")
    assert bracket["found"] is True
    assert "winners" in bracket["brackets"]
    assert "losers" not in bracket["brackets"]


def test_get_team_playoff_path(monkeypatch_sleeper_api):
    """Team playoff path works when brackets are loaded."""
    config = SleeperConfig(league_id="123", week_override=15)
    data = SleeperLeagueData(config=config)
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
