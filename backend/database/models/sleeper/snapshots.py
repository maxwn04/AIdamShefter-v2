"""Immutable frozen factual snapshot metadata models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    CheckConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class DataSnapshot(Base):
    __tablename__ = "data_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["primary_competition_season_id", "competition_id"],
            ["core.competition_seasons.id", "core.competition_seasons.competition_id"],
            name="fk_data_snapshots_primary_season_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "competition_id", name="uq_data_snapshots_id_competition"),
        UniqueConstraint(
            "id",
            "primary_competition_season_id",
            name="uq_data_snapshots_id_primary_season",
        ),
        Index(
            "ix_data_snapshots_season_as_of_created",
            "primary_competition_season_id",
            "as_of_date",
            "created_at",
        ),
        Index(
            "uq_data_snapshots_active_build_key",
            "build_key",
            unique=True,
            postgresql_where=text("status IN ('building', 'ready')"),
        ),
        Index("ix_data_snapshots_competition_status", "competition_id", "status"),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.competitions.id", ondelete="RESTRICT")
    )
    primary_competition_season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    build_key: Mapped[str] = mapped_column(Text)
    input_revision: Mapped[str | None] = mapped_column(Text)
    domain_cutoff_week: Mapped[int | None] = mapped_column(SmallInteger)
    domain_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    as_of_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text)
    snapshot_projection_version: Mapped[str] = mapped_column(Text)
    code_version: Mapped[str] = mapped_column(Text)
    completeness_warnings: Mapped[list[Any]] = mapped_column(JSONB)
    failure_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sqlite_artifact_sha256: Mapped[str | None] = mapped_column(Text)
    sqlite_artifact_byte_length: Mapped[int | None] = mapped_column(BigInteger)
    sqlite_artifact_storage_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataSnapshotRequest(Base):
    __tablename__ = "data_snapshot_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["api_request_id", "scope_key", "response_sha256"],
            [
                "sleeper.api_requests.id",
                "sleeper.api_requests.scope_key",
                "sleeper.api_requests.response_sha256",
            ],
            name="fk_data_snapshot_requests_request_scope_hash",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "data_snapshot_id", "scope_key", name="uq_data_snapshot_requests_snapshot_scope"
        ),
        Index("ix_data_snapshot_requests_api_request", "api_request_id"),
        {"schema": "sleeper"},
    )

    data_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sleeper.data_snapshots.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    api_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    scope_key: Mapped[str] = mapped_column(Text)
    response_sha256: Mapped[str] = mapped_column(Text)
    selection_role: Mapped[str] = mapped_column(Text)


class DataSnapshotSeason(Base):
    __tablename__ = "data_snapshot_seasons"
    __table_args__ = (
        CheckConstraint(
            "role IN ('primary', 'history')",
            name="role",
        ),
        CheckConstraint(
            "through_week BETWEEN 1 AND 18",
            name="through_week",
        ),
        CheckConstraint(
            "role <> 'primary' OR competition_season_id = primary_competition_season_id",
            name="primary_matches",
        ),
        ForeignKeyConstraint(
            ["data_snapshot_id", "competition_id"],
            ["sleeper.data_snapshots.id", "sleeper.data_snapshots.competition_id"],
            name="fk_data_snapshot_seasons_snapshot_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["data_snapshot_id", "primary_competition_season_id"],
            [
                "sleeper.data_snapshots.id",
                "sleeper.data_snapshots.primary_competition_season_id",
            ],
            name="fk_data_snapshot_seasons_snapshot_primary",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            ["core.competition_seasons.id", "core.competition_seasons.competition_id"],
            name="fk_data_snapshot_seasons_season_competition",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_data_snapshot_seasons_primary",
            "data_snapshot_id",
            unique=True,
            postgresql_where=text("role = 'primary'"),
        ),
        Index(
            "ix_data_snapshot_seasons_season_snapshot",
            "competition_season_id",
            "data_snapshot_id",
        ),
        {"schema": "sleeper"},
    )

    data_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    primary_competition_season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    competition_season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text)
    through_week: Mapped[int] = mapped_column(SmallInteger)
