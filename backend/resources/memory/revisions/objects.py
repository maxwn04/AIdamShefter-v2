from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.resources._contracts import ContractModel, NonBlankStr


class CanonicalRevision(ContractModel):
    """One immutable competition-wide canonical memory state."""

    revision_id: UUID
    competition_id: UUID
    sequence_number: int = Field(ge=0, strict=True)
    previous_revision_id: UUID | None = None
    producing_generation_id: UUID | None = None
    competition_season_id: UUID | None = None
    week: int | None = Field(default=None, ge=0, strict=True)
    knowledge_cutoff_at: AwareDatetime | None = None
    state_content_hash: NonBlankStr
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_linear_position(self) -> CanonicalRevision:
        if self.sequence_number == 0 and self.previous_revision_id is not None:
            raise ValueError("root revision cannot have a previous revision")
        if self.sequence_number > 0 and self.previous_revision_id is None:
            raise ValueError("non-root revision requires a previous revision")
        return self
