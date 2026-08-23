"""Stable application failures for reporting artifact identities."""

from __future__ import annotations

from uuid import UUID


class ArtifactResourceError(RuntimeError):
    """Base class for artifact failures safe at service boundaries."""


class ArtifactResourceNotFound(ArtifactResourceError):
    def __init__(self, resource_kind: str, resource_id: UUID) -> None:
        self.resource_kind = resource_kind
        self.resource_id = resource_id
        super().__init__(f"{resource_kind} {resource_id} was not found")


class ArtifactLifecycleConflict(ArtifactResourceError):
    def __init__(self, resource_id: UUID, message: str, *, actual_status: str) -> None:
        self.resource_id = resource_id
        self.message = message
        self.actual_status = actual_status
        super().__init__(message)


class ArtifactConcurrencyConflict(ArtifactResourceError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ArtifactMediaTypeConflict(ArtifactResourceError):
    def __init__(
        self,
        path: str,
        *,
        requested_media_type: str,
        actual_media_type: str,
    ) -> None:
        self.path = path
        self.requested_media_type = requested_media_type
        self.actual_media_type = actual_media_type
        super().__init__(f"artifact {path} already uses media type {actual_media_type}")


__all__ = [
    "ArtifactConcurrencyConflict",
    "ArtifactLifecycleConflict",
    "ArtifactMediaTypeConflict",
    "ArtifactResourceError",
    "ArtifactResourceNotFound",
]
