from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import Field

from backend.resources._contracts import ContractModel, NonBlankStr


class LocalUserActor(ContractModel):
    kind: Literal["local_user"] = "local_user"


class SystemProcessActor(ContractModel):
    kind: Literal["system_process"] = "system_process"
    process_name: NonBlankStr


class GenerationActor(ContractModel):
    kind: Literal["generation"] = "generation"
    generation_id: UUID


Actor = Annotated[
    LocalUserActor | SystemProcessActor | GenerationActor,
    Field(discriminator="kind"),
]


class CompetitionScope(ContractModel):
    kind: Literal["competition"] = "competition"
    competition_id: UUID


class GlobalScope(ContractModel):
    kind: Literal["global"] = "global"
    reason: NonBlankStr


ScopeT = TypeVar("ScopeT", CompetitionScope, GlobalScope)


class ManagerContext(ContractModel, Generic[ScopeT]):
    actor: Actor
    scope: ScopeT
    correlation_id: UUID
