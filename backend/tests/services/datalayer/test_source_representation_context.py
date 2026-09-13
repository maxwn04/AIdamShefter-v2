"""Actual frozen queries retain movement, score ownership and standings period."""

from pathlib import Path

import pytest

from backend.services.datalayer import FrozenLeagueData, ReadyDataSnapshot, ResolvedRosterIdentity
from backend.services.reporter.runner.tools.evidence_presentation import evidence_page, selected_records
from backend.tests.services.datalayer.test_frozen_query_runtime import (
    _mutated_copy_many, ready_snapshot, v3_ready_snapshot,
)


def _records(data, tool, raw, week, season=None):
    seasons = [item.model_dump(mode="json") for item in data.available_seasons()]

    def identity(key, year):
        result = data.resolve_roster_identity(key, season=year)
        if isinstance(result, ResolvedRosterIdentity):
            return str(result.identity.franchise_id), result.identity.sleeper_roster_id
        return None, None

    return selected_records("source", tool, raw, {"week": week, "season": season}, seasons, identity)


@pytest.mark.parametrize("same_name", [False, True])
def test_trade_endpoints_are_query_derived_and_bindable(v3_ready_snapshot: ReadyDataSnapshot, tmp_path: Path, same_name: bool):
    names = (("UPDATE team_profiles SET team_name='Same name'", ()),) if same_name else ()
    artifact = _mutated_copy_many(v3_ready_snapshot.artifact.path, tmp_path / "endpoints.sqlite", (
        ("UPDATE transactions SET type='trade'", ()),
        ("UPDATE transaction_moves SET player_id='p2', from_roster_id=1, to_roster_id=2, roster_id=CASE WHEN direction='drop' THEN 1 ELSE 2 END", ()),
    ) + names)
    with FrozenLeagueData.open(v3_ready_snapshot.model_copy(update={"artifact": artifact})) as data:
        raw = data.get_transactions(1, 1)
        records = _records(data, "transactions", raw, 1)
    assets = [record for record in records if "asset_type" in record.fields]
    assert len(assets) == 2
    assert {asset.fields["movement"] for asset in assets} == {"add", "drop"}
    assert len([row for row in evidence_page(records)["records"] if "asset_type" in row["fields"]]) == 1
    assert len([row for row in evidence_page(records, view="detail")["records"] if "asset_type" in row["fields"]]) == 2
    for asset in assets:
        assert asset.fields["from_team"] == ("Same name" if same_name else "Alpha")
        assert asset.fields["to_team"] == ("Same name" if same_name else "Beta")
        assert asset.fields["from_roster_lookup"] == {"roster_key": "1", "season": 2026}
        assert asset.fields["to_roster_lookup"] == {"roster_key": "2", "season": 2026}
        assert asset.fields["team_name"] == ("Same name" if same_name else "Alpha" if asset.perspective == "sent" else "Beta")
        assert asset.fields["roster_lookup"]["roster_key"] == ("1" if asset.perspective == "sent" else "2")
        assert asset.field_paths["movement"].endswith("/movement")


def test_unknown_source_direction_is_inspectable_and_unavailable(v3_ready_snapshot: ReadyDataSnapshot, tmp_path: Path):
    artifact = _mutated_copy_many(v3_ready_snapshot.artifact.path, tmp_path / "unknown.sqlite", (
        ("UPDATE transaction_moves SET direction='unsupported'", ()),
    ))
    with FrozenLeagueData.open(v3_ready_snapshot.model_copy(update={"artifact": artifact})) as data:
        records = _records(data, "transactions", data.get_transactions(1, 1), 1)
    assets = [row for row in evidence_page(records)["records"] if "asset_type" in row["fields"]]
    assert len(assets) == 2
    assert all(row["outcome"] == "unavailable" for row in assets)


def test_both_team_player_scores_keep_owner_on_each_card(ready_snapshot: ReadyDataSnapshot):
    with FrozenLeagueData.open(ready_snapshot) as data:
        raw = data.get_team_game_with_players("Alpha", 2)
        records = _records(data, "team_game", raw, 2)
    player_cards = [record for record in records if "player_name" in record.fields and "points" in record.fields]
    assert {record.fields["team_name"] for record in player_cards} == {"Alpha", "Beta"}
    for record in player_cards:
        assert record.perspective == record.fields["team_name"]
        assert record.field_paths["team_name"] == (
            "/game/team_a" if record.fields["team_name"] == "Alpha" else "/game/team_b"
        )


@pytest.mark.parametrize("tool", ["standings", "league_snapshot", "team_dossier"])
def test_requested_postseason_week_preserves_regular_standings_cutoff(
    ready_snapshot: ReadyDataSnapshot, tmp_path: Path, tool: str,
):
    artifact = _mutated_copy_many(ready_snapshot.artifact.path, tmp_path / "postseason.sqlite", (
        ("UPDATE leagues SET playoff_week_start=2, league_average_match=1", ()),
    ))
    with FrozenLeagueData.open(ready_snapshot.model_copy(update={"artifact": artifact})) as data:
        raw = {
            "standings": lambda: data.get_standings(2),
            "league_snapshot": lambda: data.get_league_snapshot(2),
            "team_dossier": lambda: data.get_team_dossier("Alpha", 2),
        }[tool]()
        records = _records(data, tool, raw, 2)
    assert raw["as_of_week"] == 2
    assert raw["standings_through_week"] == 1
    standings = [record for record in records if "wins" in record.fields]
    assert standings
    for record in standings:
        assert record.week_to == 1
        assert record.fields["competition_phase"] == "postseason"
        assert record.fields["standings_basis"] == "regular_season"
        assert record.units["wins"] == "standings_decisions"
    games = [record for record in records if "points_a" in record.fields]
    assert all(record.week_to == record.week_from for record in games)
    if games:
        assert any(record.week_to == 2 for record in games)
    assert any("regular season" in line for line in evidence_page(records)["guidance"])
