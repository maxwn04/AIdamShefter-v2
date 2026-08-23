from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.services.datalayer.snapshot_sqlite import get_snapshot_schema
from datalayer.sleeper_data.schema import metadata as legacy_metadata


EXPECTED_TABLES = {
    "leagues",
    "season_context",
    "users",
    "rosters",
    "roster_identities",
    "roster_players",
    "team_profiles",
    "draft_picks",
    "players",
    "matchups",
    "player_performances",
    "games",
    "standings",
    "transactions",
    "transaction_moves",
    "playoff_matchups",
    "snapshot_metadata",
}


def test_v2_schema_is_snapshot_only_and_complete() -> None:
    schema = get_snapshot_schema("2")

    assert set(schema.tables) == EXPECTED_TABLES
    assert set(schema.table_order) == EXPECTED_TABLES
    assert schema.metadata is not legacy_metadata
    assert "snapshot_metadata" not in legacy_metadata.tables


def test_metadata_omits_volatile_snapshot_instance_fields() -> None:
    columns = set(get_snapshot_schema("2").tables["snapshot_metadata"].c.keys())

    assert {
        "build_key",
        "selected_requests_json",
        "completeness_warnings_json",
    } <= columns
    assert not {"snapshot_id", "created_at", "completed_at", "code_version"} & columns


def test_roster_identity_table_has_stable_one_to_one_keys() -> None:
    table = get_snapshot_schema("2").tables["roster_identities"]

    assert [column.name for column in table.primary_key.columns] == [
        "league_id",
        "roster_id",
    ]
    assert table.c.season_roster_id.unique
    assert table.c.franchise_id.unique


def test_playoff_nodes_have_stable_key_and_legacy_matchup_seam() -> None:
    table = get_snapshot_schema("2").tables["playoff_matchups"]

    assert [column.name for column in table.primary_key.columns] == [
        "league_id",
        "season",
        "bracket_type",
        "node_key",
    ]
    assert table.c.matchup_id.nullable


def test_real_sqlite_ddl_enforces_singleton_metadata(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.sqlite'}")
    schema = get_snapshot_schema("2")
    schema.metadata.create_all(engine)
    try:
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
        with engine.begin() as connection:
            connection.execute(
                schema.tables["snapshot_metadata"].insert(),
                {
                    "singleton_id": 1,
                    "build_key": "a" * 64,
                    "competition_id": "11111111-1111-1111-1111-111111111111",
                    "primary_competition_season_id": (
                        "22222222-2222-2222-2222-222222222222"
                    ),
                    "sleeper_league_id": "123",
                    "season_year": 2026,
                    "through_week": 8,
                    "as_of_date": "2026-10-27",
                    "snapshot_projection_version": "2",
                    "selected_requests_json": "[]",
                    "completeness_warnings_json": "[]",
                },
            )
        with pytest.raises(Exception):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO snapshot_metadata "
                        "SELECT 2, build_key || 'x', competition_id, "
                        "primary_competition_season_id, sleeper_league_id, "
                        "season_year, through_week, as_of_date, "
                        "snapshot_projection_version, selected_requests_json, "
                        "completeness_warnings_json FROM snapshot_metadata"
                    )
                )
    finally:
        engine.dispose()


@pytest.mark.parametrize("version", ["", "1", " 2", "3"])
def test_unknown_projection_version_is_rejected(version: str) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        get_snapshot_schema(version)
