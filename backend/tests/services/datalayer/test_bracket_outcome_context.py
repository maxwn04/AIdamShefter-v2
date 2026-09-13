"""Frozen query coverage does not invent playoff field or elimination rules."""

from pathlib import Path

import pytest

from backend.services.datalayer import FrozenLeagueData, ReadyDataSnapshot
from backend.tests.services.datalayer.test_frozen_query_runtime import _mutated_copy_many, v3_ready_snapshot


def changed_bracket(snapshot: ReadyDataSnapshot, path: Path, bracket: str, placement: int | None = None):
    return snapshot.model_copy(update={"artifact": _mutated_copy_many(snapshot.artifact.path, path, (
        ("DELETE FROM playoff_matchups", ()),
        ("UPDATE leagues SET playoff_teams=6", ()),
        ("INSERT INTO playoff_matchups (league_id,season,bracket_type,node_key,round,matchup_id,t1_roster_id,t2_roster_id,winner_roster_id,loser_roster_id,placement) SELECT league_id,season,?,'test-round1',1,1,1,2,2,1,? FROM leagues WHERE season='2026'", (bracket, placement)),
    ))})


def test_visible_round_participants_do_not_become_remaining_field(v3_ready_snapshot, tmp_path):
    with FrozenLeagueData.open(changed_bracket(v3_ready_snapshot, tmp_path / "partial.sqlite", "losers")) as data:
        result = data.get_playoff_bracket()
        assert result["configured_playoff_teams"] == 6
        assert result["observed_matchup_count"] == 1
        assert result["observed_participants"] == ["Alpha", "Beta"]
        assert result["remaining_field_status"] == "not_established"
        assert result["coverage"] == "visible_recorded_matchups"
        matchup = result["brackets"]["losers"]["rounds"][1][0]
        assert matchup["winner"] == "Beta" and matchup["loser"] == "Alpha"
        for team in ("1", "2"):
            path = data.get_team_playoff_path(team)
            assert path["is_eliminated"] is None
            assert path["elimination_status"] == "not_established"
            assert path["matchups"][0]["result_kind"] == "recorded_bracket_outcome"


@pytest.mark.parametrize(("bracket", "placement", "expected"), [
    ("winners", None, None), ("winners", 1, False), ("winners", 3, True), ("losers", 1, None),
])
def test_only_recorded_winners_final_placement_establishes_status(v3_ready_snapshot, tmp_path, bracket, placement, expected):
    with FrozenLeagueData.open(changed_bracket(v3_ready_snapshot, tmp_path / "placement.sqlite", bracket, placement)) as data:
        winner = data.get_team_playoff_path("2")
        assert winner["is_eliminated"] is expected
        assert winner["is_champion"] is (bracket == "winners" and placement == 1)
        # The losing endpoint's placement is not declared by the source row.
        assert data.get_team_playoff_path("1")["is_eliminated"] is None
