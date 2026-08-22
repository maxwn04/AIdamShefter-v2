"""Immutable values crossing the Sleeper HTTP boundary."""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from backend.services.datalayer.canonical_json import (
    JsonValue,
    canonical_json_bytes,
)
from backend.services.datalayer.contracts import RequestStatus
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


RequestParameter: TypeAlias = None | StrictBool | StrictInt | StrictStr
SourceErrorCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]
SourceErrorSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class _SourceValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class EndpointRequest(_SourceValue):
    endpoint_kind: EndpointKind
    scope_key: ScopeKey
    path: str
    parameters: dict[str, RequestParameter] = Field(default_factory=dict)
    week: int | None = Field(default=None, ge=1, le=18, strict=True)
    bracket_kind: Literal["winners", "losers"] | None = None

    @field_validator("path")
    @classmethod
    def require_sanitized_relative_api_path(cls, value: str) -> str:
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "?" in value
            or "#" in value
            or "://" in value
            or "\\" in value
            or any(character.isspace() for character in value)
        ):
            raise ValueError(
                "Sleeper path must be a sanitized absolute API path without a query"
            )
        if any(part in {".", ".."} for part in value.split("/")):
            raise ValueError("Sleeper path must not contain traversal segments")
        return value

    @field_validator("parameters")
    @classmethod
    def reject_binary_float_parameters(
        cls,
        value: dict[str, RequestParameter],
    ) -> dict[str, RequestParameter]:
        if any(
            not key or any(character.isspace() for character in key)
            for key in value
        ):
            raise ValueError(
                "Sleeper parameter names must be non-empty and contain no whitespace"
            )
        return value


class SanitizedSourceError(_SourceValue):
    code: SourceErrorCode
    summary: SourceErrorSummary


class _TimedSourceAttempt(_SourceValue):
    requested_at: datetime
    completed_at: datetime
    latency_ms: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def validate_timing(self) -> "_TimedSourceAttempt":
        for timestamp in (self.requested_at, self.completed_at):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("source attempt timestamps must include a timezone")
        if self.completed_at < self.requested_at:
            raise ValueError("source attempt cannot complete before it was requested")
        return self


class SuccessfulSourceAttempt(_TimedSourceAttempt):
    outcome: Literal["succeeded"] = "succeeded"
    endpoint: EndpointRequest
    http_status: int = Field(ge=200, le=299, strict=True)
    payload: JsonValue
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_length: int = Field(ge=0, strict=True)
    media_type: Literal["application/json"] = "application/json"

    @field_validator("payload", mode="before")
    @classmethod
    def reject_binary_float_payloads(cls, value: object) -> object:
        _reject_binary_floats(value)
        return value

    @model_validator(mode="after")
    def validate_payload_receipt(self) -> "SuccessfulSourceAttempt":
        canonical = canonical_json_bytes(self.payload)
        if self.byte_length != len(canonical):
            raise ValueError("source payload byte length does not match canonical JSON")
        if self.raw_sha256 != hashlib.sha256(canonical).hexdigest():
            raise ValueError("source payload SHA-256 does not match canonical JSON")
        return self


class FailedSourceAttempt(_TimedSourceAttempt):
    outcome: Literal["failed"] = "failed"
    endpoint: EndpointRequest
    status: RequestStatus
    http_status: int | None = Field(default=None, ge=100, le=599, strict=True)
    error: SanitizedSourceError

    @model_validator(mode="after")
    def validate_failure_status(self) -> "FailedSourceAttempt":
        if self.status is RequestStatus.SUCCEEDED:
            raise ValueError("failed source attempt cannot have succeeded status")
        if self.status is RequestStatus.HTTP_ERROR and self.http_status is None:
            raise ValueError("HTTP source failure requires an HTTP status")
        if (
            self.status is RequestStatus.TRANSPORT_ERROR
            and self.http_status is not None
        ):
            raise ValueError("transport source failure cannot have an HTTP status")
        if self.status is RequestStatus.INVALID_PAYLOAD and (
            self.http_status is None or not 200 <= self.http_status <= 299
        ):
            raise ValueError(
                "invalid payload failure requires a successful HTTP status"
            )
        return self


SourceAttempt = Annotated[
    SuccessfulSourceAttempt | FailedSourceAttempt,
    Field(discriminator="outcome"),
]


def _reject_binary_floats(value: object) -> None:
    if isinstance(value, float):
        raise ValueError("binary floats are not accepted at the Sleeper boundary")
    if isinstance(value, list):
        for item in value:
            _reject_binary_floats(item)
    elif isinstance(value, dict):
        for item in value.values():
            _reject_binary_floats(item)
