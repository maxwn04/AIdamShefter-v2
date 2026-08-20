"""Small immutable contracts shared by Sleeper resources."""

from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from pydantic import Field

from backend.resources._contracts import ContractModel

PositiveLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
NonNegativeOffset = Annotated[int, Field(strict=True, ge=0)]

ItemT = TypeVar("ItemT")


class Page(ContractModel, Generic[ItemT]):
    items: tuple[ItemT, ...]
    total: int = Field(strict=True, ge=0)
    limit: PositiveLimit
    offset: NonNegativeOffset
