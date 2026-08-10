from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import model_validator

from backend.resources._contracts import ContractModel, NonBlankStr


class MatchupEventPayload(ContractModel):
    kind: Literal["matchup"] = "matchup"
    winner_franchise_id: UUID
    loser_franchise_id: UUID
    sleeper_matchup_id: NonBlankStr

    @model_validator(mode="after")
    def validate_matchup(self) -> MatchupEventPayload:
        if self.winner_franchise_id == self.loser_franchise_id:
            raise ValueError("matchup winner and loser must differ")
        return self
