from __future__ import annotations

from typing import Generic, Literal, TypeVar
from uuid import UUID

from backend.resources._contracts import (
    ContractModel,
    DisplayName,
    NonBlankStr,
)


RoleT = TypeVar("RoleT", bound=str)


class EntityReference(ContractModel, Generic[RoleT]):
    role: RoleT
    display_name: DisplayName = None


class FranchiseRef(EntityReference[RoleT], Generic[RoleT]):
    kind: Literal["franchise"] = "franchise"
    id: UUID


class PlayerRef(EntityReference[RoleT], Generic[RoleT]):
    kind: Literal["player"] = "player"
    id: NonBlankStr


class SeasonRosterRef(EntityReference[RoleT], Generic[RoleT]):
    kind: Literal["season_roster"] = "season_roster"
    id: UUID


class SeasonRef(EntityReference[RoleT], Generic[RoleT]):
    kind: Literal["season"] = "season"
    id: UUID


class SleeperUserRef(EntityReference[RoleT], Generic[RoleT]):
    kind: Literal["sleeper_user"] = "sleeper_user"
    id: NonBlankStr
