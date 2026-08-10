from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from backend.resources._contracts import NonBlankStr
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.common.receipts import (
    ReceiptConfidence,
    ReceiptedMemoryContent,
)
from backend.resources.memory.common.versioning import VersionedMemory
from backend.resources.memory.events.payloads.matchup import MatchupEventPayload
from backend.resources.memory.events.payloads.trade import TradeEventPayload


class EventType(StrEnum):
    TRADE = "trade"
    MATCHUP = "matchup"


EventConfidence = ReceiptConfidence


class EventStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    ARCHIVED = "archived"


EventPayload = Annotated[
    TradeEventPayload | MatchupEventPayload,
    Field(discriminator="kind"),
]


class EventContent(ReceiptedMemoryContent):
    memory_kind: ClassVar[MemoryKind] = MemoryKind.EVENT
    schema_version: Literal[1] = 1
    event_type: EventType
    headline: NonBlankStr
    summary: NonBlankStr
    salience: int = Field(ge=1, le=5, strict=True)
    status: EventStatus
    details: EventPayload

    @model_validator(mode="after")
    def validate_event(self) -> EventContent:
        if self.event_type != self.details.kind:
            raise ValueError("event type does not match payload kind")
        return self


Event = VersionedMemory[EventContent]
