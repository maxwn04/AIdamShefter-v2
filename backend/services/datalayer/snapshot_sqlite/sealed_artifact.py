"""Verify a stored artifact against its sealed PostgreSQL audit identity."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from backend.resources.sleeper_data.snapshots import (
    DataSnapshot,
    SnapshotRequestMembership,
)
from backend.services.datalayer.canonical_json import (
    canonical_json_bytes,
    parse_json_bytes,
)
from backend.services.datalayer.snapshot_sqlite.materializer import (
    SnapshotArtifactInvalid,
)
from backend.services.datalayer.snapshot_sqlite.schema import (
    SQLITE_APPLICATION_ID,
    get_snapshot_schema,
)


def verify_sealed_snapshot_file(
    path: Path,
    snapshot: DataSnapshot,
    requests: tuple[SnapshotRequestMembership, ...],
) -> None:
    """Fail when immutable SQLite identity disagrees with sealed DB records."""

    schema = get_snapshot_schema(snapshot.snapshot_projection_version)
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise SnapshotArtifactInvalid(
            "sealed snapshot SQLite file is unavailable"
        ) from error
    connection.row_factory = sqlite3.Row
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise SnapshotArtifactInvalid("sealed snapshot integrity check failed")
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        if application_id != SQLITE_APPLICATION_ID:
            raise SnapshotArtifactInvalid("sealed snapshot application ID differs")
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if user_version != schema.user_version:
            raise SnapshotArtifactInvalid("sealed snapshot user version differs")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if tables != set(schema.tables):
            raise SnapshotArtifactInvalid("sealed snapshot table set differs")

        metadata_rows = connection.execute("SELECT * FROM snapshot_metadata").fetchall()
        if len(metadata_rows) != 1:
            raise SnapshotArtifactInvalid("sealed snapshot metadata is not singular")
        metadata = dict(metadata_rows[0])
        expected_identity = {
            "build_key": snapshot.build_key,
            "competition_id": str(snapshot.competition_id),
            "primary_competition_season_id": str(
                snapshot.primary_competition_season_id
            ),
            "through_week": snapshot.through_week,
            "as_of_date": snapshot.as_of_date.isoformat(),
            "snapshot_projection_version": snapshot.snapshot_projection_version,
        }
        if any(metadata.get(key) != value for key, value in expected_identity.items()):
            raise SnapshotArtifactInvalid("sealed snapshot metadata identity differs")
        if snapshot.snapshot_projection_version == "3":
            if metadata.get("input_revision") != snapshot.input_revision:
                raise SnapshotArtifactInvalid("sealed snapshot input revision differs")
            _verify_seasons(connection, snapshot)

        stored_requests = _decode_request_memberships(
            metadata.get("selected_requests_json")
        )
        if _request_identity(stored_requests) != _request_identity(requests):
            raise SnapshotArtifactInvalid("sealed snapshot request membership differs")
        expected_warnings = canonical_json_bytes(
            [
                warning.model_dump(mode="json")
                for warning in snapshot.completeness_warnings
            ]
        ).decode("utf-8")
        if metadata.get("completeness_warnings_json") != expected_warnings:
            raise SnapshotArtifactInvalid("sealed snapshot warning metadata differs")
    except sqlite3.Error as error:
        raise SnapshotArtifactInvalid("sealed snapshot verification failed") from error
    finally:
        connection.close()


def _verify_seasons(connection: sqlite3.Connection, snapshot: DataSnapshot) -> None:
    rows = connection.execute(
        "SELECT competition_id, competition_season_id, league_id, season_year, "
        "sequence_number, role, through_week FROM snapshot_seasons "
        "ORDER BY sequence_number"
    ).fetchall()
    actual = tuple(tuple(row) for row in rows)
    expected = tuple(
        (
            str(season.competition_id),
            str(season.competition_season_id),
            season.sleeper_league_id,
            season.season_year,
            season.sequence_number,
            season.role.value,
            season.through_week,
        )
        for season in snapshot.included_seasons
    )
    if actual != expected:
        raise SnapshotArtifactInvalid("sealed snapshot season membership differs")


def _decode_request_memberships(value: object) -> tuple[SnapshotRequestMembership, ...]:
    if not isinstance(value, str):
        raise SnapshotArtifactInvalid("sealed snapshot request metadata is missing")
    try:
        parsed = parse_json_bytes(value.encode("utf-8"))
        if not isinstance(parsed, list):
            raise ValueError("request metadata must be a list")
        return tuple(SnapshotRequestMembership.model_validate(item) for item in parsed)
    except (TypeError, ValueError) as error:
        raise SnapshotArtifactInvalid(
            "sealed snapshot request metadata is invalid"
        ) from error


def _request_identity(
    requests: tuple[SnapshotRequestMembership, ...],
) -> tuple[tuple[str, str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                str(request.request_id),
                request.endpoint_kind.value,
                request.scope_key.value,
                request.response_sha256,
                request.selection_role.value,
            )
            for request in requests
        )
    )


__all__ = ["verify_sealed_snapshot_file"]
