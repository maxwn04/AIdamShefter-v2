from datalayer.sleeper_data.config import SleeperConfig
from datalayer.sleeper_data.sleeper_league_data import SleeperLeagueData


def test_week_override_updates_season_context(monkeypatch_sleeper_api):
    config = SleeperConfig(league_id="123", week_override=1)
    data = SleeperLeagueData(config=config)
    data.load()

    result = data.run_sql(
        "SELECT computed_week, override_week, effective_week FROM season_context LIMIT 1"
    )
    assert result["rows"][0] == (2, 1, 1)
