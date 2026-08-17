from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class FactVersion(Base):
    __tablename__ = "fact_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "competition_id"],
            ["memory.memory_versions.id", "memory.memory_versions.competition_id"],
            name="fk_fact_versions_version_same_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["primary_tool_call_id", "primary_tool_call_generation_id"],
            ["reporting.tool_calls.id", "reporting.tool_calls.generation_id"],
            name="fk_fact_versions_tool_call_same_generation",
            ondelete="RESTRICT",
            match="FULL",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["primary_tool_call_generation_id", "competition_id"],
            ["reporting.generations.id", "reporting.generations.competition_id"],
            name="fk_fact_versions_tool_generation_same_competition",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "ix_fact_versions_primary_tool_call",
            "primary_tool_call_id",
            "primary_tool_call_generation_id",
        ),
        Index(
            "ix_fact_versions_tool_generation_competition",
            "primary_tool_call_generation_id",
            "competition_id",
        ),
        Index("ix_fact_versions_primary_api_request", "primary_api_request_id"),
        {"schema": "memory"},
    )

    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    competition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    structured_numbers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    subjects: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    originating_event_version_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
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
    additional_source_hints: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
