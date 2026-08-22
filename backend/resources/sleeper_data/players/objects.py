"""Immutable player catalog resource contracts."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from backend.resources._contracts import ContractModel
from backend.resources.sleeper_data.common.objects import Page
from backend.services.datalayer.canonical_json import JsonValue


class Player(ContractModel):
    sleeper_player_id: str
    full_name: str | None
    position: str | None
    nfl_team: str | None
    active: bool | None
    status: str | None
    injury_status: str | None
    age: int | None
    years_experience: int | None
    metadata: dict[str, JsonValue]
    source_api_request_id: UUID


class PlayerSearch(ContractModel):
    text: str | None = None
    position: str | None = None
    nfl_team: str | None = None
    active: StrictBool | None = None
    limit: int = Field(default=50, strict=True, ge=1, le=200)
    offset: int = Field(default=0, strict=True, ge=0)

    @model_validator(mode="after")
    def normalize_search(self) -> "PlayerSearch":
        for name in ("text", "position", "nfl_team"):
            value = getattr(self, name)
            if value is not None and not value.strip():
                raise ValueError(f"player search {name} must not be blank")
        return self
