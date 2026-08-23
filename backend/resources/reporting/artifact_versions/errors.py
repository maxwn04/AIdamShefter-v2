"""Stable application failures for reporting artifact revisions."""

from __future__ import annotations

from uuid import UUID


class ArtifactVersionResourceError(RuntimeError):
    """Base class for artifact-version failures safe at service boundaries."""


class ArtifactVersionResourceNotFound(ArtifactVersionResourceError):
    def __init__(self, resource_kind: str, resource_id: UUID) -> None:
        self.resource_kind = resource_kind
        self.resource_id = resource_id
        super().__init__(f"{resource_kind} {resource_id} was not found")


class ArtifactVersionLifecycleConflict(ArtifactVersionResourceError):
    def __init__(self, resource_id: UUID, message: str, *, actual_status: str) -> None:
        self.resource_id = resource_id
        self.message = message
        self.actual_status = actual_status
        super().__init__(message)


class ArtifactVersionConcurrencyConflict(ArtifactVersionResourceError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ArtifactVersionProvenanceConflict(ArtifactVersionResourceError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


__all__ = [
    "ArtifactVersionConcurrencyConflict",
    "ArtifactVersionLifecycleConflict",
    "ArtifactVersionProvenanceConflict",
    "ArtifactVersionResourceError",
    "ArtifactVersionResourceNotFound",
]
