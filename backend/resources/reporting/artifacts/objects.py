"""Immutable commands and views for durable artifact identities."""

from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Annotated, Any
from uuid import UUID

from pydantic import AwareDatetime, BeforeValidator, Field

from backend.resources._contracts import ContractModel


PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
_MEDIA_TYPE = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$"
)


def _artifact_path(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if not value or value != value.strip():
        raise ValueError("artifact path must be a non-empty normalized string")
    if "\x00" in value or "\\" in value:
        raise ValueError("artifact path must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise ValueError("artifact path must be a normalized relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("artifact path cannot contain dot segments")
    if not path.parts or ":" in path.parts[0]:
        raise ValueError("artifact path must be relative to the artifact workspace")
    return value


def _media_type(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = value.strip().lower()
    if _MEDIA_TYPE.fullmatch(value) is None:
        raise ValueError("media_type must be a normalized IANA media type")
    return value


ArtifactPath = Annotated[str, BeforeValidator(_artifact_path)]
MediaType = Annotated[str, BeforeValidator(_media_type)]


class CreateArtifact(ContractModel):
    generation_id: UUID
    path: ArtifactPath
    media_type: MediaType


class FinalizeArtifact(ContractModel):
    artifact_id: UUID
    artifact_version_id: UUID


class ArtifactQuery(ContractModel):
    generation_id: UUID
    finalized: bool | None = None
    limit: PageLimit = 50
    offset: NonNegativeInt = 0


class Artifact(ContractModel):
    id: UUID
    generation_id: UUID
    path: str
    media_type: str
    finalized_version_id: UUID | None
    finalized_at: AwareDatetime | None
    created_at: AwareDatetime


class ArtifactSummary(Artifact):
    revision_count: NonNegativeInt
    latest_version_at: AwareDatetime | None


class ArtifactPage(ContractModel):
    items: tuple[ArtifactSummary, ...]
    total: NonNegativeInt
    limit: PageLimit
    offset: NonNegativeInt


__all__ = [
    "Artifact",
    "ArtifactPage",
    "ArtifactPath",
    "ArtifactQuery",
    "ArtifactSummary",
    "CreateArtifact",
    "FinalizeArtifact",
    "MediaType",
]
