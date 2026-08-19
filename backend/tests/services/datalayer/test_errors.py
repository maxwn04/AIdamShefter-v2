from uuid import UUID

from backend.services.datalayer import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
    EndpointKind,
    EndpointPayloadRejected,
    InternalDatalayerFailure,
    InvalidDatalayerRequest,
    ScopeKey,
    SnapshotUnavailable,
)


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")


def test_boundary_errors_retain_only_safe_typed_context() -> None:
    missing = ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 8)
    unavailable = SnapshotUnavailable("required snapshot inputs are unavailable", [missing])
    rejected = EndpointPayloadRejected(
        EndpointKind.LEAGUE_ROSTERS,
        "identity_mapping_missing",
        "roster identity mapping is incomplete",
    )

    assert unavailable.missing_scopes == (missing,)
    assert str(unavailable) == "required snapshot inputs are unavailable"
    assert rejected.endpoint_kind is EndpointKind.LEAGUE_ROSTERS
    assert rejected.code == "identity_mapping_missing"
    assert str(rejected) == "roster identity mapping is incomplete"


def test_http_translation_categories_have_stable_messages() -> None:
    invalid = InvalidDatalayerRequest("through_week must be in the active season")
    missing = DatalayerResourceNotFound("data snapshot", "snapshot-1")
    conflict = DatalayerScopeConflict("season belongs to another competition")
    internal = InternalDatalayerFailure("correlation-123")

    assert str(invalid) == "through_week must be in the active season"
    assert str(missing) == "data snapshot snapshot-1 was not found"
    assert str(conflict) == "season belongs to another competition"
    assert str(internal) == "datalayer operation failed (correlation-123)"
