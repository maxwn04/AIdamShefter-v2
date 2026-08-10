from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class MemoryItem(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        UniqueConstraint(
            "id", "competition_id", name="uq_memory_items_id_competition"
        ),
        Index("ix_memory_items_competition_kind", "competition_id", "kind"),
        Index("ix_memory_items_competition_agent_key", "competition_id", "agent_key"),
        {"schema": "memory"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    competition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.competitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    agent_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryVersion(Base):
    __tablename__ = "memory_versions"
    __table_args__ = (
        UniqueConstraint(
            "item_id", "revision_number", name="uq_memory_versions_item_revision"
        ),
        UniqueConstraint(
            "id", "competition_id", name="uq_memory_versions_id_competition"
        ),
        ForeignKeyConstraint(
            ["item_id", "competition_id"],
            ["memory.memory_items.id", "memory.memory_items.competition_id"],
            name="fk_memory_versions_item_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["introduced_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_memory_versions_introduced_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["retired_revision_id", "competition_id"],
            ["memory.memory_revisions.id", "memory.memory_revisions.competition_id"],
            name="fk_memory_versions_retired_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            [
                "core.competition_seasons.id",
                "core.competition_seasons.competition_id",
            ],
            name="fk_memory_versions_season_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["creating_generation_id", "competition_id"],
            ["reporting.generations.id", "reporting.generations.competition_id"],
            name="fk_memory_versions_generation_same_competition",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["creating_tool_call_id", "creating_generation_id"],
            ["reporting.tool_calls.id", "reporting.tool_calls.generation_id"],
            name="fk_memory_versions_tool_call_same_generation",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_memory_versions_item_revision", "item_id", "revision_number"),
        Index("ix_memory_versions_introduced_revision", "introduced_revision_id"),
        Index("ix_memory_versions_retired_revision", "retired_revision_id"),
        Index(
            "ix_memory_versions_creating_generation",
            "creating_generation_id",
            "competition_id",
        ),
        Index(
            "ix_memory_versions_creating_tool_call",
            "creating_tool_call_id",
            "creating_generation_id",
        ),
        Index(
            "ix_memory_versions_competition_season_week",
            "competition_id",
            "competition_season_id",
            "week",
        ),
        Index(
            "ix_memory_versions_season_competition",
            "competition_season_id",
            "competition_id",
        ),
        {"schema": "memory"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_schema_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    introduced_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    retired_revision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    competition_season_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creating_generation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    creating_tool_call_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
