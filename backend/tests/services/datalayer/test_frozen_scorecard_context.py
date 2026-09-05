from pathlib import Path

import pytest

from backend.services.datalayer import FrozenLeagueData, ReadyDataSnapshot
from backend.tests.services.datalayer.test_frozen_query_runtime import (
    _mutated_copy_many,
    ready_snapshot,
)


@pytest.mark.parametrize("league_average_match", [0, 1])
def test_scorecards_retain_actual_matchup_number_and_league_format(
    ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
    league_average_match: int,
) -> None:
    artifact = _mutated_copy_many(
        ready_snapshot.artifact.path,
        tmp_path / "isolated-scorecard-context.sqlite",
        (
            ("UPDATE leagues SET league_average_match = ?", (league_average_match,)),
            ("UPDATE games SET matchup_id = 97 WHERE week = 2", ()),
            ("UPDATE matchups SET matchup_id = 97 WHERE week = 2", ()),
            ("UPDATE player_performances SET matchup_id = 97 WHERE week = 2", ()),
        ),
    )
    with FrozenLeagueData.open(ready_snapshot.model_copy(update={"artifact": artifact})) as data:
        source = data.run_sql("SELECT matchup_id FROM games WHERE week = 2")["rows"][0][0]
        snapshot = data.get_league_snapshot(2)
        games = data.get_week_games(2)
        detailed_games = data.get_week_games_with_players(2)
        team_game = data.get_team_game("Alpha", 2)["game"]
        detailed_team_game = data.get_team_game_with_players("Beta", 2)["game"]

    assert source == 97
    assert snapshot["league"]["league_average_match"] is bool(league_average_match)
    for game in (*snapshot["games"], *games, *detailed_games, team_game, detailed_team_game):
        assert game["sleeper_matchup_number"] == source
        assert isinstance(game["sleeper_matchup_number"], int)
        assert "matchup_id" not in game
        assert game["points_a"] == 110.0
        assert game["points_b"] == 105.0
    assert detailed_games[0]["team_a_players"]["starters"]["qb"]
    assert any(detailed_team_game["team_b_players"]["starters"].values())
