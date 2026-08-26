"""Stable, sanitized datalayer application failures."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


class DatalayerError(RuntimeError):
    """Base class for failures safe to translate at an application boundary."""


class InvalidDatalayerRequest(DatalayerError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DatalayerResourceNotFound(DatalayerError):
    def __init__(self, resource_kind: str, resource_id: str) -> None:
        self.resource_kind = resource_kind
        self.resource_id = resource_id
        super().__init__(f"{resource_kind} {resource_id} was not found")


class DatalayerScopeConflict(DatalayerError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class RosterIdentityMappingRequired(DatalayerScopeConflict):
    """A complete roster observation cannot yet resolve durable identities."""

    def __init__(
        self,
        message: str,
        *,
        competition_season_id: UUID | None = None,
        sleeper_roster_ids: Iterable[str] = (),
    ) -> None:
        self.competition_season_id = competition_season_id
        self.sleeper_roster_ids = tuple(sleeper_roster_ids)
        super().__init__(message)


class EndpointPayloadRejected(DatalayerError):
    """A source payload cannot be normalized without inventing facts."""

    def __init__(self, endpoint_kind: EndpointKind, code: str, summary: str) -> None:
        self.endpoint_kind = endpoint_kind
        self.code = code
        self.summary = summary
        super().__init__(summary)


class SnapshotUnavailable(DatalayerError):
    """Required factual inputs or a healthy ready artifact are unavailable."""

    def __init__(
        self,
        message: str,
        missing_scopes: Iterable[ScopeKey] = (),
    ) -> None:
        self.message = message
        self.missing_scopes = tuple(missing_scopes)
        super().__init__(message)


class SnapshotInputsUnavailable(SnapshotUnavailable):
    """One bounded refresh did not produce complete snapshot inputs."""

    def __init__(
        self,
        competition_season_id: UUID,
        missing_scopes: Iterable[ScopeKey] = (),
    ) -> None:
        self.competition_season_id = competition_season_id
        super().__init__(
            "snapshot inputs remain unavailable after automatic refresh",
            missing_scopes,
        )


class RefreshUnavailable(DatalayerError):
    """Automatic refresh could not be completed within its bounded workflow."""

    def __init__(
        self,
        competition_season_id: UUID,
        *,
        claim_id: UUID | None = None,
        refresh_run_id: UUID | None = None,
        retryable: bool = False,
    ) -> None:
        self.competition_season_id = competition_season_id
        self.claim_id = claim_id
        self.refresh_run_id = refresh_run_id
        self.retryable = retryable
        super().__init__("automatic season refresh is unavailable")


class InternalDatalayerFailure(DatalayerError):
    """Sanitized unexpected failure carrying only a correlation identifier."""

    def __init__(self, correlation_id: str) -> None:
        self.correlation_id = correlation_id
        super().__init__(f"datalayer operation failed ({correlation_id})")
