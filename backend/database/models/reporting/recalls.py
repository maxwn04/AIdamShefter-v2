from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class GenerationMemoryRecall(Base):
    __tablename__ = "generation_memory_recalls"
    __table_args__ = (
        CheckConstraint(
            "status IN ('complete', 'partial', 'failed')",
            name="status",
        ),
        {"schema": "reporting"},
    )

    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("reporting.generations.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    result_jsonb: Mapped[Any] = mapped_column(JSONB, nullable=False)
    result_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_jsonb: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
