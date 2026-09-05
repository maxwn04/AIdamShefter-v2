"""Sleeper request audit and content-addressed payload models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class RefreshRun(Base):
    __tablename__ = "refresh_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            ["core.competition_seasons.id", "core.competition_seasons.competition_id"],
            name="fk_refresh_runs_season_competition",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id",
            "competition_season_id",
            name="uq_refresh_runs_id_competition_season",
        ),
        Index("ix_refresh_runs_competition_started", "competition_id", text("started_at DESC")),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("core.competitions.id", ondelete="RESTRICT")
    )
    competition_season_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requested_through_week: Mapped[int | None] = mapped_column(SmallInteger)
    endpoint_scope: Mapped[dict[str, Any]] = mapped_column(JSONB)
    trigger_source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    code_version: Mapped[str] = mapped_column(Text)
    normalizer_version: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    succeeded_request_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )
    failed_request_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class ApiPayload(Base):
    __tablename__ = "api_payloads"
    __table_args__ = (
        UniqueConstraint("sha256_hash", name="uq_api_payloads_sha256_hash"),
        UniqueConstraint("id", "sha256_hash", name="uq_api_payloads_id_hash"),
        CheckConstraint(
            "(storage_kind = 'inline_json' AND inline_payload IS NOT NULL "
            "AND object_storage_key IS NULL) OR "
            "(storage_kind = 'object' AND inline_payload IS NULL "
            "AND object_storage_key IS NOT NULL)",
            name="exactly_one_location",
        ),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sha256_hash: Mapped[str] = mapped_column(Text)
    byte_length: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(Text)
    storage_kind: Mapped[str] = mapped_column(Text)
    inline_payload: Mapped[Any | None] = mapped_column(JSONB)
    object_storage_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApiRequest(Base):
    __tablename__ = "api_requests"
    __table_args__ = (
        UniqueConstraint("id", "scope_key", name="uq_api_requests_id_scope"),
        UniqueConstraint(
            "id",
            "competition_season_id",
            name="uq_api_requests_id_competition_season",
        ),
        UniqueConstraint(
            "id", "scope_key", "response_sha256", name="uq_api_requests_id_scope_hash"
        ),
        ForeignKeyConstraint(
            ["refresh_run_id", "competition_season_id"],
            ["sleeper.refresh_runs.id", "sleeper.refresh_runs.competition_season_id"],
            name="fk_api_requests_refresh_run_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["refresh_run_id"],
            ["sleeper.refresh_runs.id"],
            name="fk_api_requests_refresh_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["payload_id", "response_sha256"],
            ["sleeper.api_payloads.id", "sleeper.api_payloads.sha256_hash"],
            name="fk_api_requests_verified_payload",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["payload_id"],
            ["sleeper.api_payloads.id"],
            name="fk_api_requests_payload",
            ondelete="RESTRICT",
        ),
        Index("ix_api_requests_refresh_run", "refresh_run_id"),
        Index(
            "ix_api_requests_eligible_scope_completed",
            "scope_key",
            text("completed_at DESC"),
            postgresql_where=text("status = 'succeeded' AND is_complete"),
        ),
        Index(
            "ix_api_requests_season_endpoint_week",
            "competition_season_id",
            "endpoint_kind",
            "week",
        ),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    refresh_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    competition_season_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.competition_seasons.id", ondelete="RESTRICT"),
    )
    endpoint_kind: Mapped[str] = mapped_column(Text)
    scope_key: Mapped[str] = mapped_column(Text)
    request_path: Mapped[str] = mapped_column(Text)
    request_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    week: Mapped[int | None] = mapped_column(SmallInteger)
    bracket_kind: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_complete: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    completeness_reason: Mapped[str | None] = mapped_column(Text)
    payload_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    response_sha256: Mapped[str | None] = mapped_column(Text)
    normalization_status: Mapped[str] = mapped_column(
        Text, server_default=text("'pending'")
    )
    normalizer_version: Mapped[str | None] = mapped_column(Text)
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NormalizedScope(Base):
    __tablename__ = "normalized_scopes"
    __table_args__ = (
        UniqueConstraint(
            "source_api_request_id", name="uq_normalized_scopes_source_request"
        ),
        ForeignKeyConstraint(
            ["source_api_request_id", "scope_key", "response_sha256"],
            [
                "sleeper.api_requests.id",
                "sleeper.api_requests.scope_key",
                "sleeper.api_requests.response_sha256",
            ],
            name="fk_normalized_scopes_request_scope_hash",
            ondelete="RESTRICT",
        ),
        {"schema": "sleeper"},
    )

    scope_key: Mapped[str] = mapped_column(Text, primary_key=True)
    source_api_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    response_sha256: Mapped[str] = mapped_column(Text)
    normalized_row_count: Mapped[int] = mapped_column(Integer)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AutomaticRefreshClaim(Base):
    __tablename__ = "automatic_refresh_claims"
    __table_args__ = (
        ForeignKeyConstraint(
            ["competition_season_id", "competition_id"],
            ["core.competition_seasons.id", "core.competition_seasons.competition_id"],
            name="fk_automatic_refresh_claims_season_competition",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["refresh_run_id", "competition_season_id"],
            ["sleeper.refresh_runs.id", "sleeper.refresh_runs.competition_season_id"],
            name="fk_automatic_refresh_claims_refresh_season",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "requested_through_week BETWEEN 1 AND 18",
            name="through_week",
        ),
        CheckConstraint("reason IN ('missing', 'stale')", name="reason"),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="status",
        ),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL "
            "AND refresh_run_id IS NULL AND refresh_status IS NULL "
            "AND failure_summary IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND refresh_run_id IS NOT NULL AND refresh_status IS NOT NULL "
            "AND failure_summary IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL "
            "AND refresh_status IS NULL AND failure_summary IS NOT NULL)",
            name="terminal_shape",
        ),
        Index(
            "uq_automatic_refresh_claims_active_key",
            "competition_id",
            "active_key",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        Index(
            "ix_automatic_refresh_claims_season_started",
            "competition_season_id",
            "started_at",
        ),
        {"schema": "sleeper"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    competition_season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    active_key: Mapped[str] = mapped_column(Text)
    requested_through_week: Mapped[int] = mapped_column(SmallInteger)
    policy_version: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    coverage_fingerprint: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    refresh_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    refresh_status: Mapped[str | None] = mapped_column(Text)
    failure_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
