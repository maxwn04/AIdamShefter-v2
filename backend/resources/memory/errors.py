"""Stable application errors exposed by the canonical memory boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class MemoryError(Exception):
    """Base class for expected memory application failures."""

    code = "memory_error"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})


class MemoryNotFound(MemoryError):
    """A resource does not exist in the requested memory scope."""

    code = "memory_not_found"


class MemoryScopeViolation(MemoryError):
    """A resource exists but is outside the caller's competition or revision."""

    code = "memory_scope_violation"


class InvalidMemoryContent(MemoryError):
    """A typed memory payload violates its content contract."""

    code = "invalid_memory_content"


class InvalidMemoryReference(MemoryError):
    """A memory reference is missing, duplicated, or targets the wrong kind."""

    code = "invalid_memory_reference"


class InvalidMemoryCursor(MemoryError):
    """A pagination cursor is malformed for the requested memory collection."""

    code = "invalid_memory_cursor"


class InvalidMemoryQuery(MemoryError):
    """A memory read query violates a stable boundary constraint."""

    code = "invalid_memory_query"


class StaleCanonicalRevision(MemoryError):
    """Canonical memory advanced beyond a generation's pinned input revision."""

    code = "stale_canonical_revision"


class SearchProjectionUnavailable(Exception):
    """Internal signal that retrieval must use its bounded canonical fallback."""


class CanonicalStateHashMismatch(RuntimeError):
    """Internal invariant failure between prepared and stored canonical state."""


class UnsupportedMemorySchema(RuntimeError):
    """Internal signal that persisted content has no installed schema codec."""
