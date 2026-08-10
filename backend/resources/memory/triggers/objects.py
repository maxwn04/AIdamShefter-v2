from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from backend.resources._contracts import NonBlankStr
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.common.versioning import MemoryContent, VersionedMemory
from backend.resources.memory.triggers.conditions.rematch import RematchCondition
from backend.resources.memory.triggers.conditions.trade_evaluation import (
    TradeEvaluationCondition,
)


class TriggerType(StrEnum):
    REMATCH = "rematch"
    TRADE_EVALUATION = "trade_evaluation"


class TriggerStatus(StrEnum):
    OPEN = "open"
    FIRED = "fired"
    SATISFIED = "satisfied"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class FirePolicy(StrEnum):
    ONE_SHOT = "one_shot"
    RECURRING = "recurring"
    UNTIL_RESOLVED = "until_resolved"


TriggerCondition = Annotated[
    RematchCondition | TradeEvaluationCondition,
    Field(discriminator="kind"),
]


class TriggerContent(MemoryContent):
    memory_kind: ClassVar[MemoryKind] = MemoryKind.TRIGGER
    schema_version: Literal[1] = 1
    trigger_type: TriggerType
    status: TriggerStatus
    fire_policy: FirePolicy
    target_competition_season_id: UUID | None = None
    target_storyline_item_id: UUID | None = None
    origin_event_item_id: UUID | None = None
    target_week: int | None = Field(default=None, ge=0, strict=True)
    target_at: AwareDatetime | None = None
    condition: TriggerCondition
    resolution_reason: NonBlankStr | None = None

    @model_validator(mode="after")
    def validate_trigger(self) -> TriggerContent:
        if self.trigger_type != self.condition.kind:
            raise ValueError("trigger type does not match condition kind")

        if isinstance(self.condition, RematchCondition):
            if self.target_competition_season_id is None or self.target_week is None:
                raise ValueError("rematch triggers require a target season and week")
        elif self.origin_event_item_id is None:
            raise ValueError("trade-evaluation triggers require an origin event")

        if (
            isinstance(self.condition, TradeEvaluationCondition)
            and self.target_week is None
            and self.target_at is None
        ):
            raise ValueError("trade-evaluation triggers require a target week or time")
        return self


Trigger = VersionedMemory[TriggerContent]
