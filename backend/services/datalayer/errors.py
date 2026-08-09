"""Sanitized datalayer boundary errors."""

from dataclasses import dataclass

from backend.sleeper import EndpointKind, ScopeKey


class DatalayerError(RuntimeError):
    """Base class for failures safe to translate at an application boundary."""


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
