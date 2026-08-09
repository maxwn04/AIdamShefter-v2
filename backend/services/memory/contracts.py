"""Narrow consumer ports for canonical memory reads.

The protocols describe capabilities granted to callers.  They deliberately do
not mirror ``MemoryManager``: persistence search and hydration primitives stay
behind ``MemoryService``.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from backend.resources.memory.objects import (
    DEFAULT_EXPANSION,
    ExpansionPolicy,
    HydratedMemoryVersion,
    ItemHistory,
    MemoryListQuery,
    MemoryMutationBundle,
    MemoryPage,
    MemoryQuery,
    MemoryRevisionRef,
    MutationResult,
    RebuildResult,
    RetrievedMemory,
    RevisionPage,
    SearchIndexStatus,
)


class PinnedMemoryReader(Protocol):
    """Revision-bound memory capability supplied to reporter execution."""

    @property
    def revision(self) -> MemoryRevisionRef: ...

    def retrieve(self, query: MemoryQuery) -> RetrievedMemory: ...

    def get_version(
        self,
        version_id: UUID,
        expansion: ExpansionPolicy = DEFAULT_EXPANSION,
    ) -> HydratedMemoryVersion: ...

    def get_item(
        self,
        item_id: UUID,
        expansion: ExpansionPolicy = DEFAULT_EXPANSION,
    ) -> HydratedMemoryVersion: ...


class MemoryReader(Protocol):
    """Capability for resolving and pinning canonical memory revisions."""

    def pin_current(self, competition_id: UUID) -> PinnedMemoryReader: ...

    def at_revision(self, revision_id: UUID) -> PinnedMemoryReader: ...


class MemoryWriter(Protocol):
    """Canonical mutation capability implemented directly by persistence."""

    def apply(self, bundle: MemoryMutationBundle) -> MutationResult: ...


class MemoryInspector(Protocol):
    """Basic canonical viewing and history capability for trusted adapters."""

    def list_items(self, query: MemoryListQuery) -> MemoryPage: ...

    def get_item(
        self,
        competition_id: UUID,
        item_id: UUID,
        revision_id: UUID | None = None,
    ) -> HydratedMemoryVersion: ...

    def item_history(self, competition_id: UUID, item_id: UUID) -> ItemHistory: ...

    def list_revisions(
        self,
        competition_id: UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> RevisionPage: ...


class MemorySearchIndexAdmin(Protocol):
    """Narrow maintenance capability implemented directly by persistence."""

    def search_index_status(self, competition_id: UUID) -> SearchIndexStatus: ...

    def rebuild_search_index(
        self,
        competition_id: UUID,
        *,
        batch_size: int = 200,
    ) -> RebuildResult: ...
