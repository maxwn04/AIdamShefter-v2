from backend.services.datalayer import (
    INGESTION_NORMALIZER_VERSION,
    SNAPSHOT_PROJECTION_VERSION,
)


def test_compatibility_versions_are_explicit_nonempty_strings() -> None:
    assert INGESTION_NORMALIZER_VERSION == "1"
    assert SNAPSHOT_PROJECTION_VERSION == "2"
