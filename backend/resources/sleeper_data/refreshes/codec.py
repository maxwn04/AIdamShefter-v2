"""Stored-schema codecs for Sleeper refresh runs."""

from __future__ import annotations

from typing import Any

from backend.database.models.sleeper import RefreshRun as StoredRefreshRun
from backend.resources.sleeper_data.refreshes.objects import (
    PlannedEndpointScope,
    RefreshRun,
)


def encode_endpoint_scope(
    scopes: tuple[PlannedEndpointScope, ...],
) -> dict[str, Any]:
    return {"scopes": [scope.model_dump(mode="json") for scope in scopes]}


def decode_endpoint_scope(value: object) -> tuple[PlannedEndpointScope, ...]:
    if not isinstance(value, dict) or set(value) != {"scopes"}:
        raise ValueError("stored refresh endpoint scope has an invalid shape")
    raw_scopes = value["scopes"]
    if not isinstance(raw_scopes, list):
        raise ValueError("stored refresh endpoint scope must contain a list")
    return tuple(PlannedEndpointScope.model_validate(item) for item in raw_scopes)


def decode_refresh(row: StoredRefreshRun) -> RefreshRun:
    if row.competition_id is None or row.competition_season_id is None:
        raise ValueError("competition-scoped refresh is missing its identity")
    return RefreshRun.model_validate(
        {
            "id": row.id,
            "competition_id": row.competition_id,
            "competition_season_id": row.competition_season_id,
            "requested_through_week": row.requested_through_week,
            "endpoint_scope": decode_endpoint_scope(row.endpoint_scope),
            "trigger": row.trigger_source,
            "status": row.status,
            "code_version": row.code_version,
            "normalizer_version": row.normalizer_version,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "error": row.error_summary,
            "request_count": row.request_count,
            "succeeded_request_count": row.succeeded_request_count,
            "failed_request_count": row.failed_request_count,
        }
    )
