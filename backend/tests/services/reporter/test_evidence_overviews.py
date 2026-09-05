"""Regressions for observed paging and transaction-status interpretation failures."""

from dataclasses import replace
import json

from backend.services.reporter.runner.evidence import EvidenceCatalog, EvidenceRecord
from backend.services.reporter.runner.tools.evidence_presentation import evidence_page, selected_records


SEASONS = [{"role": "primary", "season_year": 2025, "through_week": 1, "competition_season_id": "season-2025"}]


def select(tool, raw):
    return selected_records("source", tool, raw, {}, SEASONS, lambda *_: (None, None))


def test_playoff_round_integer_keys_preserve_matchups_and_exact_json_paths():
    raw = {"winners": {"rounds": {
        1: [{"matchup_id": 1, "round": 1, "team_1": "Alpha", "team_2": "Beta",
             "winner": "Alpha", "loser": "Beta", "status": "complete"}],
        2: [{"matchup_id": 2, "round": 2, "team_1": "Alpha", "team_2": "Gamma",
             "winner": None, "loser": None, "status": "pending"}],
    }, "champion": None, "placements": []}}
    records = select("playoff_bracket", raw)
    games = [record for record in records if "round" in record.fields]
    assert [record.fields["round"] for record in games] == [1, 2]
    assert [record.fields["status"] for record in games] == ["complete", "pending"]
    assert games[0].fields["winner"] == "Alpha"
    assert games[1].fields["winner"] is None
    assert games[0].field_paths["winner"] == "/winners/rounds/1/0/winner"
    assert games[1].field_paths["winner"] == "/winners/rounds/2/0/winner"
    assert set(raw["winners"]["rounds"]) == {1, 2}  # Private raw audit is unchanged.
    assert evidence_page(records)["records"]


def test_all_six_game_scores_precede_optional_player_details():
    games = [{
        "week": 1, "sleeper_matchup_number": index + 1,
        "team_a": f"Home {index}", "team_b": f"Away {index}",
        "points_a": 100.25 + index, "points_b": 90.75 + index,
        "winner": f"Home {index}",
        "team_a_players": {"starters": {"wr": [
            {"player_name": f"Player {index}-{player}", "points": 10.0}
            for player in range(55)
        ]}},
    } for index in range(6)]
    records = select("week_games", games)
    catalog = EvidenceCatalog()
    catalog.register("source", records)
    overview = evidence_page(records)
    assert overview["next_offset"] is None
    assert overview["total_records"] == 18
    assert overview["catalog_records"] > 300
    assert len([r for r in overview["records"] if "winner" in r["fields"]]) == 6
    assert {r["fields"]["sleeper_matchup_number"] for r in overview["records"] if "winner" in r["fields"]} == set(range(1, 7))
    for item in overview["records"]:
        assert catalog.resolve(item["ref"]).fields == item["fields"]
        assert item["fields"]["sleeper_matchup_number"] in range(1, 7)
    detail = evidence_page(records, view="detail")
    assert detail["next_offset"] == 40
    assert any("player_name" in r["fields"] for r in detail["records"])
    assert len(json.dumps(overview)) < sum(len(json.dumps(evidence_page(records, offset, view="detail"))) for offset in range(0, len(records), 40)) / 5


def test_later_failed_transaction_warning_does_not_contaminate_completed_page():
    records = tuple(EvidenceRecord(
        ref=f"source.r{index}", source="source", tool="transactions", outcome="found",
        fields={"player_name": f"Player {index}", "status": "complete"}, perspective="received",
    ) for index in range(41))
    failed = replace(records[-1], outcome="unavailable", fields={"player_name": "Failed bid", "status": "failed"}, limitations=("Transaction is not confirmed complete.",))
    records = (*records[:-1], failed)
    first = evidence_page(records)
    assert first["limitation_definitions"] == []
    assert all("limitation_refs" not in record for record in first["records"])
    assert all(record["fields"]["status"] == "complete" for record in first["records"])
    assert all("complete" not in record and not record["population_complete"] for record in first["records"])
    second = evidence_page(records, offset=first["next_offset"])
    assert second["limitation_definitions"] == ["Transaction is not confirmed complete."]
    assert second["records"][0]["limitation_refs"] == [0]
    assert second["records"][0]["outcome"] == "unavailable"


def test_mixed_transaction_cards_preserve_direction_status_time_and_exact_paths():
    raw = [{
        "type": "waiver", "status": status, "week": 1, "created_ts": 1756160492371,
        "bid_amount": bid, "details": [{"team_name": team,
            "assets_sent": [], "assets_received": [{"asset_type": "player", "player_name": "Receiver"}]}],
    } for status, bid, team in [("complete", 20, "Winner"), ("failed", 5, "Failed bidder")]]
    records = select("transactions", raw)
    page = evidence_page(records)
    assert len(page["records"]) == 2
    complete, failed = page["records"]
    assert complete["fields"]["status"] == "complete" and complete["outcome"] == "found"
    assert "limitation_refs" not in complete
    assert failed["fields"]["status"] == "failed" and failed["outcome"] == "unavailable"
    assert failed["limitation_refs"] == [0]
    assert complete["fields"]["occurred_at"] == "2025-08-25T22:21:32.371Z"
    assert complete["fields"]["source_week"] == 1
    assert page["scope"]["week_from"] is None and page["scope"]["week_to"] is None
    assert {**page["scope"], **complete}["perspective"] == "received"
    source = next(record for record in records if record.ref == complete["ref"])
    assert source.field_paths["occurred_at"] == "/0/created_ts (Unix milliseconds to UTC)"
    assert source.field_paths["status"] == "/0/status"
    assert source.field_paths["player_name"] == "/0/details/0/assets_received/0/player_name"
    assert any("not postgame timing" in item for item in page["guidance"])


def test_league_overview_excludes_transaction_details_and_explains_bonus_record():
    records = select("league_snapshot", {
        "league": {"league_average_match": True},
        "games": [{"team_a": "Alpha", "team_b": "Beta", "points_a": 101, "points_b": 100, "winner": "Alpha"}],
        "standings": [{"team_name": "Alpha", "wins": 2, "losses": 0}],
        "transactions": [{"type": "waiver", "status": "failed", "week": 1}],
    })
    page = evidence_page(records)
    assert all("status" not in r["fields"] for r in page["records"])
    assert not page["limitation_definitions"]
    assert any("league-average bonus" in item for item in page["guidance"])
    assert any(r["fields"].get("wins") == 2 for r in page["records"])


def test_missing_timestamp_does_not_imply_occurrence_week_or_completed_status():
    records = select("transactions", [{"type": "waiver", "week": 1, "details": [{
        "team_name": "Unknown", "assets_received": [{"player_name": "Receiver"}], "assets_sent": [],
    }]}])
    asset = next(record for record in records if "player_name" in record.fields)
    assert asset.outcome == "unavailable"
    assert "occurred_at" not in asset.fields
    assert asset.week_from is None and asset.week_to is None
    assert any("timing is unknown" in item for item in asset.limitations)


def test_transaction_without_listed_assets_remains_visible_alongside_movements():
    records = select("transactions", [
        {"type": "waiver", "week": 1, "status": "failed", "details": []},
        {"type": "free_agent", "week": 1, "status": "complete", "details": [{
            "team_name": "Team", "assets_received": [{"player_name": "Receiver"}], "assets_sent": [],
        }]},
    ])
    page = evidence_page(records)
    assert len(page["records"]) == 2
    assert page["records"][0]["outcome"] == "unavailable"
    assert page["records"][1]["fields"]["player_name"] == "Receiver"
