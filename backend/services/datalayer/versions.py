"""Compatibility versions for normalized facts and frozen projections."""

INGESTION_NORMALIZER_VERSION = "1"
SNAPSHOT_PROJECTION_VERSION = "2"
RESOLVED_SNAPSHOT_PROJECTION_VERSION = "3"
# Changes to derived facts invalidate build reuse without changing SQLite shape.
SNAPSHOT_DERIVATION_VERSION = "1"
