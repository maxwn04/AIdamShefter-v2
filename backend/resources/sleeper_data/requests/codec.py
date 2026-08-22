"""Stored-schema and Decimal-safe payload codecs for Sleeper requests."""

from __future__ import annotations

from backend.database.models.sleeper import ApiRequest as StoredApiRequest
from backend.resources.sleeper_data.common.codec import (
    jsonb_expression,
    parse_jsonb_text,
)
from backend.resources.sleeper_data.requests.objects import ApiRequest
from backend.services.datalayer.sleeper.scope import ScopeKey


def decode_api_request(row: StoredApiRequest) -> ApiRequest:
    return ApiRequest.model_validate(
        {
            "id": row.id,
            "refresh_run_id": row.refresh_run_id,
            "competition_season_id": row.competition_season_id,
            "endpoint_kind": row.endpoint_kind,
            "scope_key": ScopeKey.parse(row.scope_key),
            "request_path": row.request_path,
            "request_parameters": row.request_parameters,
            "week": row.week,
            "bracket_kind": row.bracket_kind,
            "requested_at": row.requested_at,
            "completed_at": row.completed_at,
            "latency_ms": row.latency_ms,
            "status": row.status,
            "http_status": row.http_status,
            "error": row.error,
            "is_complete": row.is_complete,
            "completeness_reason": row.completeness_reason,
            "payload_id": row.payload_id,
            "response_sha256": row.response_sha256,
            "normalization_status": row.normalization_status,
            "normalizer_version": row.normalizer_version,
            "normalized_at": row.normalized_at,
        }
    )
