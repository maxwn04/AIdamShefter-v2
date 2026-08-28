from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.resources.sleeper_data.snapshots import SnapshotSeasonRole
from backend.services.datalayer.canonical_json import parse_json_bytes
from backend.services.datalayer.snapshot_inputs import (
    ResolvedRosterMapping,
    ResolvedSnapshotInputs,
)
from backend.services.datalayer.snapshot_service import SnapshotEndpointRecords
from backend.services.datalayer.snapshot_sqlite import (
    ResolvedSnapshotMaterializationInput,
    SQLiteSnapshotMaterializer,
    project_resolved_snapshot,
)
from backend.services.datalayer.sleeper.endpoints import (
    normalize_league,
    normalize_league_rosters,
    normalize_league_users,
    normalize_losers_bracket,
    normalize_matchups,
    normalize_player_catalog,
    normalize_transactions,
    normalize_winners_bracket,
)
from backend.services.datalayer.sleeper.scope import EndpointKind
from backend.tests.services.datalayer.test_snapshot_inputs import (
    HISTORY_ID,
    PRIMARY_ID,
    _Candidates,
    _resolve,
)


FIXTURES = Path(__file__).parents[4] / "datalayer" / "tests" / "fixtures" / "sleeper"
SHARED_FRANCHISE_ID = UUID("30000000-0000-0000-0000-000000000001")
SECOND_FRANCHISE_ID = UUID("30000000-0000-0000-0000-000000000002")


def _resolved() -> ResolvedSnapshotInputs:
    state, _ = _resolve(_Candidates())
    assert isinstance(state, ResolvedSnapshotInputs)
    mappings = tuple(
        ResolvedRosterMapping(
            competition_id=season.identity.competition_id,
            competition_season_id=season.identity.competition_season_id,
            sleeper_roster_id=str(roster_id),
            season_roster_id=UUID(int=season.identity.sequence_number * 10 + roster_id),
            franchise_id=(
                SHARED_FRANCHISE_ID if roster_id == 1 else SECOND_FRANCHISE_ID
            ),
        )
        for season in state.seasons
        for roster_id in (1, 2)
    )
    return state.model_copy(
        update={"roster_mappings": mappings, "input_revision": "c" * 64}
    )


def _materialization() -> ResolvedSnapshotMaterializationInput:
    inputs = _resolved()
    requirements = {
        requirement.request.scope_key: requirement
        for requirement in inputs.requirements.entries
    }
    endpoints = []
    for entry in inputs.manifest.entries:
        requirement = requirements[entry.scope_key]
        request = requirement.request
        kind = request.endpoint_kind
        if kind is EndpointKind.LEAGUE:
            season = next(
                season
                for season in inputs.seasons
                if request.scope_key in season.requirement_scopes
            )
            payload = {
                "league_id": season.identity.sleeper_league_id,
                "name": f"League {season.identity.season_year}",
                "season": str(season.identity.season_year),
                "sport": "nfl",
                "settings": {
                    "draft_rounds": 0,
                    "league_average_match": 0,
                    "playoff_teams": 6,
                    "playoff_week_start": 15,
                },
                "scoring_settings": {},
                "roster_positions": ["QB"],
            }
            normalizer = normalize_league
        elif kind is EndpointKind.LEAGUE_USERS:
            payload = parse_json_bytes((FIXTURES / "users.json").read_bytes())
            normalizer = normalize_league_users
        elif kind is EndpointKind.LEAGUE_ROSTERS:
            payload = parse_json_bytes((FIXTURES / "rosters.json").read_bytes())
            normalizer = normalize_league_rosters
        elif kind is EndpointKind.PLAYER_CATALOG:
            payload = parse_json_bytes((FIXTURES / "players.json").read_bytes())
            normalizer = normalize_player_catalog
        elif kind is EndpointKind.MATCHUPS:
            payload = (
                parse_json_bytes((FIXTURES / "matchups_week1.json").read_bytes())
                if request.week == 1
                else []
            )
            normalizer = normalize_matchups
        elif kind is EndpointKind.TRANSACTIONS:
            payload = (
                parse_json_bytes((FIXTURES / "transactions_week1.json").read_bytes())
                if request.week == 1
                else []
            )
            normalizer = normalize_transactions
        elif kind is EndpointKind.WINNERS_BRACKET:
            payload = []
            normalizer = normalize_winners_bracket
        elif kind is EndpointKind.LOSERS_BRACKET:
            payload = []
            normalizer = normalize_losers_bracket
        else:
            raise AssertionError(kind)
        endpoints.append(
            SnapshotEndpointRecords(
                manifest_entry=entry,
                records=normalizer(payload, request),
            )
        )
    return ResolvedSnapshotMaterializationInput(
        inputs=inputs,
        build_key="d" * 64,
        endpoint_records=tuple(endpoints),
    )


def test_projects_two_seasons_with_collision_safe_keys() -> None:
    projection = project_resolved_snapshot(_materialization())

    assert len(projection.rows_for("snapshot_seasons")) == 2
    assert {row["league_id"] for row in projection.rows_for("users")} == {
        "league-2025",
        "league-2026",
    }
    assert len(projection.rows_for("transactions")) == 2
    assert {
        (row["league_id"], row["transaction_id"])
        for row in projection.rows_for("transactions")
    } == {("league-2025", "tx1"), ("league-2026", "tx1")}
    assert {row["league_id"] for row in projection.rows_for("transaction_moves")} == {
        "league-2025",
        "league-2026",
    }
    assert {
        row["franchise_id"] for row in projection.rows_for("roster_identities")
    } == {str(SHARED_FRANCHISE_ID), str(SECOND_FRANCHISE_ID)}


def test_materializes_v3_deterministically_with_exact_metadata(tmp_path: Path) -> None:
    materialization = _materialization()
    materializer = SQLiteSnapshotMaterializer(tmp_path / "staging")

    first = materializer.materialize(materialization)
    second = materializer.materialize(materialization)
    try:
        assert first.sha256 == second.sha256
        assert first.path.read_bytes() == second.path.read_bytes()
        connection = sqlite3.connect(first.path)
        connection.row_factory = sqlite3.Row
        metadata = dict(connection.execute("SELECT * FROM snapshot_metadata").fetchone())
        seasons = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM snapshot_seasons ORDER BY sequence_number"
            ).fetchall()
        ]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        connection.close()
        assert user_version == 3
        assert metadata["input_revision"] == materialization.inputs.input_revision
        assert metadata["snapshot_projection_version"] == "3"
        assert [(row["season_year"], row["through_week"]) for row in seasons] == [
            (2025, 18),
            (2026, 3),
        ]
        assert [row["role"] for row in seasons] == ["history", "primary"]
    finally:
        first.path.unlink(missing_ok=True)
        second.path.unlink(missing_ok=True)


def test_rejects_partial_or_cross_competition_lineage() -> None:
    materialization = _materialization()
    shortened_manifest = materialization.inputs.manifest.model_copy(
        update={"entries": materialization.inputs.manifest.entries[1:]}
    )
    with pytest.raises(ValidationError, match="exactly cover"):
        ResolvedSnapshotMaterializationInput(
            inputs=materialization.inputs.model_copy(
                update={
                    "requirements": materialization.inputs.requirements.model_copy(
                        update={"entries": materialization.inputs.requirements.entries[1:]}
                    ),
                    "manifest": shortened_manifest,
                }
            ),
            build_key=materialization.build_key,
            endpoint_records=materialization.endpoint_records[1:],
        )

    history, primary = materialization.inputs.seasons
    conflicting = history.model_copy(
        update={
            "identity": history.identity.model_copy(
                update={"competition_id": UUID("40000000-0000-0000-0000-000000000001")}
            )
        }
    )
    with pytest.raises(ValidationError, match="one competition"):
        ResolvedSnapshotMaterializationInput(
            inputs=materialization.inputs.model_copy(
                update={"seasons": (conflicting, primary)}
            ),
            build_key=materialization.build_key,
            endpoint_records=materialization.endpoint_records,
        )


def test_rejects_wrong_historical_cutoff() -> None:
    materialization = _materialization()
    history, primary = materialization.inputs.seasons
    changed = materialization.inputs.model_copy(
        update={"seasons": (history.model_copy(update={"through_week": 17}), primary)}
    )

    with pytest.raises(ValidationError, match="week-18"):
        ResolvedSnapshotMaterializationInput(
            inputs=changed,
            build_key=materialization.build_key,
            endpoint_records=materialization.endpoint_records,
        )
