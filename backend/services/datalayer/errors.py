"""Sanitized datalayer boundary errors."""

from dataclasses import dataclass

from .sleeper.scope import EndpointKind, ScopeKey


class DatalayerError(RuntimeError):
    """Base class for failures safe to translate at an application boundary."""


class InvalidDatalayerRequest(DatalayerError):
    """The caller supplied an invalid workflow request."""


class DatalayerResourceNotFound(DatalayerError):
    """A resource does not exist inside the caller's established scope."""


@dataclass(frozen=True, slots=True)
class EndpointPayloadRejected(DatalayerError):
    """A complete source payload cannot be mapped without inventing facts."""

    endpoint_kind: EndpointKind
    code: str
    summary: str

    def __str__(self) -> str:
        return self.summary


@dataclass(frozen=True, slots=True)
class SnapshotUnavailable(DatalayerError):
    """Required factual input or a ready artifact is currently unavailable."""

    message: str
    missing_scopes: tuple[ScopeKey, ...] = ()

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class InternalDatalayerFailure(DatalayerError):
    """Sanitized unexpected failure carrying only a correlation identifier."""

    correlation_id: str

    def __str__(self) -> str:
        return f"datalayer operation failed ({self.correlation_id})"
