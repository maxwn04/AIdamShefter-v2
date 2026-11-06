"""Configured slots remain distinct from observed player positions."""

import json
import sqlite3

import pytest

from backend.services.datalayer.query.curated.league import get_league_snapshot
from backend.services.reporter.runner.tools.evidence_presentation import (
    evidence_page,
    selected_records,
)
from backend.tests.services.datalayer.test_frozen_query_runtime import ready_snapshot


def _source_scope():
    return [{
        "role": "primary",
        "season_year": 2025,
        "through_week": 1,
        "competition_season_id": "synthetic-season",
    }]


@pytest.mark.parametrize(
    "slots",
    [
        ["QB", "SUPER_FLEX", "BN"],
        ["QB", "QB", "BN"],
        ["QB", "FLEX", "REC_FLEX", "WRRB_FLEX", "BN"],
        [],
        None,
        ["QB", "UNKNOWN_SLOT"],
    ],
)
def test_source_slots_survive_query_and_evidence_without_inference(ready_snapshot, slots):
    with (
        sqlite3.connect(ready_snapshot.artifact.path) as source,
        sqlite3.connect(":memory:") as conn,
    ):
        source.backup(conn)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT league_id, season FROM leagues LIMIT 1").fetchone()
        conn.execute(
            "UPDATE leagues SET roster_positions_json = ?",
            (json.dumps(slots) if slots is not None else None,),
        )
        raw = get_league_snapshot(conn, row["league_id"], row["season"], 1)

    assert raw["league"]["roster_positions"] == slots
    assert "roster_positions_json" not in raw["league"]
    records = selected_records(
        "s", "league_snapshot", raw, {}, _source_scope(), lambda *_: (None, None)
    )
    record = next(r for r in records if "roster_positions" in r.fields)
    assert record.fields["roster_positions"] == slots
    assert record.field_paths["roster_positions"] == "/league/roster_positions"
    page = evidence_page(records)
    assert any(r["fields"].get("roster_positions") == slots for r in page["records"])
    hints = [x for x in page["guidance"] if "SUPER_FLEX permits" in x]
    assert bool(hints) == isinstance(slots, list)
    if hints:
        assert "does not require a second quarterback" in hints[0]
        assert "historical change dates are not established" in hints[0]


def test_two_observed_quarterbacks_do_not_create_configured_slots():
    raw = {
        "team_a_players": {
            "starters": {"qb": [{"player_name": "One"}, {"player_name": "Two"}]}
        }
    }
    records = selected_records(
        "s", "team_game", raw, {}, _source_scope(), lambda *_: (None, None)
    )
    assert all("roster_positions" not in r.fields for r in records)
    assert not any("SUPER_FLEX permits" in x for x in evidence_page(records)["guidance"])
