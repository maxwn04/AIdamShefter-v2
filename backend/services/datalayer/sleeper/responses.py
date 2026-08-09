"""Typed values crossing the Sleeper HTTP boundary."""

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.json import JsonValue
from ..contracts import RequestStatus
from backend.sleeper import EndpointKind, ScopeKey

RequestParameter: TypeAlias = None | bool | int | str


class _SourceValue(BaseModel):
    model_config = ConfigDict(frozen=True)


class EndpointRequest(_SourceValue):
    endpoint_kind: EndpointKind
    scope_key: ScopeKey
    path: str
    parameters: dict[str, RequestParameter] = Field(default_factory=dict)
    week: int | None = Field(default=None, ge=1, le=18)
    bracket_kind: Literal["winners", "losers"] | None = None

    @field_validator("path")
    @classmethod
    def require_relative_api_path(cls, value: str) -> str:
        if not value.startswith("/") or "?" in value or "://" in value:
            raise ValueError("Sleeper path must be an absolute API path without a query")
        return value


class SanitizedSourceError(_SourceValue):
    code: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class _TimedAttempt(_SourceValue):
    requested_at: datetime
    completed_at: datetime
    latency_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_timing(self) -> "_TimedAttempt":
        for value in (self.requested_at, self.completed_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("source attempt timestamps must include a timezone")
        if self.completed_at < self.requested_at:
            raise ValueError("source attempt cannot complete before it was requested")
        return self


class SuccessfulSourceAttempt(_TimedAttempt):
    outcome: Literal["succeeded"] = "succeeded"
    endpoint: EndpointRequest
    http_status: int
    payload: JsonValue
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_length: int = Field(ge=0)
    media_type: str


class FailedSourceAttempt(_TimedAttempt):
    outcome: Literal["failed"] = "failed"
    endpoint: EndpointRequest
    requested_at: datetime
    completed_at: datetime
    status: Literal[
        RequestStatus.HTTP_ERROR,
        RequestStatus.TRANSPORT_ERROR,
        RequestStatus.INVALID_PAYLOAD,
    ]
    http_status: int | None
    error: SanitizedSourceError


SourceAttempt = Annotated[
    SuccessfulSourceAttempt | FailedSourceAttempt,
    Field(discriminator="outcome"),
]


class CompletenessFinding(_SourceValue):
    is_complete: bool
    code: str = Field(min_length=1)
    summary: str = Field(min_length=1)
