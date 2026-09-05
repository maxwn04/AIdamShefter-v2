from datetime import date
from pathlib import Path
from uuid import UUID

import pytest

from backend.resources.sleeper_data import SeasonRosterIdentity, SnapshotPlanningContext
from backend.services.datalayer import SnapshotRequest
from backend.services.datalayer.canonical_json import parse_json_bytes
from backend.services.datalayer.snapshot_selection import (
    SelectedRequestManifest,
    SelectedRequestManifestEntry,
    plan_snapshot_requirements,
)
from backend.services.datalayer.snapshot_service import (
    SnapshotEndpointRecords,
    SnapshotMaterializationInput,
)
from backend.services.datalayer.snapshot_sqlite import project_source_records
from backend.services.datalayer.sleeper.endpoints import (
    LeagueRostersEndpointRecords,
    RosterRecord,
    normalize_league,
    normalize_league_rosters,
    normalize_league_users,
    normalize_matchups,
    normalize_nfl_state,
    normalize_player_catalog,
    normalize_traded_picks,
    normalize_transactions,
)
from backend.services.datalayer.sleeper.scope import EndpointKind


SEASON_ID = UUID("11111111-1111-1111-1111-111111111111")
COMPETITION_ID = UUID("22222222-2222-2222-2222-222222222222")
FIXTURES = Path(__file__).parents[4] / "datalayer" / "tests" / "fixtures" / "sleeper"


def _roster_identities() -> tuple[SeasonRosterIdentity, ...]:
    return tuple(
        SeasonRosterIdentity(
            competition_id=COMPETITION_ID,
            competition_season_id=SEASON_ID,
            season_roster_id=UUID(int=100 + roster_id),
            franchise_id=UUID(int=200 + roster_id),
            sleeper_roster_id=str(roster_id),
        )
        for roster_id in (1, 2)
    )


def _context(*, playoff_start_week: int | None = 15) -> SnapshotPlanningContext:
    return SnapshotPlanningContext(
        competition_id=COMPETITION_ID,
        competition_season_id=SEASON_ID,
        sleeper_league_id="123",
        season_year=2024,
        playoff_start_week=playoff_start_week,
        playoff_team_count=4,
        draft_rounds=2,
        league_average_match=0,
    )


def _fixture_input() -> SnapshotMaterializationInput:
    request = SnapshotRequest(
        competition_season_id=SEASON_ID,
        through_week=2,
        as_of_date=date(2024, 9, 17),
    )
    context = _context()
    requirements = plan_snapshot_requirements(request, context)
    files = {
        EndpointKind.LEAGUE: "league.json",
        EndpointKind.LEAGUE_USERS: "users.json",
        EndpointKind.NFL_STATE: "state.json",
        EndpointKind.PLAYER_CATALOG: "players.json",
        EndpointKind.LEAGUE_ROSTERS: "rosters.json",
        EndpointKind.TRADED_PICKS: "traded_picks.json",
        EndpointKind.MATCHUPS: None,
        EndpointKind.TRANSACTIONS: None,
    }
    normalizers = {
        EndpointKind.LEAGUE: normalize_league,
        EndpointKind.LEAGUE_USERS: normalize_league_users,
        EndpointKind.NFL_STATE: normalize_nfl_state,
        EndpointKind.PLAYER_CATALOG: normalize_player_catalog,
        EndpointKind.LEAGUE_ROSTERS: normalize_league_rosters,
        EndpointKind.TRADED_PICKS: normalize_traded_picks,
        EndpointKind.MATCHUPS: normalize_matchups,
        EndpointKind.TRANSACTIONS: normalize_transactions,
    }
    manifest = []
    endpoints = []
    for index, requirement in enumerate(requirements.entries, start=1):
        endpoint = requirement.request
        filename = files[endpoint.endpoint_kind]
        if endpoint.endpoint_kind is EndpointKind.MATCHUPS:
            filename = f"matchups_week{endpoint.week}.json"
        elif endpoint.endpoint_kind is EndpointKind.TRANSACTIONS:
            filename = f"transactions_week{endpoint.week}.json"
        payload = parse_json_bytes((FIXTURES / filename).read_bytes())
        if endpoint.endpoint_kind is EndpointKind.LEAGUE:
            # The frozen score fixtures are final through week two.
            payload["settings"]["last_scored_leg"] = 2
        entry = SelectedRequestManifestEntry(
            request_id=UUID(int=index),
            endpoint_kind=endpoint.endpoint_kind,
            scope_key=endpoint.scope_key,
            selection_role=requirement.selection_role,
            response_sha256=f"{index:064x}",
        )
        manifest.append(entry)
        endpoints.append(
            SnapshotEndpointRecords(
                manifest_entry=entry,
                records=normalizers[endpoint.endpoint_kind](payload, endpoint),
            )
        )
    return SnapshotMaterializationInput(
        request=request,
        planning_context=context,
        build_key="a" * 64,
        snapshot_projection_version="2",
        manifest=SelectedRequestManifest(entries=tuple(manifest)),
        endpoint_records=tuple(endpoints),
        roster_identities=_roster_identities(),
    )


def test_projects_all_source_families_with_strict_current_state_policy() -> None:
    projection = project_source_records(_fixture_input())

    assert len(projection.rows_for("leagues")) == 1
    assert len(projection.rows_for("users")) == 2
    assert len(projection.rows_for("rosters")) == 2
    assert len(projection.rows_for("matchups")) == 4
    assert len(projection.rows_for("transactions")) == 2
    assert projection.rows_for("players")[0]["nfl_team"] is None
    assert projection.rows_for("players")[0]["status"] is None
    assert projection.rows_for("players")[0]["metadata_json"] is None
    assert all(row["settings_json"] is None for row in projection.rows_for("rosters"))
    assert {warning.code for warning in projection.warnings} == {
        "snapshot.player_state_omitted",
        "snapshot.roster_reconstruction_limited",
    }


def test_cutoff_roster_membership_comes_only_from_last_week_matchups() -> None:
    projection = project_source_records(_fixture_input())

    members = projection.rows_for("roster_players")
    week_two = projection.rows_for("player_performances")
    week_two = tuple(row for row in week_two if row["week"] == 2)
    assert {(row["roster_id"], row["player_id"], row["role"]) for row in members} == {
        (row["roster_id"], row["player_id"], row["role"]) for row in week_two
    }
    assert {row["role"] for row in members} <= {"starter", "bench"}


def test_transaction_assets_expand_to_legacy_direction_rows() -> None:
    moves = project_source_records(_fixture_input()).rows_for("transaction_moves")

    assert {(row["asset_type"], row["direction"]) for row in moves} == {
        ("player", "add"),
        ("player", "drop"),
        ("pick", "pick_in"),
        ("pick", "pick_out"),
    }
    pick_rows = [row for row in moves if row["asset_type"] == "pick"]
    assert {row["roster_id"] for row in pick_rows} == {1, 2}
    assert {row["pick_id"] for row in pick_rows} == {"pick1"}


def test_every_source_row_has_manifest_provenance() -> None:
    materialization = _fixture_input()
    projection = project_source_records(materialization)
    selected = {entry.scope_key for entry in materialization.manifest.entries}

    assert len(projection.provenance) == sum(map(len, projection.rows.values()))
    assert {entry.scope_key for entry in projection.provenance} <= selected


def test_non_numeric_roster_ids_fail_closed() -> None:
    materialization = _fixture_input()
    endpoints = list(materialization.endpoint_records)
    index = next(
        i
        for i, endpoint in enumerate(endpoints)
        if isinstance(endpoint.records, LeagueRostersEndpointRecords)
    )
    original = endpoints[index]
    records = original.records.model_copy(
        update={
            "rosters": (
                RosterRecord(
                    sleeper_roster_id="not-numeric",
                    settings={},
                    metadata={},
                    wins=0,
                    losses=0,
                    ties=0,
                    points_for=0,
                    points_against=0,
                ),
            )
        }
    )
    endpoints[index] = original.model_copy(update={"records": records})

    with pytest.raises(ValueError, match="numeric roster IDs"):
        project_source_records(
            materialization.model_copy(update={"endpoint_records": tuple(endpoints)})
        )


def test_duplicate_stable_roster_identities_are_rejected() -> None:
    materialization = _fixture_input()
    duplicate = materialization.roster_identities[1].model_copy(
        update={
            "season_roster_id": materialization.roster_identities[0].season_roster_id
        }
    )
    payload = materialization.model_dump()
    payload["roster_identities"] = (materialization.roster_identities[0], duplicate)

    with pytest.raises(ValueError, match="duplicate season-roster IDs"):
        SnapshotMaterializationInput.model_validate(payload)
