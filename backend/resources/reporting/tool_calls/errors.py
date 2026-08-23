"""Stable application failures for tool-call persistence."""

from __future__ import annotations

from uuid import UUID


class ToolCallResourceError(RuntimeError):
    """Base class for tool-call failures safe at service boundaries."""


class ToolCallResourceNotFound(ToolCallResourceError):
    def __init__(self, resource_kind: str, resource_id: UUID) -> None:
        self.resource_kind = resource_kind
        self.resource_id = resource_id
        super().__init__(f"{resource_kind} {resource_id} was not found")


class ToolCallLifecycleConflict(ToolCallResourceError):
    def __init__(self, resource_id: UUID, message: str, *, actual_status: str) -> None:
        self.resource_id = resource_id
        self.message = message
        self.actual_status = actual_status
        super().__init__(message)


class ToolCallConcurrencyConflict(ToolCallResourceError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


__all__ = [
    "ToolCallConcurrencyConflict",
    "ToolCallLifecycleConflict",
    "ToolCallResourceError",
    "ToolCallResourceNotFound",
]
