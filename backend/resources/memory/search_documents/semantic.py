"""Narrow semantic strategy contract; eligibility belongs to search queries."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EmbeddingDocument:
    version_id: UUID
    document_text: str
    content_hash: str
    builder_version: int


@dataclass(frozen=True, slots=True)
class SemanticSearchResult:
    scores: dict[UUID, float] = field(default_factory=dict)
    status: Literal["ready", "disabled", "unavailable", "partial", "stale"] = "disabled"
    missing_count: int = 0
    stale_count: int = 0
    total_count: int = 0
    available_count: int = 0
    reason: str | None = None


class SemanticScorer(Protocol):
    def score(
        self, query: str, documents: Sequence[EmbeddingDocument],
    ) -> SemanticSearchResult: ...
