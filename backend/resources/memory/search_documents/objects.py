from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

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
