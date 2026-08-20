"""Immutable contracts for Sleeper request observations and payloads."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)

from backend.resources._contracts import ContractModel
from backend.resources.sleeper_data.common.objects import Page
from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.contracts import NormalizationStatus, RequestStatus
from backend.services.datalayer.local_files import StoredLocalArtifact
from backend.services.datalayer.sleeper.endpoints.contracts import CompletenessFinding
from backend.services.datalayer.sleeper.responses import (
    FailedSourceAttempt,
    RequestParameter,
    SourceAttempt,
)
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey

Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
SafeCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]
SafeSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class NormalizationRejection(ContractModel):
    code: SafeCode
    summary: SafeSummary


class RecordApiAttempt(ContractModel):
    refresh_run_id: UUID
    attempt: SourceAttempt
    completeness: CompletenessFinding
    object_receipt: StoredLocalArtifact | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> "RecordApiAttempt":
        if isinstance(self.attempt, FailedSourceAttempt):
            if self.completeness.is_complete:
                raise ValueError("a failed source attempt cannot be complete")
            if self.object_receipt is not None:
                raise ValueError(
                    "a failed source attempt cannot have a payload receipt"
                )
            return self
        if self.object_receipt is not None and (
            self.object_receipt.sha256 != self.attempt.raw_sha256
            or self.object_receipt.byte_length != self.attempt.byte_length
        ):
            raise ValueError("object receipt does not match the source payload")
        return self


class ApiRequest(ContractModel):
    id: UUID
    refresh_run_id: UUID
    competition_season_id: UUID | None
    endpoint_kind: EndpointKind
    scope_key: ScopeKey
    request_path: str
    request_parameters: dict[str, RequestParameter]
    week: int | None
    bracket_kind: Literal["winners", "losers"] | None
    requested_at: AwareDatetime
    completed_at: AwareDatetime
    latency_ms: int | None
    status: RequestStatus
    http_status: int | None
    error: dict[str, JsonValue] | None
    is_complete: StrictBool
    completeness_reason: str | None
    payload_id: UUID | None
    response_sha256: Sha256 | None
    normalization_status: NormalizationStatus
    normalizer_version: str | None
    normalized_at: AwareDatetime | None


class SnapshotCandidateQuery(ContractModel):
    competition_season_id: UUID
    scope_keys: tuple[ScopeKey, ...]
    through_week: int = Field(strict=True, ge=1, le=18)

    @model_validator(mode="after")
    def validate_scopes(self) -> "SnapshotCandidateQuery":
        if not self.scope_keys:
            raise ValueError("snapshot candidate query requires at least one scope")
        if len(set(self.scope_keys)) != len(self.scope_keys):
            raise ValueError("snapshot candidate scopes must be unique")
        return self


class ApiRequestCandidate(ContractModel):
    request_id: UUID
    competition_season_id: UUID | None
    endpoint_kind: EndpointKind
    scope_key: ScopeKey
    week: int | None
    bracket_kind: Literal["winners", "losers"] | None
    requested_at: AwareDatetime
    completed_at: AwareDatetime
    payload_id: UUID
    response_sha256: Sha256


class InlineVerifiedPayload(ContractModel):
    kind: Literal["inline_json"] = "inline_json"
    request_id: UUID
    scope_key: ScopeKey
    sha256: Sha256
    byte_length: int = Field(strict=True, ge=0)
    media_type: Literal["application/json"]
    payload: JsonValue


class ObjectVerifiedPayload(ContractModel):
    kind: Literal["object"] = "object"
    request_id: UUID
    scope_key: ScopeKey
    sha256: Sha256
    byte_length: int = Field(strict=True, ge=0)
    media_type: Literal["application/json"]
    storage_key: str

    @model_validator(mode="after")
    def validate_object_receipt(self) -> "ObjectVerifiedPayload":
        StoredLocalArtifact(
            storage_key=self.storage_key,
            sha256=self.sha256,
            byte_length=self.byte_length,
        )
        return self


VerifiedPayload: TypeAlias = Annotated[
    InlineVerifiedPayload | ObjectVerifiedPayload,
    Field(discriminator="kind"),
]
