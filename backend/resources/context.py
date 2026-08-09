"""Explicit actor and resource scope carried by every manager."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ActorKind(StrEnum):
    API = "api"
    WORKER = "worker"
    SYSTEM = "system"
    USER = "user"
    GENERATION = "generation"


@dataclass(frozen=True, slots=True)
class ManagerContext:
    """Trusted caller identity plus either competition or explicit global scope."""

    actor_kind: ActorKind
    actor_id: str
    competition_id: UUID | None
    global_reason: str | None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.actor_id.strip():
            raise ValueError("manager actor_id must not be empty")
        if (self.competition_id is None) == (self.global_reason is None):
            raise ValueError(
                "manager context requires exactly one competition or global scope"
            )
        if self.global_reason is not None and not self.global_reason.strip():
            raise ValueError("global manager scope requires a non-empty reason")
        if self.correlation_id is not None and not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty when supplied")

    @classmethod
    def competition(
        cls,
        *,
        actor_kind: ActorKind,
        actor_id: str,
        competition_id: UUID,
        correlation_id: str | None = None,
    ) -> ManagerContext:
        return cls(
            actor_kind=actor_kind,
            actor_id=actor_id,
            competition_id=competition_id,
            global_reason=None,
            correlation_id=correlation_id,
        )

    @classmethod
    def global_scope(
        cls,
        *,
        actor_kind: ActorKind,
        actor_id: str,
        reason: str,
        correlation_id: str | None = None,
    ) -> ManagerContext:
        return cls(
            actor_kind=actor_kind,
            actor_id=actor_id,
            competition_id=None,
            global_reason=reason,
            correlation_id=correlation_id,
        )

    @property
    def is_global(self) -> bool:
        return self.competition_id is None
