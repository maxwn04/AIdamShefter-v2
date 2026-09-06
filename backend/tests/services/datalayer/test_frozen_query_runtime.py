from __future__ import annotations

from collections.abc import Iterator
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import UUID

import pytest

from backend.services.datalayer import (
    AmbiguousRosterIdentity,
    FrozenLeagueData,
    FrozenSnapshotInvalid,
    ReadyDataSnapshot,
    ReadySnapshotSeason,
    ResolvedRosterIdentity,
    RosterIdentityNotFound,
    SnapshotSeason,
    SnapshotRequest,
    VerifiedLocalArtifact,
)
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
from backend.services.datalayer.snapshot_sqlite import SQLiteSnapshotMaterializer
from backend.services.datalayer.sleeper.endpoints import (
    normalize_league,
    normalize_league_rosters,
    normalize_league_users,
    normalize_losers_bracket,
    normalize_matchups,
    normalize_nfl_state,
    normalize_player_catalog,
    normalize_traded_picks,
    normalize_transactions,
    normalize_winners_bracket,
)
from backend.services.datalayer.sleeper.scope import EndpointKind
from backend.tests.services.datalayer.test_snapshot_source_projection import (
    FIXTURES,
    _context,
    _fixture_input,
    _roster_identities,
)
from backend.tests.services.datalayer.test_snapshot_sqlite_v3 import (
    _materialization as _v3_materialization,
)


GOLDEN = (
    Path(__file__).parents[4]
    / "datalayer"
    / "tests"
    / "characterization"
    / "golden"
    / "legacy_query_outputs.json"
)


@pytest.fixture
def ready_snapshot(tmp_path: Path) -> Iterator[ReadyDataSnapshot]:
    materialization = _fixture_input()
    artifact = SQLiteSnapshotMaterializer(tmp_path / "staging").materialize(
        materialization
    )
    ready = _ready(materialization, artifact)
    try:
        yield ready
    finally:
        artifact.path.unlink(missing_ok=True)


@pytest.fixture
def v3_ready_snapshot(tmp_path: Path) -> Iterator[ReadyDataSnapshot]:
    materialization = _v3_materialization()
    artifact = SQLiteSnapshotMaterializer(tmp_path / "staging-v3").materialize(
        materialization
    )
    primary = next(
        season
        for season in materialization.inputs.seasons
        if season.role.value == "primary"
    )
    sha256 = artifact.sha256
    ready = ReadyDataSnapshot(
        id=UUID(int=100),
        competition_id=primary.identity.competition_id,
        primary_competition_season_id=primary.identity.competition_season_id,
        through_week=primary.through_week,
        as_of_date=materialization.inputs.primary.as_of_date,
        build_key=materialization.build_key,
        snapshot_projection_version="3",
        artifact=VerifiedLocalArtifact(
            path=artifact.path.resolve(),
            storage_key=f"snapshots/sha256/{sha256[:2]}/{sha256}.sqlite",
            sha256=sha256,
            byte_length=artifact.byte_length,
        ),
        completeness_warnings=artifact.completeness_warnings,
        input_revision=materialization.inputs.input_revision,
        included_seasons=tuple(
            ReadySnapshotSeason(
                competition_season_id=season.identity.competition_season_id,
                sleeper_league_id=season.identity.sleeper_league_id,
                season_year=season.identity.season_year,
                sequence_number=season.identity.sequence_number,
                role=season.role.value,
                through_week=season.through_week,
            )
            for season in materialization.inputs.seasons
        ),
    )
    try:
        yield ready
    finally:
        artifact.path.unlink(missing_ok=True)


def test_v3_catalog_primary_defaults_and_historical_reads_are_isolated(
    v3_ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(v3_ready_snapshot) as data:
        seasons = data.available_seasons()
        assert all(isinstance(season, SnapshotSeason) for season in seasons)
        assert [season.season_year for season in seasons] == [2025, 2026]
        assert [season.role for season in seasons] == ["history", "primary"]
        assert data.completeness_warnings() == v3_ready_snapshot.completeness_warnings
        assert [season.through_week for season in seasons] == [18, 3]

        assert data.get_league_snapshot(week=1) == data.get_league_snapshot(
            week=1,
            season=2026,
        )
        history = data.get_league_snapshot(week=1, season=2025)
        primary = data.get_league_snapshot(week=1, season=2026)
        assert history["league"]["name"] == "League 2025"
        assert primary["league"]["name"] == "League 2026"

        history_transactions = data.get_transactions(1, 1, season=2025)
        primary_transactions = data.get_transactions(1, 1, season=2026)
        assert len(history_transactions) == len(primary_transactions) == 1
        assert history_transactions == primary_transactions
        assert sum(
            len(detail["assets_received"]) + len(detail["assets_sent"])
            for detail in history_transactions[0]["details"]
        ) == 2

        history_identity = data.resolve_roster_identity("1", season=2025)
        primary_identity = data.resolve_roster_identity("1", season=2026)
        assert isinstance(history_identity, ResolvedRosterIdentity)
        assert isinstance(primary_identity, ResolvedRosterIdentity)
        assert history_identity.identity.competition_season_id != (
            primary_identity.identity.competition_season_id
        )
        assert data.get_roster_identity_by_canonical_id(
            franchise_id=history_identity.identity.franchise_id,
            season=2025,
        ) == history_identity.identity
        assert data.get_roster_identity_by_canonical_id(
            season_roster_id=primary_identity.identity.season_roster_id,
        ) == primary_identity.identity


def test_every_season_scoped_v3_call_defaults_to_primary(
    v3_ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(v3_ready_snapshot) as data:
        calls = (
            lambda season=None: data.get_league_snapshot(1, season=season),
            lambda season=None: data.get_bench_analysis("1", 1, season=season),
            lambda season=None: data.get_standings(1, season=season),
            lambda season=None: data.get_team_dossier("1", 1, season=season),
            lambda season=None: data.get_team_schedule("1", season=season),
            lambda season=None: data.get_week_games(1, season=season),
            lambda season=None: data.get_week_games_with_players(1, season=season),
            lambda season=None: data.get_team_game("1", 1, season=season),
            lambda season=None: data.get_team_game_with_players(
                "1", 1, season=season
            ),
            lambda season=None: data.get_week_player_leaderboard(
                1, 3, season=season
            ),
            lambda season=None: data.get_season_leaders(
                season=season, week_from=1, week_to=1, limit=3
            ),
            lambda season=None: data.get_transactions(1, 1, season=season),
            lambda season=None: data.get_team_transactions(
                "1", 1, 1, season=season
            ),
            lambda season=None: data.get_week_transactions(1, season=season),
            lambda season=None: data.get_team_week_transactions(
                "1", 1, season=season
            ),
            lambda season=None: data.get_player_weekly_log(
                "Player One", 1, 1, season=season
            ),
            lambda season=None: data.get_roster_at_cutoff("1", season=season),
            lambda season=None: data.resolve_roster_identity("1", season=season),
            lambda season=None: data.get_roster_snapshot("1", 1, season=season),
            lambda season=None: data.get_playoff_bracket(season=season),
            lambda season=None: data.get_team_playoff_path("1", season=season),
        )
        for call in calls:
            assert call() == call(2026)


def test_v3_season_and_cutoff_validation_are_catalog_scoped(
    v3_ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(v3_ready_snapshot) as data:
        assert data.get_week_games(week=18, season=2025) == []
        with pytest.raises(ValueError, match="1 through 3"):
            data.get_week_games(week=4, season=2026)
        with pytest.raises(ValueError, match="2025, 2026"):
            data.get_week_games(season=2024)
        with pytest.raises(ValueError, match="integer"):
            data.get_week_games(season=True)  # type: ignore[arg-type]


def test_v3_ready_membership_and_revision_mismatches_fail_closed(
    v3_ready_snapshot: ReadyDataSnapshot,
) -> None:
    with pytest.raises(FrozenSnapshotInvalid, match="input revision"):
        FrozenLeagueData.open(
            v3_ready_snapshot.model_copy(update={"input_revision": "f" * 64})
        )
    with pytest.raises(FrozenSnapshotInvalid, match="season membership"):
        FrozenLeagueData.open(
            v3_ready_snapshot.model_copy(
                update={"included_seasons": v3_ready_snapshot.included_seasons[1:]}
            )
        )


def test_v3_malformed_catalog_fails_closed(
    v3_ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    changed = _mutated_copy(
        v3_ready_snapshot.artifact.path,
        tmp_path / "wrong-v3-cutoff.sqlite",
        "UPDATE snapshot_seasons SET through_week = 17 WHERE role = 'history'",
    )
    with pytest.raises(FrozenSnapshotInvalid, match="historical cutoff"):
        FrozenLeagueData.open(
            v3_ready_snapshot.model_copy(update={"artifact": changed})
        )


def test_full_regular_query_contract_matches_legacy_golden(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    with FrozenLeagueData.open(ready_snapshot) as data:
        seasons = data.available_seasons()
        assert len(seasons) == 1
        assert seasons[0].role == "primary"
        assert seasons[0].through_week == ready_snapshot.through_week
        actual = {
            "league_snapshot": data.get_league_snapshot(week=2),
            "bench_analysis_league": data.get_bench_analysis(week=2),
            "bench_analysis_team": data.get_bench_analysis("Alpha", week=2),
            "standings": data.get_standings(week=2),
            "team_dossier_by_name": data.get_team_dossier("alpha", week=2),
            "team_dossier_by_manager": data.get_team_dossier("Alice", week=2),
            "team_dossier_by_id": data.get_team_dossier("1", week=2),
            "team_dossier_not_found": data.get_team_dossier("missing", week=2),
            "team_schedule": data.get_team_schedule("Alpha"),
            "week_games": data.get_week_games(week=2),
            "week_games_default": data.get_week_games(),
            "week_games_with_players": data.get_week_games_with_players(week=2),
            "team_game": data.get_team_game("Alpha", week=2),
            "team_game_with_players": data.get_team_game_with_players(
                "Alpha", week=2
            ),
            "week_player_leaderboard": data.get_week_player_leaderboard(
                week=2, limit=3
            ),
            "season_leaders": data.get_season_leaders(limit=3),
            "season_leaders_filtered": data.get_season_leaders(
                week_from=2,
                week_to=2,
                position="QB",
                roster_key="Alice",
                role="starter",
                sort_by="avg",
                limit=3,
            ),
            "transactions": data.get_transactions(1, 2),
            "team_transactions": data.get_team_transactions("Alpha", 1, 2),
            "week_transactions": data.get_week_transactions(week=2),
            "team_week_transactions": data.get_team_week_transactions(
                "Alpha", week_from=2
            ),
            "player_summary_by_name": data.get_player_summary("player one"),
            "player_summary_by_id": data.get_player_summary("p1"),
            "player_summary_not_found": data.get_player_summary("missing"),
            "player_weekly_log": data.get_player_weekly_log("Player One"),
            "player_weekly_log_filtered": data.get_player_weekly_log(
                "p1", week_from=2, week_to=2
            ),
            "roster_current_by_name": data.get_roster_at_cutoff("Alpha"),
            "roster_current_by_manager": data.get_roster_at_cutoff("Alice"),
            "roster_snapshot": data.get_roster_snapshot("1", week=1),
            "sql_named_params_and_limit": data.run_sql(
                "SELECT roster_id, points FROM matchups "
                "WHERE week = :week ORDER BY roster_id",
                {"week": 2},
                limit=1,
            ),
        }

    regular_keys = set(actual)
    expected = {key: expected[key] for key in regular_keys}
    # Frozen scorecards retain source matchup identity and league scoring format.
    expected["league_snapshot"]["league"]["league_average_match"] = False
    for row in expected["standings"]["standings"]:
        row["streak_basis"] = "head_to_head"
    for key in ("week_games", "week_games_default", "week_games_with_players"):
        for game in expected[key]:
            game["sleeper_matchup_number"] = 1
    for game in expected["league_snapshot"]["games"]:
        game["sleeper_matchup_number"] = 1
    for key in ("team_game", "team_game_with_players"):
        expected[key]["game"]["sleeper_matchup_number"] = 1
    normalized_actual = _json_round_trip(_without_volatile_player_state(actual))
    normalized_expected = _without_volatile_player_state(expected)
    # Additive relationship/period metadata has dedicated source-boundary tests;
    # compare the retained legacy shape without editing its frozen golden file.
    def legacy_shape(value):
        if isinstance(value, list):
            return [legacy_shape(item) for item in value]
        if not isinstance(value, dict):
            return value
        omitted = {"competition_phase", "standings_through_week", "standings_basis", "record_unit"}
        if "as_of_week" in value:
            omitted.add("streak_basis")
        if "asset_type" in value:
            omitted.update({"from_team", "to_team", "from_roster_key", "to_roster_key", "movement"})
        if "assets_sent" in value:
            omitted.add("roster_key")
        return {key: legacy_shape(item) for key, item in value.items() if key not in omitted}

    normalized_actual = legacy_shape(normalized_actual)
    assert _contract_shape(normalized_actual) == _contract_shape(normalized_expected)
    stable_keys = {
        "bench_analysis_league",
        "bench_analysis_team",
        "team_schedule",
        "week_games",
        "week_games_default",
        "week_games_with_players",
        "team_game",
        "team_game_with_players",
        "week_player_leaderboard",
        "season_leaders",
        "season_leaders_filtered",
        "player_weekly_log",
        "player_weekly_log_filtered",
        "roster_current_by_name",
        "roster_current_by_manager",
        "roster_snapshot",
        "sql_named_params_and_limit",
    }
    assert {key: normalized_actual[key] for key in stable_keys} == {
        key: normalized_expected[key] for key in stable_keys
    }


def test_playoff_query_contract_matches_legacy_golden(tmp_path: Path) -> None:
    materialization = _fixture_input_for_week(18)
    artifact = SQLiteSnapshotMaterializer(tmp_path / "staging").materialize(
        materialization
    )
    try:
        with FrozenLeagueData.open(_ready(materialization, artifact)) as data:
            actual = {
                "playoff_brackets": data.get_playoff_bracket(),
                "playoff_winners": data.get_playoff_bracket("winners"),
                "team_playoff_path": data.get_team_playoff_path("Alice"),
            }
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        # The frozen query now retains each matchup's bracket perspective.
        for matchup in expected["team_playoff_path"]["matchups"]:
            matchup["bracket_type"] = expected["team_playoff_path"]["bracket_type"]
        for key in ("playoff_brackets", "playoff_winners"):
            for bracket_type, bracket in expected[key]["brackets"].items():
                bracket["bracket_type"] = bracket_type
                for matchups in bracket["rounds"].values():
                    for matchup in matchups:
                        matchup["bracket_type"] = bracket_type
                for placement in bracket["placements"]:
                    placement["bracket_type"] = bracket_type
        assert _json_round_trip(actual) == {key: expected[key] for key in actual}
    finally:
        artifact.path.unlink(missing_ok=True)


def test_runtime_defaults_to_cutoff_and_rejects_out_of_domain_weeks(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        assert data.get_week_games() == data.get_week_games(2)
        for invalid in (0, 3, True, "2"):
            with pytest.raises(ValueError, match="week"):
                data.get_week_games(invalid)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="week_from"):
            data.get_transactions(2, 1)


def test_curated_queries_exclude_decoy_seasons(
    ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    decoy = _mutated_copy_many(
        ready_snapshot.artifact.path,
        tmp_path / "decoy-season.sqlite",
        (
            (
                "INSERT INTO games VALUES "
                "('123', '2023', 2, 99, 1, 2, 999, 0, 1, 0)",
                (),
            ),
            (
                "INSERT INTO player_performances VALUES "
                "('123', '2023', 2, 'p1', 1, 99, 999, 'starter')",
                (),
            ),
            (
                "INSERT INTO transactions "
                "(league_id, season, week, transaction_id, type) "
                "VALUES ('123', '2023', 2, 'decoy', 'decoy')",
                (),
            ),
            (
                "INSERT INTO playoff_matchups "
                "(league_id, season, bracket_type, node_key, round, matchup_id) "
                "VALUES ('123', '2023', 'winners', 'decoy', 1, 99)",
                (),
            ),
        ),
    )
    with FrozenLeagueData.open(
        ready_snapshot.model_copy(update={"artifact": decoy})
    ) as data:
        assert len(data.get_week_games(2)) == 1
        assert data.get_season_leaders(limit=1)[0]["total_points"] == 130.5
        assert all(item["type"] != "decoy" for item in data.get_transactions(1, 2))
        assert data.get_playoff_bracket() == {"found": False}


def test_name_resolvers_preserve_ambiguity_results(
    ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    ambiguous = _mutated_copy_many(
        ready_snapshot.artifact.path,
        tmp_path / "ambiguous.sqlite",
        (
            (
                "INSERT INTO team_profiles "
                "(league_id, roster_id, team_name, manager_name) "
                "VALUES ('123', 3, 'Alpha', 'Another Manager')",
                (),
            ),
            (
                "INSERT INTO players (player_id, full_name, position) "
                "VALUES ('duplicate-p1', 'Player One', 'QB')",
                (),
            ),
        ),
    )
    with FrozenLeagueData.open(
        ready_snapshot.model_copy(update={"artifact": ambiguous})
    ) as data:
        team = data.get_team_dossier("Alpha")
        player = data.get_player_summary("Player One")

    assert team["found"] is False
    assert len(team["matches"]) == 2
    assert player["found"] is False
    assert len(player["matches"]) == 2


def test_typed_roster_identity_resolution_uses_only_frozen_snapshot(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        by_id = data.resolve_roster_identity(1)
        by_team = data.resolve_roster_identity(" alpha ")
        by_manager = data.resolve_roster_identity("ALICE")
        by_franchise = data.get_roster_identity_by_canonical_id(
            franchise_id=UUID("00000000-0000-0000-0000-0000000000c9")
        )
        by_season_roster = data.get_roster_identity_by_canonical_id(
            season_roster_id=UUID("00000000-0000-0000-0000-000000000065")
        )
        missing_canonical = data.get_roster_identity_by_canonical_id(
            franchise_id=UUID(int=999)
        )
        missing = data.resolve_roster_identity("missing")
        invalid = data.resolve_roster_identity("01")

    assert isinstance(by_id, ResolvedRosterIdentity)
    assert by_team == by_id.model_copy(update={"roster_key": "alpha"})
    assert by_manager == by_id.model_copy(update={"roster_key": "ALICE"})
    assert by_franchise == by_id.identity
    assert by_season_roster == by_id.identity
    assert missing_canonical is None
    assert by_id.identity.model_dump(mode="json") == {
        "competition_id": "22222222-2222-2222-2222-222222222222",
        "competition_season_id": "11111111-1111-1111-1111-111111111111",
        "season_roster_id": "00000000-0000-0000-0000-000000000065",
        "franchise_id": "00000000-0000-0000-0000-0000000000c9",
        "sleeper_roster_id": "1",
        "team_name": "Alpha",
        "manager_name": "Alice",
    }
    assert missing == RosterIdentityNotFound(roster_key="missing")
    assert invalid == RosterIdentityNotFound(roster_key="01")


def test_typed_roster_identity_resolution_preserves_name_ambiguity(
    ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    ambiguous = _mutated_copy(
        ready_snapshot.artifact.path,
        tmp_path / "ambiguous-identity.sqlite",
        "UPDATE team_profiles SET team_name = 'Alpha' WHERE roster_id = 2",
    )
    with FrozenLeagueData.open(
        ready_snapshot.model_copy(update={"artifact": ambiguous})
    ) as data:
        resolution = data.resolve_roster_identity("Alpha")

    assert isinstance(resolution, AmbiguousRosterIdentity)
    assert [match.sleeper_roster_id for match in resolution.matches] == ["1", "2"]


@pytest.mark.parametrize(
    ("statement", "message"),
    [
        (
            "UPDATE roster_identities SET season_roster_id = 'not-a-uuid' "
            "WHERE roster_id = 1",
            "season_roster_id",
        ),
        (
            "UPDATE roster_identities SET competition_id = "
            "'33333333-3333-3333-3333-333333333333' WHERE roster_id = 1",
            "scope",
        ),
        (
            "DELETE FROM roster_identities WHERE roster_id = 1",
            "match snapshot rosters",
        ),
    ],
)
def test_invalid_frozen_roster_identity_rows_fail_closed(
    ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
    statement: str,
    message: str,
) -> None:
    changed = _mutated_copy(
        ready_snapshot.artifact.path,
        tmp_path / f"invalid-identity-{message}.sqlite",
        statement,
    )

    with pytest.raises(FrozenSnapshotInvalid, match=message):
        FrozenLeagueData.open(
            ready_snapshot.model_copy(update={"artifact": changed})
        )


def test_context_exit_closes_runtime_deterministically(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    data = FrozenLeagueData.open(ready_snapshot)
    with data:
        assert data.get_league_snapshot()["found"] is True

    with pytest.raises(RuntimeError, match="closed"):
        data.get_league_snapshot()
    with pytest.raises(RuntimeError, match="closed"):
        data.resolve_roster_identity("Alpha")


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("build_key", "b" * 64),
        ("competition_id", "33333333-3333-3333-3333-333333333333"),
        ("primary_competition_season_id", "44444444-4444-4444-4444-444444444444"),
        ("through_week", 1),
        ("as_of_date", "2024-09-18"),
        ("snapshot_projection_version", "1"),
    ],
)
def test_internal_identity_mismatches_fail_closed(
    ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
    column: str,
    replacement: object,
) -> None:
    changed = _mutated_copy(
        ready_snapshot.artifact.path,
        tmp_path / f"wrong-{column}.sqlite",
        f'UPDATE snapshot_metadata SET "{column}" = ?',
        (replacement,),
    )
    with pytest.raises(FrozenSnapshotInvalid, match="metadata"):
        FrozenLeagueData.open(ready_snapshot.model_copy(update={"artifact": changed}))


def test_manifest_warning_and_table_corruption_fail_closed(
    ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    noncanonical = _mutated_copy(
        ready_snapshot.artifact.path,
        tmp_path / "noncanonical.sqlite",
        "UPDATE snapshot_metadata SET selected_requests_json = '[ ]'",
    )
    with pytest.raises(FrozenSnapshotInvalid, match="manifest"):
        FrozenLeagueData.open(
            ready_snapshot.model_copy(update={"artifact": noncanonical})
        )

    missing_table = _mutated_copy(
        ready_snapshot.artifact.path,
        tmp_path / "missing-table.sqlite",
        "DROP TABLE games",
    )
    with pytest.raises(FrozenSnapshotInvalid, match="table set"):
        FrozenLeagueData.open(
            ready_snapshot.model_copy(update={"artifact": missing_table})
        )

    with pytest.raises(FrozenSnapshotInvalid, match="warnings"):
        FrozenLeagueData.open(
            ready_snapshot.model_copy(update={"completeness_warnings": ()})
        )


def test_unavailable_and_unsupported_snapshots_fail_before_querying(
    ready_snapshot: ReadyDataSnapshot,
    tmp_path: Path,
) -> None:
    missing = ready_snapshot.artifact.__class__(
        path=(tmp_path / "missing.sqlite").resolve(),
        storage_key=ready_snapshot.artifact.storage_key,
        sha256=ready_snapshot.artifact.sha256,
        byte_length=ready_snapshot.artifact.byte_length,
    )
    with pytest.raises(FrozenSnapshotInvalid, match="unavailable"):
        FrozenLeagueData.open(ready_snapshot.model_copy(update={"artifact": missing}))
    with pytest.raises(FrozenSnapshotInvalid, match="unsupported"):
        FrozenLeagueData.open(
            ready_snapshot.model_copy(update={"snapshot_projection_version": "1"})
        )


def test_constructor_and_public_surface_exclude_legacy_lifecycle(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with pytest.raises(TypeError, match="open"):
        FrozenLeagueData(object())
    with FrozenLeagueData.open(ready_snapshot) as data:
        assert not hasattr(data, "load")
        assert not hasattr(data, "save_to_file")
        assert not hasattr(data, "get_roster_current")


def _ready(materialization, artifact) -> ReadyDataSnapshot:
    sha256 = artifact.sha256
    return ReadyDataSnapshot(
        id=UUID(int=99),
        competition_id=materialization.planning_context.competition_id,
        primary_competition_season_id=(
            materialization.planning_context.competition_season_id
        ),
        through_week=materialization.request.through_week,
        as_of_date=materialization.request.as_of_date,
        build_key=materialization.build_key,
        snapshot_projection_version=materialization.snapshot_projection_version,
        artifact=VerifiedLocalArtifact(
            path=artifact.path.resolve(),
            storage_key=f"snapshots/sha256/{sha256[:2]}/{sha256}.sqlite",
            sha256=sha256,
            byte_length=artifact.byte_length,
        ),
        completeness_warnings=artifact.completeness_warnings,
    )


def _fixture_input_for_week(through_week: int) -> SnapshotMaterializationInput:
    request = SnapshotRequest(
        competition_season_id=_fixture_input().request.competition_season_id,
        through_week=through_week,
        as_of_date=date(2024, 12, 31),
    )
    context = _context()
    requirements = plan_snapshot_requirements(request, context)
    normalizers = {
        EndpointKind.LEAGUE: normalize_league,
        EndpointKind.LEAGUE_USERS: normalize_league_users,
        EndpointKind.NFL_STATE: normalize_nfl_state,
        EndpointKind.PLAYER_CATALOG: normalize_player_catalog,
        EndpointKind.LEAGUE_ROSTERS: normalize_league_rosters,
        EndpointKind.TRADED_PICKS: normalize_traded_picks,
        EndpointKind.MATCHUPS: normalize_matchups,
        EndpointKind.TRANSACTIONS: normalize_transactions,
        EndpointKind.WINNERS_BRACKET: normalize_winners_bracket,
        EndpointKind.LOSERS_BRACKET: normalize_losers_bracket,
    }
    fixed_files = {
        EndpointKind.LEAGUE: "league.json",
        EndpointKind.LEAGUE_USERS: "users.json",
        EndpointKind.NFL_STATE: "state.json",
        EndpointKind.PLAYER_CATALOG: "players.json",
        EndpointKind.LEAGUE_ROSTERS: "rosters.json",
        EndpointKind.TRADED_PICKS: "traded_picks.json",
        EndpointKind.WINNERS_BRACKET: "winners_bracket.json",
        EndpointKind.LOSERS_BRACKET: "losers_bracket.json",
    }
    manifest = []
    endpoints = []
    for index, requirement in enumerate(requirements.entries, start=1):
        endpoint = requirement.request
        filename = fixed_files.get(endpoint.endpoint_kind)
        if endpoint.endpoint_kind is EndpointKind.MATCHUPS and endpoint.week <= 2:
            filename = f"matchups_week{endpoint.week}.json"
        elif endpoint.endpoint_kind is EndpointKind.TRANSACTIONS and endpoint.week <= 2:
            filename = f"transactions_week{endpoint.week}.json"
        payload = parse_json_bytes((FIXTURES / filename).read_bytes()) if filename else []
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
        build_key="c" * 64,
        snapshot_projection_version="2",
        manifest=SelectedRequestManifest(entries=tuple(manifest)),
        endpoint_records=tuple(endpoints),
        roster_identities=_roster_identities(),
    )


def _without_volatile_player_state(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                None
                if key in {"nfl_team", "status", "injury_status"}
                else _without_volatile_player_state(item)
            )
            for key, item in value.items()
            if key not in {"age", "years_exp"}
        }
    if isinstance(value, list):
        return [_without_volatile_player_state(item) for item in value]
    return value


def _contract_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _contract_shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        shapes = {_stable_json(_contract_shape(item)) for item in value}
        return [json.loads(item) for item in sorted(shapes)]
    if value is None:
        return None
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _json_round_trip(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _mutated_copy(
    source: Path,
    target: Path,
    statement: str,
    params: tuple[object, ...] = (),
) -> VerifiedLocalArtifact:
    target.write_bytes(source.read_bytes())
    connection = sqlite3.connect(target)
    try:
        connection.execute(statement, params)
        connection.commit()
    finally:
        connection.close()
    content = target.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    return VerifiedLocalArtifact(
        path=target.resolve(),
        storage_key=f"snapshots/sha256/{sha256[:2]}/{sha256}.sqlite",
        sha256=sha256,
        byte_length=len(content),
    )


def _mutated_copy_many(
    source: Path,
    target: Path,
    statements: tuple[tuple[str, tuple[object, ...]], ...],
) -> VerifiedLocalArtifact:
    target.write_bytes(source.read_bytes())
    connection = sqlite3.connect(target)
    try:
        for statement, params in statements:
            connection.execute(statement, params)
        connection.commit()
    finally:
        connection.close()
    content = target.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    return VerifiedLocalArtifact(
        path=target.resolve(),
        storage_key=f"snapshots/sha256/{sha256[:2]}/{sha256}.sqlite",
        sha256=sha256,
        byte_length=len(content),
    )
