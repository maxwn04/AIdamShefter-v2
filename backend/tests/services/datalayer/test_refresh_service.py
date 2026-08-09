from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.json import JsonValue, canonical_json_bytes
from backend.resources.errors import ResourceReferenceUnavailable
from backend.resources.sleeper_data.objects import (
    ApiRequest,
    ApplyDisposition as ResourceApplyDisposition,
    ApplyResult,
    ApplyScopeRecords,
    BracketScopeRecords,
    ExpandRefreshPlan,
    NormalizationRejection,
    NormalizationStatus as ResourceNormalizationStatus,
    RecordApiAttempt,
    RefreshFailure,
    RefreshRun,
    RefreshScopePlan,
    RefreshStatus as ResourceRefreshStatus,
    RequestStatus as ResourceRequestStatus,
    RostersScopeRecords,
    SeasonIdentityMap,
    SeasonRosterIdentity,
    StartRefresh,
    TradedPicksScopeRecords,
)
from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RefreshRequest,
    RefreshStatus,
    RefreshTrigger,
)
from backend.services.datalayer.errors import InternalDatalayerFailure
from backend.services.datalayer.local_files import LocalDatalayerFileStore
from backend.services.datalayer.refresh_service import (
    DatalayerRefreshService,
    _build_base_plan,
    _build_weekly_plan,
)
from backend.services.datalayer.sleeper.responses import (
    EndpointRequest,
    FailedSourceAttempt,
    SanitizedSourceError,
    SourceAttempt,
    SuccessfulSourceAttempt,
)
from backend.sleeper import EndpointKind

NOW = datetime(2024, 10, 1, tzinfo=timezone.utc)
COMPETITION_ID = UUID("10000000-0000-0000-0000-000000000001")
SEASON_ID = UUID("20000000-0000-0000-0000-000000000001")
SEASON_ROSTER_ID = UUID("30000000-0000-0000-0000-000000000001")
FRANCHISE_ID = UUID("40000000-0000-0000-0000-000000000001")


class FakeSourceClient:
    def __init__(
        self,
        *,
        failures: set[EndpointKind] | None = None,
        raises: dict[EndpointKind, BaseException] | None = None,
        state_payload: JsonValue | None = None,
    ) -> None:
        self.failures = failures or set()
        self.raises = raises or {}
        self.state_payload = state_payload or {"season": "2024", "week": 2}
        self.requests: list[EndpointRequest] = []

    def execute(self, request: EndpointRequest) -> SourceAttempt:
        self.requests.append(request)
        if error := self.raises.get(request.endpoint_kind):
            raise error
        if request.endpoint_kind in self.failures:
            return FailedSourceAttempt(
                endpoint=request,
                requested_at=NOW,
                completed_at=NOW,
                latency_ms=1,
                status="transport_error",
                http_status=None,
                error=SanitizedSourceError(
                    code="test_transport_error",
                    summary="Test source failed",
                ),
            )
        return _success(request, _payload(request, state_payload=self.state_payload))


class FakeSleeperDataManager:
    def __init__(
        self,
        identity: SeasonIdentityMap,
        *,
        reference_failures: set[EndpointKind] | None = None,
    ) -> None:
        self.identity = identity
        self.reference_failures = reference_failures or set()
        self.refresh: RefreshRun | None = None
        self.requests: dict[UUID, ApiRequest] = {}
        self.commands: list[RecordApiAttempt] = []
        self.applied: list[ApplyScopeRecords] = []
        self.rejections: list[NormalizationRejection] = []
        self.expansions: list[ExpandRefreshPlan] = []
        self.finish_calls: list[tuple[bool, RefreshFailure | None]] = []
        self.events: list[str] = []

    def get_season_identity_map(self, competition_season_id: UUID) -> SeasonIdentityMap:
        assert competition_season_id == self.identity.competition_season_id
        return self.identity

    def start_refresh(self, command: StartRefresh) -> RefreshRun:
        self.events.append("start")
        self.refresh = _refresh_run(
            plan=command.endpoint_plan,
            through_week=command.requested_through_week,
        )
        return self.refresh

    def expand_refresh_plan(
        self,
        refresh_id: UUID,
        command: ExpandRefreshPlan,
    ) -> RefreshRun:
        assert self.refresh is not None and refresh_id == self.refresh.id
        self.events.append("expand")
        self.expansions.append(command)
        self.refresh = replace(
            self.refresh,
            effective_through_week=command.effective_through_week,
            endpoint_plan=(*self.refresh.endpoint_plan, *command.remaining_scopes),
        )
        return self.refresh

    def record_attempt(self, command: RecordApiAttempt) -> ApiRequest:
        assert self.refresh is not None
        self.events.append(f"record:{command.endpoint_kind}")
        self.commands.append(command)
        normalization_status = (
            ResourceNormalizationStatus.PENDING
            if command.status is ResourceRequestStatus.SUCCEEDED
            and command.completeness.is_complete
            else ResourceNormalizationStatus.NOT_APPLICABLE
        )
        request = ApiRequest(
            id=uuid4(),
            refresh_run_id=self.refresh.id,
            competition_season_id=command.competition_season_id,
            endpoint_kind=command.endpoint_kind,
            scope_key=command.scope_key,
            request_path=command.request_path,
            request_parameters=command.request_parameters,
            week=command.week,
            bracket_kind=command.bracket_kind,
            requested_at=command.requested_at,
            completed_at=command.completed_at,
            latency_ms=command.latency_ms,
            status=command.status,
            http_status=command.http_status,
            error=command.error,
            is_complete=command.completeness.is_complete,
            completeness_reason=command.completeness.code,
            response_sha256=(command.payload.sha256 if command.payload else None),
            normalization_status=normalization_status,
            normalizer_version=None,
            normalized_at=None,
        )
        self.requests[request.id] = request
        return request

    def reject_normalization(
        self,
        request_id: UUID,
        rejection: NormalizationRejection,
    ) -> ApiRequest:
        self.rejections.append(rejection)
        request = replace(
            self.requests[request_id],
            normalization_status=ResourceNormalizationStatus.REJECTED,
        )
        self.requests[request_id] = request
        return request

    def apply_scope(
        self,
        request_id: UUID,
        records: ApplyScopeRecords,
    ) -> ApplyResult:
        request = self.requests[request_id]
        if EndpointKind(request.endpoint_kind) in self.reference_failures:
            raise ResourceReferenceUnavailable("private missing reference")
        self.applied.append(records)
        request = replace(
            request,
            normalization_status=ResourceNormalizationStatus.SUCCEEDED,
        )
        self.requests[request_id] = request
        return ApplyResult(
            disposition=ResourceApplyDisposition.APPLIED,
            request_id=request_id,
            scope_key=request.scope_key,
            normalized_row_count=1,
        )

    def finish_refresh(
        self,
        refresh_id: UUID,
        *,
        cancelled: bool = False,
        failure: RefreshFailure | None = None,
    ) -> RefreshRun:
        assert self.refresh is not None and refresh_id == self.refresh.id
        self.events.append("finish")
        self.finish_calls.append((cancelled, failure))
        succeeded = 0
        failed = 0
        latest = {request.scope_key: request for request in self.requests.values()}
        for planned in self.refresh.endpoint_plan:
            request = latest.get(planned.scope_key)
            if (
                request is not None
                and request.status is ResourceRequestStatus.SUCCEEDED
                and request.is_complete
                and request.normalization_status
                is ResourceNormalizationStatus.SUCCEEDED
            ):
                succeeded += 1
            elif not cancelled or request is not None:
                failed += 1
        if cancelled:
            status = ResourceRefreshStatus.CANCELLED
        elif failure is not None:
            status = (
                ResourceRefreshStatus.PARTIAL
                if succeeded
                else ResourceRefreshStatus.FAILED
            )
        elif failed and succeeded:
            status = ResourceRefreshStatus.PARTIAL
        elif failed:
            status = ResourceRefreshStatus.FAILED
        else:
            status = ResourceRefreshStatus.SUCCEEDED
        self.refresh = replace(
            self.refresh,
            status=status,
            completed_at=NOW,
            attempt_count=len(self.requests),
            succeeded_scope_count=succeeded,
            failed_scope_count=failed,
        )
        return self.refresh


def test_standard_plan_is_stable_and_dependencies_match_actual_foreign_keys() -> None:
    identity = _identity()
    base = _build_base_plan(identity)
    weekly = _build_weekly_plan(identity, through_week=2)

    assert [item.request.endpoint_kind for item in base] == [
        EndpointKind.LEAGUE,
        EndpointKind.NFL_STATE,
        EndpointKind.LEAGUE_USERS,
        EndpointKind.PLAYER_CATALOG,
        EndpointKind.LEAGUE_ROSTERS,
        EndpointKind.TRADED_PICKS,
        EndpointKind.WINNERS_BRACKET,
        EndpointKind.LOSERS_BRACKET,
    ]
    assert tuple(map(str, base[4].dependency_scope_keys)) == (
        f"users:{SEASON_ID}",
        "players:nfl",
    )
    assert all(item.dependency_scope_keys == () for item in (*base[:4], *base[5:]))
    assert [item.request.endpoint_kind for item in weekly] == [
        EndpointKind.MATCHUPS,
        EndpointKind.TRANSACTIONS,
        EndpointKind.MATCHUPS,
        EndpointKind.TRANSACTIONS,
    ]
    assert all(tuple(map(str, item.dependency_scope_keys)) == ("players:nfl",) for item in weekly)


def test_explicit_refresh_records_applies_and_finalizes_the_full_plan(tmp_path: Path) -> None:
    source = FakeSourceClient()
    manager = FakeSleeperDataManager(_identity())
    service = _service(source, manager, tmp_path)

    outcome = service.refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=2,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.SUCCEEDED
    assert outcome.requested_scope_count == 12
    assert len(source.requests) == len(manager.commands) == len(manager.applied) == 12
    assert manager.expansions == []
    assert manager.refresh is not None
    assert manager.refresh.effective_through_week == 2
    assert manager.commands[0].payload is not None
    assert manager.commands[0].payload.inline_json_text is not None
    assert manager.commands[0].payload.local_storage_key is None
    roster_scope = next(row for row in manager.applied if isinstance(row, RostersScopeRecords))
    assert len(roster_scope.draft_pick_seeds) == 6
    assert {row.draft_season_year for row in roster_scope.draft_pick_seeds} == {
        2025,
        2026,
        2027,
    }
    assert sum(isinstance(row, BracketScopeRecords) for row in manager.applied) == 2
    assert any(
        isinstance(row, TradedPicksScopeRecords) and row.picks == ()
        for row in manager.applied
    )


def test_omitted_week_expands_only_after_full_base_plan_is_recorded(tmp_path: Path) -> None:
    source = FakeSourceClient(state_payload={"season": "2024", "week": 2})
    manager = FakeSleeperDataManager(_identity())

    outcome = _service(source, manager, tmp_path).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=None,
            trigger=RefreshTrigger.SCHEDULED,
        )
    )

    assert outcome.status is RefreshStatus.SUCCEEDED
    assert len(manager.expansions) == 1
    assert manager.expansions[0].effective_through_week == 2
    assert len(manager.expansions[0].remaining_scopes) == 4
    assert manager.events.index("expand") > max(
        index
        for index, event in enumerate(manager.events)
        if event.startswith("record:") and "matchups" not in event and "transactions" not in event
    )


def test_missing_effective_week_keeps_independent_base_work_and_finishes_partial(
    tmp_path: Path,
) -> None:
    source = FakeSourceClient(failures={EndpointKind.NFL_STATE})
    manager = FakeSleeperDataManager(_identity())

    outcome = _service(source, manager, tmp_path).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=None,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert len(source.requests) == 8
    assert manager.expansions == []
    assert outcome.status is RefreshStatus.PARTIAL
    assert manager.finish_calls[-1][1] == RefreshFailure(
        code="effective_week_unavailable",
        summary="Weekly scopes could not be planned from current NFL state",
    )
    state_result = next(
        result for result in outcome.scope_results if str(result.scope_key) == "state:nfl"
    )
    assert "weekly_plan_omitted_nfl_state_unavailable" in state_result.warning_codes


def test_explicit_week_allows_refreshing_a_historical_season(tmp_path: Path) -> None:
    source = FakeSourceClient(state_payload={"season": "2025", "week": 8})
    manager = FakeSleeperDataManager(_identity())

    outcome = _service(source, manager, tmp_path).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.BACKFILL,
        )
    )

    assert outcome.status is RefreshStatus.SUCCEEDED
    assert manager.expansions == []
    assert manager.refresh is not None
    assert manager.refresh.effective_through_week == 1


def test_omitted_week_rejects_a_current_state_from_another_season(
    tmp_path: Path,
) -> None:
    source = FakeSourceClient(state_payload={"season": "2025", "week": 8})
    manager = FakeSleeperDataManager(_identity())

    outcome = _service(source, manager, tmp_path).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=None,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.PARTIAL
    state_result = next(
        result for result in outcome.scope_results if str(result.scope_key) == "state:nfl"
    )
    assert state_result.warning_codes == (
        "nfl_state_season_mismatch",
        "weekly_plan_omitted_nfl_state_unavailable",
    )


def test_failed_player_catalog_rejects_only_real_dependents(tmp_path: Path) -> None:
    source = FakeSourceClient(failures={EndpointKind.PLAYER_CATALOG})
    manager = FakeSleeperDataManager(_identity())

    outcome = _service(source, manager, tmp_path).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.PARTIAL
    assert [rejection.code for rejection in manager.rejections] == [
        "dependency_scope_unavailable",
        "dependency_scope_unavailable",
        "dependency_scope_unavailable",
    ]
    assert any(isinstance(row, TradedPicksScopeRecords) for row in manager.applied)
    assert sum(isinstance(row, BracketScopeRecords) for row in manager.applied) == 2
    assert all(not isinstance(row, RostersScopeRecords) for row in manager.applied)


def test_missing_reference_rejects_one_scope_without_aborting_refresh(
    tmp_path: Path,
) -> None:
    source = FakeSourceClient()
    manager = FakeSleeperDataManager(
        _identity(),
        reference_failures={EndpointKind.TRADED_PICKS},
    )

    outcome = _service(source, manager, tmp_path).refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.PARTIAL
    assert manager.rejections[-1].code == "reference_data_unavailable"
    assert len(source.requests) == 10
    assert any(isinstance(row, BracketScopeRecords) for row in manager.applied)


def test_large_payload_is_stored_by_verified_canonical_receipt(tmp_path: Path) -> None:
    source = FakeSourceClient()
    manager = FakeSleeperDataManager(_identity())
    service = DatalayerRefreshService(
        source_client=source,  # type: ignore[arg-type]
        data_manager=manager,  # type: ignore[arg-type]
        file_store=LocalDatalayerFileStore(tmp_path),
        inline_payload_threshold_bytes=1,
        code_version="test",
    )

    service.refresh(
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    receipt = manager.commands[0].payload
    assert receipt is not None
    assert receipt.inline_json_text is None
    assert receipt.local_storage_key is not None
    assert (tmp_path / receipt.local_storage_key).read_bytes() == canonical_json_bytes(
        _payload(source.requests[0], state_payload=source.state_payload)
    )


def test_cancellation_finalizes_cancelled_and_propagates(tmp_path: Path) -> None:
    source = FakeSourceClient(raises={EndpointKind.NFL_STATE: asyncio.CancelledError()})
    manager = FakeSleeperDataManager(_identity())

    with pytest.raises(asyncio.CancelledError):
        _service(source, manager, tmp_path).refresh(
            RefreshRequest(
                competition_season_id=SEASON_ID,
                through_week=1,
                trigger=RefreshTrigger.MANUAL,
            )
        )

    assert manager.finish_calls == [(True, None)]


def test_unexpected_failure_is_sanitized_finalized_and_propagated(tmp_path: Path) -> None:
    source = FakeSourceClient(
        raises={EndpointKind.NFL_STATE: ValueError("private upstream detail")}
    )
    manager = FakeSleeperDataManager(_identity())

    with pytest.raises(InternalDatalayerFailure) as caught:
        _service(source, manager, tmp_path).refresh(
            RefreshRequest(
                competition_season_id=SEASON_ID,
                through_week=1,
                trigger=RefreshTrigger.MANUAL,
            )
        )

    assert "private upstream detail" not in str(caught.value)
    assert manager.finish_calls[-1][1] == RefreshFailure(
        code="refresh_orchestration_failed",
        summary="Datalayer refresh orchestration failed",
    )


def _service(
    source: FakeSourceClient,
    manager: FakeSleeperDataManager,
    root: Path,
) -> DatalayerRefreshService:
    return DatalayerRefreshService(
        source_client=source,  # type: ignore[arg-type]
        data_manager=manager,  # type: ignore[arg-type]
        file_store=LocalDatalayerFileStore(root),
        inline_payload_threshold_bytes=1024 * 1024,
        code_version="test",
    )


def _identity() -> SeasonIdentityMap:
    return SeasonIdentityMap(
        competition_id=COMPETITION_ID,
        competition_season_id=SEASON_ID,
        sleeper_league_id="league-123",
        season_year=2024,
        roster_by_sleeper_id={
            "1": SeasonRosterIdentity(
                season_roster_id=SEASON_ROSTER_ID,
                franchise_id=FRANCHISE_ID,
            )
        },
    )


def _success(request: EndpointRequest, payload: JsonValue) -> SuccessfulSourceAttempt:
    canonical = canonical_json_bytes(payload)
    return SuccessfulSourceAttempt(
        endpoint=request,
        requested_at=NOW,
        completed_at=NOW,
        latency_ms=1,
        http_status=200,
        payload=payload,
        response_sha256=hashlib.sha256(canonical).hexdigest(),
        byte_length=len(canonical),
        media_type="application/json",
    )


def _payload(request: EndpointRequest, *, state_payload: JsonValue) -> JsonValue:
    match request.endpoint_kind:
        case EndpointKind.LEAGUE:
            return {
                "league_id": "league-123",
                "season": "2024",
                "name": "Test League",
                "sport": "nfl",
                "settings": {"draft_rounds": 2},
            }
        case EndpointKind.NFL_STATE:
            return state_payload
        case EndpointKind.PLAYER_CATALOG:
            return {"p1": {"player_id": "p1", "full_name": "Player One"}}
        case _:
            return []


def _refresh_run(
    *,
    plan: tuple[RefreshScopePlan, ...],
    through_week: int | None,
) -> RefreshRun:
    return RefreshRun(
        id=uuid4(),
        competition_id=COMPETITION_ID,
        competition_season_id=SEASON_ID,
        requested_through_week=through_week,
        effective_through_week=through_week,
        endpoint_plan=plan,
        trigger_source="manual",
        status=ResourceRefreshStatus.RUNNING,
        code_version="test",
        normalizer_version="1",
        started_at=NOW,
        completed_at=None,
        error_summary=None,
        attempt_count=0,
        succeeded_scope_count=0,
        failed_scope_count=0,
    )
