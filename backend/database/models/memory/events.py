from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class EventVersion(Base):
    __tablename__ = "event_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "competition_id"],
            ["memory.memory_versions.id", "memory.memory_versions.competition_id"],
            name="fk_event_versions_version_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["primary_tool_call_id", "primary_tool_call_generation_id"],
            ["reporting.tool_calls.id", "reporting.tool_calls.generation_id"],
            name="fk_event_versions_tool_call_same_generation",
            ondelete="RESTRICT",
            match="FULL",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["primary_tool_call_generation_id", "competition_id"],
            ["reporting.generations.id", "reporting.generations.competition_id"],
            name="fk_event_versions_tool_generation_same_competition",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "ix_event_versions_primary_tool_call",
            "primary_tool_call_id",
            "primary_tool_call_generation_id",
        ),
        Index(
            "ix_event_versions_tool_generation_competition",
            "primary_tool_call_generation_id",
            "competition_id",
        ),
        Index("ix_event_versions_primary_api_request", "primary_api_request_id"),
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    salience: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    additional_source_hints: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    primary_tool_call_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    primary_tool_call_generation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    primary_api_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sleeper.api_requests.id", ondelete="RESTRICT"),
        nullable=True,
    )
