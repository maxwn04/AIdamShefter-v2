from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class TriggerVersion(Base):
    __tablename__ = "trigger_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "competition_id"],
            ["memory.memory_versions.id", "memory.memory_versions.competition_id"],
            name="fk_trigger_versions_version_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_trigger_versions_target_same_competition",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_trigger_versions_target_season_competition",
            "target_competition_season_id",
            "competition_id",
        ),
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    fire_policy: Mapped[str] = mapped_column(Text, nullable=False)
    target_competition_season_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    target_storyline_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    origin_event_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    target_week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    target_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
