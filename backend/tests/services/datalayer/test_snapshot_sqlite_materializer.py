from pathlib import Path
import sqlite3

import pytest

from backend.services.datalayer.snapshot_sqlite import (
    SQLiteSnapshotMaterializer,
    SnapshotArtifactInvalid,
    derive_snapshot_rows,
    project_source_records,
    verify_snapshot_file,
)
from backend.services.datalayer import (
    DatalayerSnapshotService,
    LocalDatalayerFileStore,
)
from backend.tests.services.datalayer.test_snapshot_service import (
    FakePlanning,
    FakeRequests,
    FakeRosterIdentities,
    FakeSnapshots,
    _request,
)
from backend.tests.services.datalayer.test_snapshot_source_projection import (
    _fixture_input,
)


def test_identical_inputs_produce_identical_sqlite_bytes(tmp_path: Path) -> None:
    materialization = _fixture_input()
    materializer = SQLiteSnapshotMaterializer(tmp_path / "staging")

    first = materializer.materialize(materialization)
    second = materializer.materialize(materialization)
    try:
        assert first.sha256 == second.sha256
        assert first.byte_length == second.byte_length
        assert first.path.read_bytes() == second.path.read_bytes()
    finally:
        first.path.unlink(missing_ok=True)
        second.path.unlink(missing_ok=True)


def test_artifact_contains_manifest_warnings_and_no_volatile_state(
    tmp_path: Path,
) -> None:
    materialization = _fixture_input()
    artifact = SQLiteSnapshotMaterializer(tmp_path / "staging").materialize(
        materialization
    )
    try:
        connection = sqlite3.connect(artifact.path)
        connection.row_factory = sqlite3.Row
        metadata = dict(
            connection.execute("SELECT * FROM snapshot_metadata").fetchone()
        )
        player = dict(connection.execute("SELECT * FROM players LIMIT 1").fetchone())
        context = dict(connection.execute("SELECT * FROM season_context").fetchone())
        identities = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM roster_identities ORDER BY roster_id"
            ).fetchall()
        ]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        connection.close()

        assert metadata["build_key"] == materialization.build_key
        assert metadata["through_week"] == 2
        assert "week_matchups" in metadata["selected_requests_json"]
        assert "snapshot.player_state_omitted" in metadata[
            "completeness_warnings_json"
        ]
        assert player["nfl_team"] is None
        assert player["status"] is None
        assert user_version == 2
        assert [row["roster_id"] for row in identities] == [1, 2]
        assert identities[0]["season_roster_id"] == (
            "00000000-0000-0000-0000-000000000065"
        )
        assert context == {
            "league_id": "123",
            "computed_week": 2,
            "override_week": 2,
            "effective_week": 2,
            "generated_at": None,
        }
    finally:
        artifact.path.unlink(missing_ok=True)


def test_wrong_expected_build_metadata_fails_closed(tmp_path: Path) -> None:
    materialization = _fixture_input()
    artifact = SQLiteSnapshotMaterializer(tmp_path / "staging").materialize(
        materialization
    )
    source = project_source_records(materialization)
    projection = derive_snapshot_rows(materialization, source)
    wrong = materialization.model_copy(update={"build_key": "b" * 64})
    try:
        with pytest.raises(SnapshotArtifactInvalid, match="metadata"):
            verify_snapshot_file(artifact.path, wrong, projection)
    finally:
        artifact.path.unlink(missing_ok=True)


def test_corrupt_or_incomplete_sqlite_fails_closed(tmp_path: Path) -> None:
    materialization = _fixture_input()
    source = project_source_records(materialization)
    projection = derive_snapshot_rows(materialization, source)
    incomplete = tmp_path / "incomplete.sqlite"
    sqlite3.connect(incomplete).close()

    with pytest.raises(SnapshotArtifactInvalid, match="version markers|table set"):
        verify_snapshot_file(incomplete, materialization, projection)


def test_unsupported_projection_version_removes_staged_file(tmp_path: Path) -> None:
    materialization = _fixture_input().model_copy(
        update={"snapshot_projection_version": "1"}
    )
    staging = tmp_path / "staging"
    materializer = SQLiteSnapshotMaterializer(staging)

    with pytest.raises(ValueError, match="unsupported"):
        materializer.materialize(materialization)

    assert list(staging.iterdir()) == []


def test_real_materializer_runs_through_storage_and_sealing(tmp_path: Path) -> None:
    class FixturePlanning(FakePlanning):
        def get_snapshot_planning_context(self, competition_season_id):
            context = super().get_snapshot_planning_context(competition_season_id)
            return context.model_copy(update={"season_year": 2024})

    files = LocalDatalayerFileStore(tmp_path / "data")
    requests = FakeRequests(files=files)
    snapshots = FakeSnapshots()
    staging = tmp_path / "materializer-staging"
    service = DatalayerSnapshotService(
        planning=FixturePlanning(),
        roster_identities=FakeRosterIdentities(),
        requests=requests,
        snapshots=snapshots,
        materializer=SQLiteSnapshotMaterializer(staging),
        files=files,
        code_version="test",
    )

    ready = service.get_or_create(_request())

    assert ready.artifact.path.exists()
    assert ready.artifact.sha256 == snapshots.sealed.artifact.sha256
    assert snapshots.sealed is not None
    assert len(snapshots.sealed.requests) == 7
    assert list(staging.glob("*.sqlite")) == []
    connection = sqlite3.connect(ready.artifact.path)
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()
