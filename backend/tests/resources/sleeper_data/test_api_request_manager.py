from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.sleeper import ApiPayload
from backend.database.sessions import create_session_factory
from backend.resources.sleeper_data.refreshes import RefreshRunManager
from backend.resources.sleeper_data.requests import (
    ApiRequestManager,
    NormalizationRejection,
    RecordApiAttempt,
    SnapshotCandidateQuery,
)
from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RequestStatus,
)
from backend.services.datalayer.errors import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
    InvalidDatalayerRequest,
)
from backend.services.datalayer.local_files import StoredLocalArtifact
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_matchups_request,
    build_player_catalog_request,
)
from backend.services.datalayer.sleeper.endpoints.contracts import CompletenessFinding
from backend.tests.resources.sleeper_data.conftest import (
    Domain,
    failed_attempt,
    manager_context,
    record_complete_attempt,
    seed_domain,
    start_refresh,
    successful_attempt,
)


def test_record_attempt_initializes_statuses_and_rejects_only_pending_successes(
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    endpoint = build_player_catalog_request()
    refresh = start_refresh(refresh_manager, domain, endpoint)
    now = datetime.now(UTC)
    complete = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        {"complete": True},
        requested_at=now,
    )
    incomplete = request_manager.record_attempt(
        RecordApiAttempt(
            refresh_run_id=refresh.id,
            attempt=successful_attempt(
                endpoint,
                {"complete": False},
                requested_at=now + timedelta(seconds=1),
            ),
            completeness=CompletenessFinding(
                is_complete=False,
                reason="catalog_incomplete",
            ),
        )
    )
    failed = request_manager.record_attempt(
        RecordApiAttempt(
            refresh_run_id=refresh.id,
            attempt=failed_attempt(
                endpoint,
                requested_at=now + timedelta(seconds=2),
            ),
            completeness=CompletenessFinding(
                is_complete=False,
                reason="source_attempt_failed",
            ),
        )
    )

    assert complete.normalization_status is NormalizationStatus.PENDING
    assert incomplete.normalization_status is NormalizationStatus.REJECTED
    assert failed.normalization_status is NormalizationStatus.NOT_APPLICABLE
    assert failed.status is RequestStatus.TRANSPORT_ERROR
    assert failed.error == {"code": "source_failed", "summary": "source failed"}

    rejection = NormalizationRejection(
        code="invalid_identity",
        summary="Payload contains an invalid identity.",
    )
    rejected = request_manager.reject_normalization(complete.id, rejection)
    assert rejected.normalization_status is NormalizationStatus.REJECTED
    assert rejected.error == {
        "stage": "normalization",
        "code": "invalid_identity",
        "summary": "Payload contains an invalid identity.",
    }
    for terminal in (incomplete, failed):
        with pytest.raises(DatalayerScopeConflict, match="pending"):
            request_manager.reject_normalization(terminal.id, rejection)
    stored = request_manager.list_refresh_requests(refresh.id)
    by_id = {request.id: request for request in stored.items}
    assert by_id[incomplete.id].normalization_status is NormalizationStatus.REJECTED
    assert by_id[failed.id].normalization_status is NormalizationStatus.NOT_APPLICABLE
    assert by_id[failed.id].error == failed.error


def test_payloads_are_deduplicated_while_request_observations_remain_distinct(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    endpoint = build_player_catalog_request()
    refresh = start_refresh(refresh_manager, domain, endpoint)
    now = datetime.now(UTC)
    payload = {"rating": Decimal("1.125")}

    first = record_complete_attempt(
        request_manager, refresh.id, endpoint, payload, requested_at=now
    )
    second = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        payload,
        requested_at=now + timedelta(seconds=1),
    )

    assert first.id != second.id
    assert first.payload_id == second.payload_id
    with database_engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(ApiPayload)) == 1
        )
    resolved = request_manager.resolve_verified_payloads([second.id, first.id])
    assert [item.request_id for item in resolved] == [second.id, first.id]
    assert all(item.kind == "inline_json" for item in resolved)
    assert resolved[0].payload == payload  # type: ignore[union-attr]


def test_refresh_request_audit_is_ordered_paginated_and_competition_scoped(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    endpoint = build_league_request(domain.season_id, domain.sleeper_league_id)
    refresh = start_refresh(refresh_manager, domain, endpoint)
    now = datetime.now(UTC)
    recorded = [
        record_complete_attempt(
            request_manager,
            refresh.id,
            endpoint,
            {"order": order},
            requested_at=now + timedelta(seconds=order),
        )
        for order in (2, 0, 1)
    ]

    page = request_manager.list_refresh_requests(refresh.id, limit=1, offset=1)
    assert page.total == 3
    assert page.items == (recorded[2],)
    with pytest.raises(InvalidDatalayerRequest, match="page"):
        request_manager.list_refresh_requests(refresh.id, limit=0)

    other = seed_domain(database_engine, label="Other")
    other_requests = ApiRequestManager(
        create_session_factory(database_engine), manager_context(other)
    )
    with pytest.raises(DatalayerResourceNotFound):
        other_requests.list_refresh_requests(refresh.id)
    with pytest.raises(DatalayerResourceNotFound):
        other_requests.resolve_verified_payloads([recorded[0].id])


def test_object_payload_resolution_returns_immutable_receipt_without_file_io(
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    endpoint = build_player_catalog_request()
    refresh = start_refresh(refresh_manager, domain, endpoint)
    attempt = successful_attempt(endpoint, {"large": True})
    receipt = StoredLocalArtifact(
        storage_key=(
            f"payloads/sha256/{attempt.raw_sha256[:2]}/" f"{attempt.raw_sha256}.json"
        ),
        sha256=attempt.raw_sha256,
        byte_length=attempt.byte_length,
    )
    request = request_manager.record_attempt(
        RecordApiAttempt(
            refresh_run_id=refresh.id,
            attempt=attempt,
            completeness=CompletenessFinding(is_complete=True),
            object_receipt=receipt,
        )
    )

    payload = request_manager.resolve_verified_payloads([request.id])[0]
    assert payload.kind == "object"
    assert payload.storage_key == receipt.storage_key  # type: ignore[union-attr]
    with pytest.raises(InvalidDatalayerRequest, match="unique"):
        request_manager.resolve_verified_payloads([request.id, request.id])


def test_snapshot_candidates_sort_newest_per_scope_and_exclude_future_weeks(
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
) -> None:
    player_catalog = build_player_catalog_request()
    week_one = build_matchups_request(domain.season_id, domain.sleeper_league_id, 1)
    week_three = build_matchups_request(domain.season_id, domain.sleeper_league_id, 3)
    refresh = start_refresh(
        refresh_manager,
        domain,
        player_catalog,
        week_one,
        week_three,
        requested_through_week=3,
    )
    now = datetime.now(UTC)
    older_player = record_complete_attempt(
        request_manager,
        refresh.id,
        player_catalog,
        {"version": 1},
        requested_at=now,
    )
    current_week = record_complete_attempt(
        request_manager,
        refresh.id,
        week_one,
        [],
        requested_at=now + timedelta(seconds=1),
    )
    newer_player = record_complete_attempt(
        request_manager,
        refresh.id,
        player_catalog,
        {"version": 2},
        requested_at=now + timedelta(seconds=2),
    )
    record_complete_attempt(
        request_manager,
        refresh.id,
        week_three,
        [],
        requested_at=now + timedelta(seconds=3),
    )

    candidates = request_manager.list_snapshot_candidates(
        SnapshotCandidateQuery(
            competition_season_id=domain.season_id,
            scope_keys=(
                player_catalog.scope_key,
                week_one.scope_key,
                week_three.scope_key,
            ),
            through_week=2,
        )
    )

    assert [item.scope_key.value for item in candidates] == sorted(
        item.scope_key.value for item in candidates
    )
    assert [
        item.request_id
        for item in candidates
        if item.scope_key == player_catalog.scope_key
    ] == [newer_player.id, older_player.id]
    assert current_week.id in {item.request_id for item in candidates}
    assert all(item.week is None or item.week <= 2 for item in candidates)
