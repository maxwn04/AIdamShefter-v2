from pathlib import Path

import pytest

from backend.services.datalayer import FrozenLeagueData, ReadyDataSnapshot
from backend.services.reporter.runner.tools.evidence_presentation import evidence_page, selected_records
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
        standings = data.get_standings(2)

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
    basis = "head_to_head_and_league_average" if league_average_match else "head_to_head"
    assert all(row["streak_basis"] == basis for row in standings["standings"])
    records = selected_records("source", "standings", standings, {}, [], lambda *_: (None, None))
    page = evidence_page(records)
    rows = [row for row in page["records"] if "streak_len" in row["fields"]]
    assert len(rows) == len(standings["standings"])
    assert all(row["fields"]["streak_basis"] == basis for row in rows)
    assert any("streak_len" in item for item in page["guidance"]) is bool(league_average_match)


def test_bracket_identity_survives_public_cards_with_overlapping_matchup_numbers(
    ready_snapshot: ReadyDataSnapshot, tmp_path: Path,
) -> None:
    artifact = _mutated_copy_many(
        ready_snapshot.artifact.path,
        tmp_path / "isolated-bracket-context.sqlite",
        tuple((
            "INSERT INTO playoff_matchups (league_id, season, bracket_type, node_key, "
            "round, matchup_id, t1_roster_id, t2_roster_id, winner_roster_id, "
            "loser_roster_id, placement) VALUES ('123', '2024', ?, 'final', 1, 1, 1, 2, ?, ?, 1)",
            (bracket_type, winner, loser),
        ) for bracket_type, winner, loser in (("winners", 1, 2), ("losers", 2, 1))),
    )
    with FrozenLeagueData.open(ready_snapshot.model_copy(update={"artifact": artifact})) as data:
        raw = data.get_playoff_bracket()
        # The source losers-bracket winner has the lower score in this fixture.
        game = data.get_team_game("Alpha", 2)["game"]
    assert game["points_a"] > game["points_b"]
    assert game["winner"] == "Alpha"
    for bracket_type, winner in (("winners", "Alpha"), ("losers", "Beta")):
        bracket = raw["brackets"][bracket_type]
        assert bracket["bracket_type"] == bracket_type
        assert bracket["rounds"][1][0]["bracket_type"] == bracket_type
        assert bracket["rounds"][1][0]["winner"] == winner
        assert bracket["placements"] == [{
            "bracket_type": bracket_type, "placement": 1, "team_name": winner,
        }]
        assert bracket["champion"] == ("Alpha" if bracket_type == "winners" else None)

    records = selected_records("source", "playoff_bracket", raw, {}, [], lambda *_: (None, None))
    page = evidence_page(records)
    for bracket_type, winner in (("winners", "Alpha"), ("losers", "Beta")):
        cards = [row["fields"] for row in page["records"] if row["fields"].get("bracket_type") == bracket_type]
        assert len(cards) == 3  # Summary, matchup, placement each retain their own label.
        assert next(row for row in cards if "matchup_id" in row)["winner"] == winner
        matchup = next(row for row in records if row.fields.get("bracket_type") == bracket_type and "matchup_id" in row.fields)
        assert matchup.field_paths["bracket_type"] == f"/brackets/{bracket_type}/rounds/1/0/bracket_type"
    assert any("may differ from the higher-scoring team" in item for item in page["guidance"])
