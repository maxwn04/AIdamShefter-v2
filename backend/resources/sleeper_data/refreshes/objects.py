"""Immutable contracts for Sleeper refresh runs."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.contracts import RefreshStatus, RefreshTrigger
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


class PlannedEndpointScope(ContractModel):
    scope_key: ScopeKey
    endpoint_kind: EndpointKind
    required: StrictBool = True
    dependency_scope_keys: tuple[ScopeKey, ...] = ()

    @model_validator(mode="after")
    def validate_scope(self) -> "PlannedEndpointScope":
        if self.scope_key.value.split(":", 1)[0] != self.endpoint_kind.value:
            raise ValueError("planned scope key does not match its endpoint kind")
        if len(set(self.dependency_scope_keys)) != len(self.dependency_scope_keys):
            raise ValueError("planned scope dependencies must be unique")
        if self.scope_key in self.dependency_scope_keys:
            raise ValueError("planned scope cannot depend on itself")
        return self


class StartRefresh(ContractModel):
    competition_season_id: UUID
    requested_through_week: int | None = Field(
        default=None,
        strict=True,
        ge=1,
        le=18,
    )
    trigger: RefreshTrigger
    endpoint_scope: tuple[PlannedEndpointScope, ...]
    code_version: NonBlankStr
    normalizer_version: NonBlankStr

    @model_validator(mode="after")
    def validate_plan(self) -> "StartRefresh":
        if not self.endpoint_scope:
            raise ValueError("refresh plan requires at least one scope")
        keys = tuple(item.scope_key for item in self.endpoint_scope)
        if len(set(keys)) != len(keys):
            raise ValueError("refresh plan scope keys must be unique")
        available: set[ScopeKey] = set()
        for item in self.endpoint_scope:
            missing = set(item.dependency_scope_keys) - available
            if missing:
                raise ValueError(
                    "refresh plan dependencies must precede their consumers"
                )
            available.add(item.scope_key)
        return self


class RefreshRunQuery(ContractModel):
    competition_season_id: UUID
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class RefreshRun(ContractModel):
    id: UUID
    competition_id: UUID
    competition_season_id: UUID
    requested_through_week: int | None
    endpoint_scope: tuple[PlannedEndpointScope, ...]
    trigger: RefreshTrigger
    status: RefreshStatus
    code_version: str
    normalizer_version: str
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    error: dict[str, JsonValue] | None
    request_count: int = Field(strict=True, ge=0)
    succeeded_request_count: int = Field(strict=True, ge=0)
    failed_request_count: int = Field(strict=True, ge=0)


class RefreshRunPage(ContractModel):
    items: tuple[RefreshRun, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt
