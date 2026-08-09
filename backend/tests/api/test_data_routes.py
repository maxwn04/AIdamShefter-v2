from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import final
from uuid import UUID

from httpx import ASGITransport, AsyncClient
import pytest

import backend.api.dependencies.services as service_dependencies
from backend.api.app import create_app
from backend.api.dependencies.services import (
    get_datalayer_refresh_service,
    get_sleeper_data_manager,
)
from backend.composition import ApiRuntimeDependencies
from backend.resources.context import ManagerContext
from backend.resources.errors import (
    InvalidResourceCommand,
    ResourceConflict,
    ResourceNotFound,
)
from backend.resources.sleeper_data.objects import (
    ApiRequest,
    Page,
    RefreshRun,
    RefreshScopePlan,
)
from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RefreshOutcome,
    RefreshRequest,
    RefreshStatus,
    RefreshTrigger,
    RequestStatus,
    ScopeRefreshResult,
)
from backend.sleeper import ScopeKey
from backend.services.datalayer.errors import InternalDatalayerFailure

COMPETITION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SEASON_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
REFRESH_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
API_REQUEST_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
NOW = datetime(2025, 9, 1, 12, tzinfo=UTC)


@final
class StubRuntime:
    def assert_ready(self) -> None:
        pass

    def close(self) -> None:
        pass


@final
class StubRefreshService:
    def __init__(self, outcome: RefreshOutcome) -> None:
        self.outcome = outcome
        self.requests: list[RefreshRequest] = []

    def refresh(self, request: RefreshRequest) -> RefreshOutcome:
        self.requests.append(request)
        return self.outcome


@final
class FailingRefreshService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def refresh(self, request: RefreshRequest) -> RefreshOutcome:
        raise self.error


@final
class StubAuditManager:
    def get_refresh(self, refresh_id: UUID) -> RefreshRun:
        assert refresh_id == REFRESH_ID
        return RefreshRun(
            id=REFRESH_ID,
            competition_id=COMPETITION_ID,
            competition_season_id=SEASON_ID,
            requested_through_week=8,
            effective_through_week=8,
            endpoint_plan=(
                RefreshScopePlan(
                    scope_key=f"league:{SEASON_ID}",
                    endpoint_kind="league",
                    required=True,
                ),
            ),
            trigger_source="manual",
            status=RefreshStatus.SUCCEEDED,
            code_version="test-sha",
            normalizer_version="1",
            started_at=NOW,
            completed_at=NOW,
            error_summary=None,
            attempt_count=1,
            succeeded_scope_count=1,
            failed_scope_count=0,
        )

    def list_refresh_requests(
        self,
        refresh_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> Page[ApiRequest]:
        assert refresh_id == REFRESH_ID
        assert (limit, offset) == (25, 5)
        return Page(
            items=(
                ApiRequest(
                    id=API_REQUEST_ID,
                    refresh_run_id=REFRESH_ID,
                    competition_season_id=SEASON_ID,
                    endpoint_kind="league",
                    scope_key=f"league:{SEASON_ID}",
                    request_path="/private/source/path",
                    request_parameters={"secret": "not-public"},
                    week=None,
                    bracket_kind=None,
                    requested_at=NOW,
                    completed_at=NOW,
                    latency_ms=1,
                    status=RequestStatus.SUCCEEDED,
                    http_status=200,
                    error=None,
                    is_complete=True,
                    completeness_reason="league_payload_complete: complete",
                    response_sha256="a" * 64,
                    normalization_status=NormalizationStatus.SUCCEEDED,
                    normalizer_version="1",
                    normalized_at=NOW,
                ),
            ),
            limit=limit,
            offset=offset,
            total=1,
        )


def _runtime_factory() -> ApiRuntimeDependencies:
    return StubRuntime()


def _outcome(status: RefreshStatus = RefreshStatus.PARTIAL) -> RefreshOutcome:
    return RefreshOutcome(
        refresh_run_id=REFRESH_ID,
        status=status,
        requested_scope_count=2,
        succeeded_scope_count=1,
        failed_scope_count=1,
        scope_results=(
            ScopeRefreshResult(
                scope_key=ScopeKey.parse("matchups:season-1:8"),
                api_request_id=API_REQUEST_ID,
                fetch_status=RequestStatus.SUCCEEDED,
                normalization_status=NormalizationStatus.SUCCEEDED,
                changed_current_view=True,
                warning_codes=(),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_manual_refresh_runs_synchronously_and_returns_terminal_audit() -> None:
    service = StubRefreshService(_outcome())
    app = create_app(runtime_factory=_runtime_factory)
    app.dependency_overrides[get_datalayer_refresh_service] = lambda: service

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/competitions/{COMPETITION_ID}/seasons/"
                f"{SEASON_ID}/data-refreshes",
                json={"through_week": 8},
            )

    assert response.status_code == 200
    assert response.json() == {
        "refresh_run_id": str(REFRESH_ID),
        "status": "partial",
        "requested_scope_count": 2,
        "succeeded_scope_count": 1,
        "failed_scope_count": 1,
        "scope_results": [
            {
                "scope_key": "matchups:season-1:8",
                "api_request_id": str(API_REQUEST_ID),
                "fetch_status": "succeeded",
                "normalization_status": "succeeded",
                "changed_current_view": True,
                "warning_codes": [],
            }
        ],
    }
    assert service.requests == [
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=8,
            trigger=RefreshTrigger.MANUAL,
        )
    ]


@pytest.mark.asyncio
async def test_refresh_dependency_scopes_manager_context_from_the_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StubRefreshService(_outcome(RefreshStatus.SUCCEEDED))
    captured_contexts: list[ManagerContext] = []

    @contextmanager
    def open_service(
        runtime: ApiRuntimeDependencies,
        context: ManagerContext,
    ) -> Iterator[StubRefreshService]:
        captured_contexts.append(context)
        yield service

    monkeypatch.setattr(
        service_dependencies,
        "open_datalayer_refresh_service",
        open_service,
    )
    app = create_app(runtime_factory=_runtime_factory)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/competitions/{COMPETITION_ID}/seasons/"
                f"{SEASON_ID}/data-refreshes",
                headers={"X-Request-ID": "external-request-123"},
                json={},
            )

    assert response.status_code == 200
    assert len(captured_contexts) == 1
    context = captured_contexts[0]
    assert context.actor_kind == "api"
    assert context.actor_id == "local-api"
    assert context.competition_id == COMPETITION_ID
    assert context.correlation_id == "external-request-123"


@pytest.mark.parametrize(
    "body",
    [
        {"through_week": 0},
        {"through_week": 19},
        {"through_week": 8, "trigger": "scheduled"},
    ],
)
@pytest.mark.asyncio
async def test_manual_refresh_rejects_caller_controlled_plan_fields(
    body: dict[str, object],
) -> None:
    service = StubRefreshService(_outcome())
    app = create_app(runtime_factory=_runtime_factory)
    app.dependency_overrides[get_datalayer_refresh_service] = lambda: service

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/competitions/{COMPETITION_ID}/seasons/"
                f"{SEASON_ID}/data-refreshes",
                json=body,
            )

    assert response.status_code == 422
    assert service.requests == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (ResourceNotFound("secret season"), 404, "data resource not found"),
        (
            ResourceConflict("secret competition mismatch"),
            409,
            "data refresh conflicts with current state",
        ),
        (
            InvalidResourceCommand("secret invalid plan"),
            422,
            "invalid data refresh request",
        ),
        (
            InternalDatalayerFailure("correlation-123"),
            500,
            {
                "code": "internal_datalayer_failure",
                "correlation_id": "correlation-123",
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_manual_refresh_translates_boundary_errors_without_leaking_details(
    error: Exception,
    expected_status: int,
    expected_detail: str | dict[str, str],
) -> None:
    app = create_app(runtime_factory=_runtime_factory)
    app.dependency_overrides[get_datalayer_refresh_service] = lambda: (
        FailingRefreshService(error)
    )

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/competitions/{COMPETITION_ID}/seasons/"
                f"{SEASON_ID}/data-refreshes",
                json={},
            )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_refresh_audit_routes_return_sanitized_scoped_resources() -> None:
    manager = StubAuditManager()
    app = create_app(runtime_factory=_runtime_factory)
    app.dependency_overrides[get_sleeper_data_manager] = lambda: manager

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            refresh_response = await client.get(
                f"/api/v1/competitions/{COMPETITION_ID}/data-refreshes/{REFRESH_ID}"
            )
            requests_response = await client.get(
                f"/api/v1/competitions/{COMPETITION_ID}/data-refreshes/"
                f"{REFRESH_ID}/requests?limit=25&offset=5"
            )

    assert refresh_response.status_code == 200
    assert refresh_response.json()["endpoint_plan"] == [
        {
            "scope_key": f"league:{SEASON_ID}",
            "endpoint_kind": "league",
            "required": True,
            "dependency_scope_keys": [],
        }
    ]
    assert requests_response.status_code == 200
    body = requests_response.json()
    assert body["limit"] == 25
    assert body["offset"] == 5
    assert body["total"] == 1
    assert body["items"][0]["api_request_id"] == str(API_REQUEST_ID)
    assert "request_path" not in body["items"][0]
    assert "request_parameters" not in body["items"][0]
    assert "private" not in requests_response.text
