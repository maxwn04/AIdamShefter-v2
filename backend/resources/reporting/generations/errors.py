"""Stable application failures for generation lifecycle persistence."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID


class GenerationResourceError(RuntimeError):
    """Base class for generation resource failures safe at service boundaries."""


class GenerationResourceNotFound(GenerationResourceError):
    def __init__(self, resource_kind: str, resource_id: UUID) -> None:
        self.resource_kind = resource_kind
        self.resource_id = resource_id
        super().__init__(f"{resource_kind} {resource_id} was not found")


class GenerationLifecycleConflict(GenerationResourceError):
    def __init__(
        self,
        generation_id: UUID,
        message: str,
        *,
        expected_statuses: Iterable[str] = (),
        actual_status: str | None = None,
    ) -> None:
        self.generation_id = generation_id
        self.message = message
        self.expected_statuses = tuple(expected_statuses)
        self.actual_status = actual_status
        super().__init__(message)


class GenerationConcurrencyConflict(GenerationResourceError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


__all__ = [
    "GenerationConcurrencyConflict",
    "GenerationLifecycleConflict",
    "GenerationResourceError",
    "GenerationResourceNotFound",
]
