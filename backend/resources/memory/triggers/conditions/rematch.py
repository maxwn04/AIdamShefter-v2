from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import model_validator

from backend.resources._contracts import ContractModel


class RematchCondition(ContractModel):
    kind: Literal["rematch"] = "rematch"
    franchise_ids: tuple[UUID, UUID]

    @model_validator(mode="after")
    def validate_franchises(self) -> RematchCondition:
        if self.franchise_ids[0] == self.franchise_ids[1]:
            raise ValueError("rematch franchises must differ")
        return self
