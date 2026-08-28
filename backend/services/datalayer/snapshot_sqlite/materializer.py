"""Deterministic construction and verification of frozen SQLite artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Mapping, TypeAlias
from uuid import UUID

from sqlalchemy import create_engine

from backend.services.datalayer.canonical_json import canonical_json_bytes
from backend.services.datalayer.errors import DatalayerError
from backend.services.datalayer.snapshot_service import (
    MaterializedSnapshot,
    SnapshotMaterializationInput,
)
from backend.services.datalayer.snapshot_sqlite.derivations import (
    derive_snapshot_rows,
)
from backend.services.datalayer.snapshot_sqlite.projection import (
    SnapshotProjection,
    project_source_records,
)
from backend.services.datalayer.snapshot_sqlite.schema import (
    SQLITE_APPLICATION_ID,
    get_snapshot_schema,
)
from backend.services.datalayer.snapshot_sqlite.v3 import (
    ResolvedSnapshotMaterializationInput,
    project_resolved_snapshot,
)


_WEEK_TABLES = (
    "matchups",
    "player_performances",
    "games",
    "standings",
    "transactions",
)
_DERIVED_TABLES = {
    "games",
    "standings",
    "team_profiles",
    "draft_picks",
    "season_context",
    "roster_identities",
}
_V3_DERIVED_TABLES = _DERIVED_TABLES | {"snapshot_seasons"}
MaterializationInput: TypeAlias = (
    SnapshotMaterializationInput | ResolvedSnapshotMaterializationInput
)


class SnapshotArtifactInvalid(DatalayerError):
    """A staged SQLite artifact does not satisfy its immutable manifest."""


class SQLiteSnapshotMaterializer:
    """Build verified snapshot SQLite files under a private staging root."""

    def __init__(self, staging_root: Path) -> None:
        self._staging_root = staging_root.expanduser().resolve()
        self._staging_root.mkdir(parents=True, exist_ok=True)

    @property
    def staging_root(self) -> Path:
        return self._staging_root

    def materialize(
        self,
        materialization: MaterializationInput,
    ) -> MaterializedSnapshot:
        schema = get_snapshot_schema(materialization.snapshot_projection_version)
        descriptor, name = tempfile.mkstemp(
            suffix=".sqlite",
            dir=self._staging_root,
        )
        path = Path(name).resolve()
        try:
            _close_descriptor(descriptor)
            Path(name).unlink()
            if isinstance(materialization, ResolvedSnapshotMaterializationInput):
                projection = project_resolved_snapshot(materialization)
                _validate_resolved_projection(materialization, projection)
            else:
                source = project_source_records(materialization)
                projection = derive_snapshot_rows(materialization, source)
                _validate_projection(materialization, source, projection)
            metadata_row = _metadata_row(materialization, projection)
            engine = create_engine(f"sqlite:///{path.as_posix()}")
            try:
                with engine.begin() as connection:
                    connection.exec_driver_sql("PRAGMA page_size = 4096")
                    connection.exec_driver_sql("PRAGMA encoding = 'UTF-8'")
                    connection.exec_driver_sql("PRAGMA auto_vacuum = NONE")
                    connection.exec_driver_sql("PRAGMA journal_mode = DELETE")
                    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
                    connection.exec_driver_sql(
                        f"PRAGMA application_id = {SQLITE_APPLICATION_ID}"
                    )
                    connection.exec_driver_sql(
                        f"PRAGMA user_version = {schema.user_version}"
                    )
                    schema.metadata.create_all(connection)
                    for table_name in schema.table_order:
                        table = schema.tables[table_name]
                        values = (
                            (metadata_row,)
                            if table_name == "snapshot_metadata"
                            else projection.rows_for(table_name)
                        )
                        if values:
                            connection.execute(
                                table.insert(),
                                [dict(row) for row in values],
                            )
                with engine.connect() as connection:
                    connection.exec_driver_sql("VACUUM")
            finally:
                engine.dispose()
            verify_snapshot_file(path, materialization, projection)
            sha256, byte_length = _hash_file(path)
            return MaterializedSnapshot(
                path=path,
                sha256=sha256,
                byte_length=byte_length,
                completeness_warnings=projection.warnings,
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise


def verify_snapshot_file(
    path: Path,
    materialization: MaterializationInput,
    projection: SnapshotProjection,
) -> None:
    """Reopen a staged artifact immutably and verify its complete contract."""

    expected_schema = get_snapshot_schema(
        materialization.snapshot_projection_version
    )
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        raise SnapshotArtifactInvalid("snapshot SQLite file is unavailable") from error
    connection.row_factory = sqlite3.Row
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise SnapshotArtifactInvalid("snapshot SQLite integrity check failed")
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if (
            application_id != SQLITE_APPLICATION_ID
            or user_version != expected_schema.user_version
        ):
            raise SnapshotArtifactInvalid("snapshot SQLite version markers differ")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if tables != set(expected_schema.tables):
            raise SnapshotArtifactInvalid("snapshot SQLite table set is incomplete")
        metadata_rows = connection.execute("SELECT * FROM snapshot_metadata").fetchall()
        if len(metadata_rows) != 1 or dict(metadata_rows[0]) != _metadata_row(
            materialization,
            projection,
        ):
            raise SnapshotArtifactInvalid("snapshot metadata differs from build input")
        if isinstance(materialization, ResolvedSnapshotMaterializationInput):
            _verify_resolved_cutoffs(connection, materialization)
        else:
            _verify_v2_cutoff(connection, materialization)
        identity_rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM roster_identities ORDER BY league_id, roster_id"
            ).fetchall()
        ]
        if isinstance(materialization, ResolvedSnapshotMaterializationInput):
            _verify_resolved_identities(connection, materialization, identity_rows)
            orphan_move = connection.execute(
                "SELECT 1 FROM transaction_moves AS m "
                "LEFT JOIN transactions AS t "
                "ON t.league_id = m.league_id "
                "AND t.transaction_id = m.transaction_id "
                "WHERE t.transaction_id IS NULL LIMIT 1"
            ).fetchone()
            if orphan_move is not None:
                raise SnapshotArtifactInvalid(
                    "snapshot transaction move has no league-scoped parent"
                )
        else:
            roster_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT roster_id FROM rosters"
                ).fetchall()
            }
            _validate_roster_identities(materialization, identity_rows, roster_ids)
    except sqlite3.Error as error:
        raise SnapshotArtifactInvalid("snapshot SQLite verification failed") from error
    finally:
        connection.close()


def _validate_projection(
    materialization: SnapshotMaterializationInput,
    source: SnapshotProjection,
    projection: SnapshotProjection,
) -> None:
    selected_scopes = {entry.scope_key for entry in materialization.manifest.entries}
    source_count = sum(
        len(rows)
        for table, rows in source.rows.items()
        if table not in _DERIVED_TABLES
    )
    if len(source.provenance) != source_count:
        raise SnapshotArtifactInvalid("source row provenance is incomplete")
    if any(entry.scope_key not in selected_scopes for entry in source.provenance):
        raise SnapshotArtifactInvalid("source row provenance is outside the manifest")
    context = materialization.planning_context
    league_ids = {
        row["league_id"]
        for table, rows in projection.rows.items()
        if table not in {"users", "players", "transaction_moves"}
        for row in rows
        if "league_id" in row
    }
    if league_ids - {context.sleeper_league_id}:
        raise SnapshotArtifactInvalid("snapshot combines multiple leagues")
    seasons = {
        row["season"]
        for table, rows in projection.rows.items()
        if table != "draft_picks"
        for row in rows
        if "season" in row and row["season"] is not None
        and row.get("league_id") == context.sleeper_league_id
    }
    if seasons - {str(context.season_year)}:
        raise SnapshotArtifactInvalid("snapshot combines multiple competition seasons")
    roster_ids = {row["roster_id"] for row in projection.rows_for("rosters")}
    _validate_roster_identities(
        materialization,
        projection.rows_for("roster_identities"),
        roster_ids,
    )
    roster_tables = (
        "matchups",
        "player_performances",
        "roster_players",
        "standings",
    )
    for table_name in roster_tables:
        if any(
            row["roster_id"] not in roster_ids
            for row in projection.rows_for(table_name)
        ):
            raise SnapshotArtifactInvalid(
                "snapshot contains an unknown roster reference"
            )


def _validate_resolved_projection(
    materialization: ResolvedSnapshotMaterializationInput,
    projection: SnapshotProjection,
) -> None:
    selected_scopes = {
        entry.scope_key for entry in materialization.inputs.manifest.entries
    }
    source_count = sum(
        len(rows)
        for table, rows in projection.rows.items()
        if table not in _V3_DERIVED_TABLES
    )
    if len(projection.provenance) != source_count:
        raise SnapshotArtifactInvalid("source row provenance is incomplete")
    if any(entry.scope_key not in selected_scopes for entry in projection.provenance):
        raise SnapshotArtifactInvalid("source row provenance is outside the manifest")

    seasons = materialization.inputs.seasons
    expected_membership = {
        season.identity.sleeper_league_id: (
            str(season.identity.competition_id),
            str(season.identity.competition_season_id),
            str(season.identity.season_year),
            season.through_week,
        )
        for season in seasons
    }
    actual_membership = {
        row["league_id"]: (
            row["competition_id"],
            row["competition_season_id"],
            str(row["season_year"]),
            row["through_week"],
        )
        for row in projection.rows_for("snapshot_seasons")
    }
    if actual_membership != expected_membership:
        raise SnapshotArtifactInvalid("snapshot season membership is incomplete")

    for table_name, rows in projection.rows.items():
        if table_name in {"players", "snapshot_metadata", "snapshot_seasons"}:
            continue
        for row in rows:
            league_id = row.get("league_id")
            if league_id not in expected_membership:
                raise SnapshotArtifactInvalid("snapshot row is outside season membership")
            season = row.get("season")
            if season is not None and table_name != "draft_picks":
                if str(season) != expected_membership[league_id][2]:
                    raise SnapshotArtifactInvalid(
                        "snapshot row season conflicts with league membership"
                    )

    expected_mappings = _resolved_mapping_rows(materialization)
    actual_mappings = {
        (row["league_id"], row["roster_id"]): (
            row["competition_id"],
            row["competition_season_id"],
            row["season_roster_id"],
            row["franchise_id"],
        )
        for row in projection.rows_for("roster_identities")
    }
    if actual_mappings != expected_mappings:
        raise SnapshotArtifactInvalid("snapshot roster identities are incomplete")

    roster_keys = {
        (row["league_id"], row["roster_id"])
        for row in projection.rows_for("rosters")
    }
    if roster_keys != set(expected_mappings):
        raise SnapshotArtifactInvalid("snapshot rosters do not match exact mappings")
    for table_name in (
        "matchups",
        "player_performances",
        "roster_players",
        "standings",
    ):
        if any(
            (row["league_id"], row["roster_id"]) not in roster_keys
            for row in projection.rows_for(table_name)
        ):
            raise SnapshotArtifactInvalid("snapshot contains an unknown roster reference")
    transaction_keys = {
        (row["league_id"], row["transaction_id"])
        for row in projection.rows_for("transactions")
    }
    if any(
        (row["league_id"], row["transaction_id"]) not in transaction_keys
        for row in projection.rows_for("transaction_moves")
    ):
        raise SnapshotArtifactInvalid(
            "snapshot transaction move has no league-scoped parent"
        )


def _verify_v2_cutoff(
    connection: sqlite3.Connection,
    materialization: SnapshotMaterializationInput,
) -> None:
    cutoff = materialization.request.through_week
    for table_name in _WEEK_TABLES:
        leaked = connection.execute(
            f'SELECT 1 FROM "{table_name}" WHERE week > ? LIMIT 1',
            (cutoff,),
        ).fetchone()
        if leaked is not None:
            raise SnapshotArtifactInvalid("snapshot contains post-cutoff facts")
    playoff_start = materialization.planning_context.playoff_start_week
    if playoff_start is None:
        bracket_count = connection.execute(
            "SELECT COUNT(*) FROM playoff_matchups"
        ).fetchone()[0]
        if bracket_count:
            raise SnapshotArtifactInvalid("snapshot bracket cutoff is unknown")
        return
    leaked = connection.execute(
        "SELECT 1 FROM playoff_matchups WHERE (? + round - 1) > ? LIMIT 1",
        (playoff_start, cutoff),
    ).fetchone()
    if leaked is not None:
        raise SnapshotArtifactInvalid("snapshot contains post-cutoff bracket facts")


def _verify_resolved_cutoffs(
    connection: sqlite3.Connection,
    materialization: ResolvedSnapshotMaterializationInput,
) -> None:
    for season in materialization.inputs.seasons:
        league_id = season.identity.sleeper_league_id
        cutoff = season.through_week
        for table_name in _WEEK_TABLES:
            leaked = connection.execute(
                f'SELECT 1 FROM "{table_name}" '
                "WHERE league_id = ? AND week > ? LIMIT 1",
                (league_id, cutoff),
            ).fetchone()
            if leaked is not None:
                raise SnapshotArtifactInvalid("snapshot contains post-cutoff facts")
        playoff_start = season.settings.playoff_start_week
        if playoff_start is None:
            bracket_count = connection.execute(
                "SELECT COUNT(*) FROM playoff_matchups WHERE league_id = ?",
                (league_id,),
            ).fetchone()[0]
            if bracket_count:
                raise SnapshotArtifactInvalid("snapshot bracket cutoff is unknown")
            continue
        leaked = connection.execute(
            "SELECT 1 FROM playoff_matchups "
            "WHERE league_id = ? AND (? + round - 1) > ? LIMIT 1",
            (league_id, playoff_start, cutoff),
        ).fetchone()
        if leaked is not None:
            raise SnapshotArtifactInvalid("snapshot contains post-cutoff bracket facts")


def _verify_resolved_identities(
    connection: sqlite3.Connection,
    materialization: ResolvedSnapshotMaterializationInput,
    identity_rows: list[dict[str, Any]],
) -> None:
    roster_keys = {
        (row[0], row[1])
        for row in connection.execute(
            "SELECT league_id, roster_id FROM rosters"
        ).fetchall()
    }
    if {(row["league_id"], row["roster_id"]) for row in identity_rows} != roster_keys:
        raise SnapshotArtifactInvalid(
            "snapshot roster identities do not match snapshot rosters"
        )
    expected = _resolved_mapping_rows(materialization)
    actual = {
        (row["league_id"], row["roster_id"]): (
            row["competition_id"],
            row["competition_season_id"],
            row["season_roster_id"],
            row["franchise_id"],
        )
        for row in identity_rows
    }
    if actual != expected:
        raise SnapshotArtifactInvalid("snapshot roster identities differ from build input")


def _resolved_mapping_rows(
    materialization: ResolvedSnapshotMaterializationInput,
) -> dict[tuple[str, int], tuple[str, str, str, str]]:
    league_by_season = {
        season.identity.competition_season_id: season.identity.sleeper_league_id
        for season in materialization.inputs.seasons
    }
    return {
        (
            league_by_season[mapping.competition_season_id],
            int(mapping.sleeper_roster_id),
        ): (
            str(mapping.competition_id),
            str(mapping.competition_season_id),
            str(mapping.season_roster_id),
            str(mapping.franchise_id),
        )
        for mapping in materialization.inputs.roster_mappings
    }


def _validate_roster_identities(
    materialization: SnapshotMaterializationInput,
    rows: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    roster_ids: set[int],
) -> None:
    context = materialization.planning_context
    if {row["roster_id"] for row in rows} != roster_ids:
        raise SnapshotArtifactInvalid(
            "snapshot roster identities do not match snapshot rosters"
        )
    expected_scope = (
        context.sleeper_league_id,
        str(context.competition_id),
        str(context.competition_season_id),
    )
    if any(
        (
            row["league_id"],
            row["competition_id"],
            row["competition_season_id"],
        )
        != expected_scope
        for row in rows
    ):
        raise SnapshotArtifactInvalid(
            "snapshot roster identities are outside the snapshot scope"
        )
    for field in ("season_roster_id", "franchise_id"):
        values = [row[field] for row in rows]
        try:
            canonical = [str(UUID(value)) for value in values]
        except (AttributeError, TypeError, ValueError) as error:
            raise SnapshotArtifactInvalid(
                f"snapshot roster identity {field} is invalid"
            ) from error
        if values != canonical or len(values) != len(set(values)):
            raise SnapshotArtifactInvalid(
                f"snapshot roster identity {field} is invalid"
            )


def _metadata_row(
    materialization: MaterializationInput,
    projection: SnapshotProjection,
) -> dict[str, Any]:
    if isinstance(materialization, ResolvedSnapshotMaterializationInput):
        inputs = materialization.inputs
        manifest_entries = inputs.manifest.entries
        primary = next(
            season
            for season in inputs.seasons
            if season.role.value == "primary"
        )
        competition_id = primary.identity.competition_id
        competition_season_id = primary.identity.competition_season_id
        sleeper_league_id = primary.identity.sleeper_league_id
        season_year = primary.identity.season_year
        through_week = primary.through_week
        as_of_date = inputs.primary.as_of_date
        input_revision = inputs.input_revision
    else:
        manifest_entries = materialization.manifest.entries
        context = materialization.planning_context
        request = materialization.request
        competition_id = context.competition_id
        competition_season_id = context.competition_season_id
        sleeper_league_id = context.sleeper_league_id
        season_year = context.season_year
        through_week = request.through_week
        as_of_date = request.as_of_date
        input_revision = None
    manifest = [entry.model_dump(mode="json") for entry in manifest_entries]
    warnings = [warning.model_dump(mode="json") for warning in projection.warnings]
    row = {
        "singleton_id": 1,
        "build_key": materialization.build_key,
        "competition_id": str(competition_id),
        "primary_competition_season_id": str(competition_season_id),
        "sleeper_league_id": sleeper_league_id,
        "season_year": season_year,
        "through_week": through_week,
        "as_of_date": as_of_date.isoformat(),
        "snapshot_projection_version": materialization.snapshot_projection_version,
        "selected_requests_json": canonical_json_bytes(manifest).decode("utf-8"),
        "completeness_warnings_json": canonical_json_bytes(warnings).decode("utf-8"),
    }
    if input_revision is not None:
        row["input_revision"] = input_revision
    return row


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    length = 0
    with path.open("rb") as content:
        while chunk := content.read(1024 * 1024):
            digest.update(chunk)
            length += len(chunk)
    return digest.hexdigest(), length


def _close_descriptor(descriptor: int) -> None:
    import os

    os.close(descriptor)
