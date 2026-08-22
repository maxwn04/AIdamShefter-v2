from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.services.datalayer.canonical_json import canonical_json_bytes
from backend.services.datalayer.contracts import RequestStatus
from backend.services.datalayer.sleeper.responses import (
    EndpointRequest,
    FailedSourceAttempt,
    SanitizedSourceError,
    SourceAttempt,
    SuccessfulSourceAttempt,
)
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
REQUESTED_AT = datetime(2025, 10, 28, 12, tzinfo=timezone.utc)
COMPLETED_AT = REQUESTED_AT + timedelta(milliseconds=12)


def _endpoint(**overrides: object) -> EndpointRequest:
    values: dict[str, object] = {
        "endpoint_kind": EndpointKind.MATCHUPS,
        "scope_key": ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 8),
        "path": "/league/123/matchups/8",
        "parameters": {"sport": "nfl", "week": 8, "active": True},
        "week": 8,
    }
    values.update(overrides)
    return EndpointRequest(**values)  # type: ignore[arg-type]


def _success() -> SuccessfulSourceAttempt:
    payload = {"score": Decimal("123.4500"), "players": ["1", "2"]}
    canonical = canonical_json_bytes(payload)
    return SuccessfulSourceAttempt(
        endpoint=_endpoint(),
        requested_at=REQUESTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=12,
        http_status=200,
        payload=payload,
        raw_sha256=hashlib.sha256(canonical).hexdigest(),
        byte_length=len(canonical),
    )


def test_source_attempt_union_round_trips_both_discriminated_outcomes() -> None:
    adapter = TypeAdapter(SourceAttempt)
    success = _success()
    failure = FailedSourceAttempt(
        endpoint=_endpoint(),
        requested_at=REQUESTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=12,
        status=RequestStatus.HTTP_ERROR,
        http_status=503,
        error=SanitizedSourceError(
            code="sleeper_http_error",
            summary="Sleeper returned HTTP 503",
        ),
    )

    assert adapter.validate_python(success.model_dump()).outcome == "succeeded"
    assert adapter.validate_python(failure.model_dump()).outcome == "failed"


def test_source_contracts_are_frozen_and_forbid_unknown_fields() -> None:
    endpoint = _endpoint()

    with pytest.raises(ValidationError, match="frozen"):
        endpoint.week = 9
    with pytest.raises(ValidationError, match="extra"):
        EndpointRequest(
            endpoint_kind=EndpointKind.MATCHUPS,
            scope_key=endpoint.scope_key,
            path=endpoint.path,
            secret_header="value",
        )


@pytest.mark.parametrize(
    "path",
    [
        "league/123",
        "//evil.example/path",
        "/league/123?token=secret",
        "/league/123#fragment",
        "https://evil.example/path",
        "/league/../secret",
        "/league\\123",
        "/league/has space",
    ],
)
def test_endpoint_request_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        _endpoint(path=path)


@pytest.mark.parametrize(
    "parameters",
    [
        {"score": 0.1},
        {"week": "8", "nested": {"secret": "value"}},
        {"has space": "value"},
    ],
)
def test_endpoint_request_rejects_unsafe_parameters(
    parameters: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _endpoint(parameters=parameters)


@pytest.mark.parametrize(
    ("requested_at", "completed_at"),
    [
        (datetime(2025, 10, 28), COMPLETED_AT),
        (REQUESTED_AT, datetime(2025, 10, 28)),
        (COMPLETED_AT, REQUESTED_AT),
    ],
)
def test_source_attempt_rejects_invalid_timing(
    requested_at: datetime,
    completed_at: datetime,
) -> None:
    success = _success()

    with pytest.raises(ValidationError):
        SuccessfulSourceAttempt(
            **success.model_dump(exclude={"requested_at", "completed_at"}),
            requested_at=requested_at,
            completed_at=completed_at,
        )


def test_successful_attempt_requires_exact_canonical_receipt() -> None:
    success = _success()

    with pytest.raises(ValidationError, match="byte length"):
        SuccessfulSourceAttempt(
            **success.model_dump(exclude={"byte_length"}),
            byte_length=success.byte_length + 1,
        )
    with pytest.raises(ValidationError, match="SHA-256"):
        SuccessfulSourceAttempt(
            **success.model_dump(exclude={"raw_sha256"}),
            raw_sha256="0" * 64,
        )
    with pytest.raises(ValidationError, match="binary floats"):
        SuccessfulSourceAttempt(
            **success.model_dump(exclude={"payload"}),
            payload={"score": 0.1},
        )


@pytest.mark.parametrize(
    ("status", "http_status"),
    [
        (RequestStatus.SUCCEEDED, None),
        (RequestStatus.HTTP_ERROR, None),
        (RequestStatus.TRANSPORT_ERROR, 503),
        (RequestStatus.INVALID_PAYLOAD, None),
        (RequestStatus.INVALID_PAYLOAD, 503),
    ],
)
def test_failed_attempt_rejects_inconsistent_status(
    status: RequestStatus,
    http_status: int | None,
) -> None:
    with pytest.raises(ValidationError):
        FailedSourceAttempt(
            endpoint=_endpoint(),
            requested_at=REQUESTED_AT,
            completed_at=COMPLETED_AT,
            latency_ms=12,
            status=status,
            http_status=http_status,
            error=SanitizedSourceError(code="safe_code", summary="Safe summary"),
        )


@pytest.mark.parametrize(
    ("code", "summary"),
    [("Not Canonical", "Safe"), ("safe_code", "   "), ("safe_code", "x" * 501)],
)
def test_source_error_rejects_unstructured_values(code: str, summary: str) -> None:
    with pytest.raises(ValidationError):
        SanitizedSourceError(code=code, summary=summary)
