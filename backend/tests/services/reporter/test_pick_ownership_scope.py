"""Snapshot ownership caveats retain data and do not reinterpret dated trades."""
from copy import deepcopy

from backend.services.reporter.runner.tools.evidence_presentation import (
    _PICK_OWNERSHIP_LIMITATION, evidence_page, selected_records,
)

SEASONS = [{"role": "primary", "competition_season_id": "fixture-season", "season_year": 2025, "through_week": 3}]


def records(raw, tool="roster_at_cutoff"):
    return selected_records("e1_0", tool, raw, {}, SEASONS,
                            lambda name, season: ("subject-" + name, name))


def roster(picks):
    return {"found": True, "team": {"team_name": "Cedar"},
            "roster": {"starters": {"qb": [{"player_name": "Player A", "position": "QB"}]}},
            "picks": picks}


def test_inventory_caveat_preserves_original_fields_scope_and_raw_input():
    raw = roster([{"season": "2027", "round": 1,
                   "original_team_name": "Birch", "current_team_name": "Cedar"}])
    original = deepcopy(raw)
    selected = records(raw)
    pick, = [r for r in selected if "original_team_name" in r.fields]
    assert pick.fields == original["picks"][0]
    assert pick.season == 2025 and pick.week_from == pick.week_to == 3
    assert pick.temporal_kind == "observation"
    assert pick.field_paths["current_team_name"] == "/picks/0/current_team_name"
    assert _PICK_OWNERSHIP_LIMITATION in pick.limitations
    assert raw == original
    player, = [r for r in selected if r.fields.get("player_name") == "Player A"]
    assert _PICK_OWNERSHIP_LIMITATION not in player.limitations


def test_empty_inventory_is_also_qualified_without_inventing_missing_picks():
    root, = [r for r in records(roster([])) if "picks" in r.fields]
    assert root.fields["picks"] == []
    assert _PICK_OWNERSHIP_LIMITATION in root.limitations
    assert root.outcome == "found"


def test_selected_cutoff_does_not_claim_historical_observation_time():
    selected = records(roster([]))
    assert all("Snapshot observation at cutoff" not in " ".join(r.limitations) for r in selected)
    assert any("Snapshot selected for the reporting cutoff" in " ".join(r.limitations) for r in selected)


def test_dated_transaction_pick_assets_do_not_receive_inventory_caveat():
    raw = {"transactions": [{"type": "trade", "status": "complete", "week": 2,
                             "created_ts": 1758000000000,
                             "assets_received": [{"asset_type": "pick", "season": "2027", "round": 1}]}]}
    selected = records(raw, "transactions")
    assert all(_PICK_OWNERSHIP_LIMITATION not in r.limitations for r in selected)
    assert any("occurred_at" in r.fields for r in selected)


def test_unrelated_standings_records_are_not_qualified_as_inventory():
    selected = records({"standings": [{"team_name": "Cedar", "wins": 4, "losses": 2}]}, "standings")
    assert all(_PICK_OWNERSHIP_LIMITATION not in r.limitations for r in selected)


def test_paginated_pick_rows_retain_their_scoped_limitation_references():
    selected = records(roster([
        {"season": str(2027 + i), "round": 1, "original_team_name": "Birch", "current_team_name": "Cedar"}
        for i in range(45)
    ]))
    seen = 0
    for offset in range(0, len(selected), 40):
        page = evidence_page(selected, offset=offset, limit=40, view="detail")
        for row in page["records"]:
            cited = [page["limitation_definitions"][i] for i in row.get("limitation_refs", [])]
            if "original_team_name" in row["fields"]:
                assert _PICK_OWNERSHIP_LIMITATION in cited
                seen += 1
            if row["fields"].get("player_name") == "Player A":
                assert _PICK_OWNERSHIP_LIMITATION not in cited
    assert seen == 45
