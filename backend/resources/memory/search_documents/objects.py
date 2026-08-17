from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from backend.resources._contracts import ContractModel, NonBlankStr
from backend.resources.memory.common.kinds import MemoryKind


Sha256Hex = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]


class SearchDocumentProjection(ContractModel):
    """Identity-free searchable fields derived from one typed memory version."""

    kind: MemoryKind
    status: NonBlankStr | None = None
    salience: int | None = Field(default=None, ge=1, le=5, strict=True)
    entity_keys: tuple[NonBlankStr, ...] = ()
    evidence_version_ids: tuple[UUID, ...] = ()
    related_item_ids: tuple[UUID, ...] = ()
    tags: tuple[NonBlankStr, ...] = ()
    document_text: NonBlankStr
    builder_version: int = Field(gt=0, strict=True)
    content_hash: Sha256Hex


class SearchMatchReason(StrEnum):
    ENTITY_OVERLAP = "entity_overlap"
    EVIDENCE_OVERLAP = "evidence_overlap"
    RELATED_ITEM_OVERLAP = "related_item_overlap"
    TAG_OVERLAP = "tag_overlap"
    LEXICAL_MATCH = "lexical_match"
    BROWSE_MATCH = "browse_match"


class SearchDocumentQuery(ContractModel):
    """Revision-grounded discovery signals and structured result filters."""

    entity_keys: tuple[NonBlankStr, ...] = ()
    evidence_version_ids: tuple[UUID, ...] = ()
    related_item_ids: tuple[UUID, ...] = ()
    tags: tuple[NonBlankStr, ...] = ()
    text: NonBlankStr | None = None
    kinds: tuple[MemoryKind, ...] = ()
    statuses: tuple[NonBlankStr, ...] = ()
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0, strict=True)
    limit: int = Field(default=20, ge=1, le=100, strict=True)

    @field_validator(
        "entity_keys",
        "evidence_version_ids",
        "related_item_ids",
        "kinds",
        "statuses",
        mode="after",
    )
    @classmethod
    def _deduplicate_values(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(dict.fromkeys(values))

    @field_validator("tags", mode="after")
    @classmethod
    def _normalize_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value.casefold() for value in values))

    @property
    def has_discovery_signals(self) -> bool:
        return bool(
            self.entity_keys
            or self.evidence_version_ids
            or self.related_item_ids
            or self.tags
            or self.text
        )


class SearchScoreComponents(ContractModel):
    entity_overlap: float = Field(default=0.0, ge=0)
    evidence_overlap: float = Field(default=0.0, ge=0)
    related_item_overlap: float = Field(default=0.0, ge=0)
    tag_overlap: float = Field(default=0.0, ge=0)
    lexical_rank: float = Field(default=0.0, ge=0)
    salience: float = Field(default=0.0, ge=0)

    @property
    def total(self) -> float:
        return (
            self.entity_overlap
            + self.evidence_overlap
            + self.related_item_overlap
            + self.tag_overlap
            + self.lexical_rank
            + self.salience
        )


class SearchDocumentCandidate(ContractModel):
    """Compact projection match; canonical content is deliberately absent."""

    version_id: UUID
    item_id: UUID
    kind: MemoryKind
    status: NonBlankStr | None = None
    salience: int | None = Field(default=None, ge=1, le=5, strict=True)
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0, strict=True)
    score: float = Field(ge=0)
    score_components: SearchScoreComponents
    matched_entity_keys: tuple[NonBlankStr, ...] = ()
    matched_evidence_version_ids: tuple[UUID, ...] = ()
    matched_related_item_ids: tuple[UUID, ...] = ()
    matched_tags: tuple[NonBlankStr, ...] = ()
    match_reasons: tuple[SearchMatchReason, ...]


class SearchProjectionRebuildResult(ContractModel):
    competition_id: UUID
    canonical_revision_id: UUID
    documents_rebuilt: int = Field(ge=0, strict=True)
