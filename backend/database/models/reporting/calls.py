from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class AICall(Base):
    __tablename__ = "ai_calls"
    __table_args__ = (
        UniqueConstraint(
            "id", "generation_id", name="uq_ai_calls_id_generation"
        ),
        UniqueConstraint(
            "generation_id",
            "turn_number",
            "attempt_number",
            name="uq_ai_calls_generation_turn_attempt",
        ),
        Index(
            "uq_ai_calls_one_success_per_turn",
            "generation_id",
            "turn_number",
            unique=True,
            postgresql_where=text("status = 'succeeded'"),
        ),
        Index(
            "ix_ai_calls_generation_turn_attempt",
            "generation_id",
            "turn_number",
            "attempt_number",
        ),
        Index("ix_ai_calls_actual_model_completed", "actual_model", "completed_at"),
        {"schema": "reporting"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("reporting.generations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    turn_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    requested_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_model: Mapped[str] = mapped_column(Text, nullable=False)
    actual_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_messages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    tool_definitions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    request_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provider_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_response_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    raw_provider_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint(
            "id", "generation_id", name="uq_tool_calls_id_generation"
        ),
        UniqueConstraint(
            "ai_call_id", "tool_ordinal", name="uq_tool_calls_ai_call_ordinal"
        ),
        ForeignKeyConstraint(
            ["ai_call_id", "generation_id"],
            ["reporting.ai_calls.id", "reporting.ai_calls.generation_id"],
            name="fk_tool_calls_ai_call_same_generation",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_tool_calls_generation_ai_ordinal",
            "generation_id",
            "ai_call_id",
            "tool_ordinal",
        ),
        Index("ix_tool_calls_name_started", "tool_name", "started_at"),
        {"schema": "reporting"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("reporting.generations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ai_call_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tool_ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    provider_tool_call_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_version: Mapped[str] = mapped_column(Text, nullable=False)
    arguments_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    full_result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_result_jsonb: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
