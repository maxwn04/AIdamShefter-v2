"""Snapshot-only SQLite schema, projections, and materialization."""

from backend.services.datalayer.snapshot_sqlite.schema import (
    SQLITE_APPLICATION_ID,
    SQLITE_USER_VERSION,
    SQLITE_USER_VERSION_V3,
    SnapshotSchema,
    get_snapshot_schema,
)
from backend.services.datalayer.snapshot_sqlite.projection import (
    SnapshotProjection,
    SourceRowProvenance,
    project_source_records,
)
from backend.services.datalayer.snapshot_sqlite.derivations import (
    derive_snapshot_rows,
)
from backend.services.datalayer.snapshot_sqlite.materializer import (
    SQLiteSnapshotMaterializer,
    SnapshotArtifactInvalid,
    verify_snapshot_file,
)
from backend.services.datalayer.snapshot_sqlite.v3 import (
    ResolvedSnapshotMaterializationInput,
    project_resolved_snapshot,
)

__all__ = [
    "SnapshotProjection",
    "SQLITE_APPLICATION_ID",
    "SQLITE_USER_VERSION",
    "SQLITE_USER_VERSION_V3",
    "SQLiteSnapshotMaterializer",
    "SnapshotArtifactInvalid",
    "SnapshotSchema",
    "ResolvedSnapshotMaterializationInput",
    "SourceRowProvenance",
    "derive_snapshot_rows",
    "get_snapshot_schema",
    "project_source_records",
    "project_resolved_snapshot",
    "verify_snapshot_file",
]
