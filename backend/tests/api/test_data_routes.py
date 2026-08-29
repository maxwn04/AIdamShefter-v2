from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

import backend.api.dependencies.data as data_dependencies_module
from backend.api.app import create_app
from backend.api.dependencies.data import get_data_api_dependencies
from backend.composition import ApiRuntimeDependencies
from backend.resources.sleeper_data import (
    DataSnapshot,
    DataSnapshotPage,
    LeagueSeasonOverview,
    PlannedEndpointScope,
    RefreshRun,
    RefreshRunPage,
)
from backend.resources.sleeper_data.snapshots import (
    SnapshotSeasonMembership,
    SnapshotSeasonRole,
)
from backend.services.datalayer import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
    EndpointKind,
    EndpointPayloadRejected,
    InvalidDatalayerRequest,
    NormalizationStatus,
    PreparedSnapshot,
    PrepareSnapshotRequest,
    ReadyDataSnapshot,
    ReadySnapshotSeason,
    ReadySnapshotReadiness,
    RefreshOutcome,
    RefreshRequest,
    RefreshStatus,
    RefreshUnavailable,
    RequestStatus,
    RosterIdentityMappingRequired,
    ScopeKey,
    ScopeRefreshResult,
    SnapshotPreparationMode,
    SnapshotReadinessSeason,
    SnapshotStatus,
    SnapshotInputsUnavailable,
    SnapshotUnavailable,
)
from backend.services.datalayer.local_files import (
    StoredLocalArtifact,
    VerifiedLocalArtifact,
)
from backend.services.datalayer.refresh_coordination import (
    RefreshReceipt,
    RefreshReceiptDisposition,
)
from backend.services.datalayer.snapshot_sqlite import SnapshotArtifactInvalid


NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)


class StubRuntime:
    def assert_ready(self) -> None:
        pass

    def close(self) -> None:
        pass


def runtime_factory() -> ApiRuntimeDependencies:
    return StubRuntime()


class StubRefreshService:
    def __init__(self, outcome: RefreshOutcome) -> None:
        self.outcome = outcome
        self.requests: list[RefreshRequest] = []

    def refresh(self, request: RefreshRequest) -> RefreshOutcome:
        self.requests.append(request)
        return self.outcome


class StubRefreshManager:
    def __init__(self, refresh: RefreshRun) -> None:
        self.refresh = refresh
        self.queries: list[object] = []
        self.reads: list[tuple[UUID, UUID]] = []
        self.error: Exception | None = None

    def list_refreshes(self, query: object) -> RefreshRunPage:
        self.queries.append(query)
        self._raise()
        return RefreshRunPage(items=(self.refresh,), total=1, limit=7, offset=2)

    def get_refresh_for_season(
        self,
        season_id: UUID,
        refresh_id: UUID,
    ) -> RefreshRun:
        self.reads.append((season_id, refresh_id))
        self._raise()
        return self.refresh

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error


class StubLeagueSeasons:
    def __init__(self, overview: LeagueSeasonOverview) -> None:
        self.overview = overview
        self.season_ids: list[UUID] = []

    def get_season_overview(self, season_id: UUID) -> LeagueSeasonOverview:
        self.season_ids.append(season_id)
        return self.overview


class StubSnapshots:
    def __init__(self, snapshot: DataSnapshot) -> None:
        self.snapshot = snapshot
        self.queries: list[object] = []

    def list_snapshots(self, query: object) -> DataSnapshotPage:
        self.queries.append(query)
        return DataSnapshotPage(items=(self.snapshot,), total=1, limit=4, offset=1)


class StubReadiness:
    def __init__(self, result: object) -> None:
        self.result = result
        self.requests: list[PrepareSnapshotRequest] = []

    def inspect(self, request: PrepareSnapshotRequest) -> object:
        self.requests.append(request)
        return self.result


class StubPreparation:
    def __init__(self, result: PreparedSnapshot) -> None:
        self.result = result
        self.requests: list[PrepareSnapshotRequest] = []
        self.error: Exception | None = None

    def get_or_create(self, request: PrepareSnapshotRequest) -> PreparedSnapshot:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def _dependencies() -> SimpleNamespace:
    competition_id = uuid4()
    season_id = uuid4()
    refresh_id = uuid4()
    scope = ScopeKey.from_parts(EndpointKind.LEAGUE, season_id)
    planned = PlannedEndpointScope(
        scope_key=scope,
        endpoint_kind=EndpointKind.LEAGUE,
    )
    refresh = RefreshRun(
        id=refresh_id,
        competition_id=competition_id,
        competition_season_id=season_id,
        requested_through_week=None,
        endpoint_scope=(planned,),
        trigger="manual",
        status=RefreshStatus.SUCCEEDED,
        code_version="test",
        normalizer_version="test",
        started_at=NOW,
        completed_at=NOW,
        error=None,
        request_count=1,
        succeeded_request_count=1,
        failed_request_count=0,
    )
    result = ScopeRefreshResult(
        scope_key=scope,
        api_request_id=uuid4(),
        fetch_status=RequestStatus.SUCCEEDED,
        normalization_status=NormalizationStatus.SUCCEEDED,
        changed_current_view=True,
    )
    outcome = RefreshOutcome(
        refresh_run_id=refresh_id,
        status=RefreshStatus.SUCCEEDED,
        effective_through_week=8,
        requested_scope_count=1,
        succeeded_scope_count=1,
        failed_scope_count=0,
        scope_results=(result,),
    )
    overview = LeagueSeasonOverview(
        competition_id=competition_id,
        competition_season_id=season_id,
        competition_name="The League",
        sleeper_league_id="sleeper-2026",
        season_year=2026,
        sequence_number=1,
        league_name="Sleeper League",
        status="in_season",
        scoring_settings={},
        roster_positions=("QB", "RB"),
        provider_settings={},
        playoff_start_week=15,
        playoff_team_count=6,
        league_average_match=None,
        roster_count=12,
        source_api_request_id=uuid4(),
    )
    digest = "a" * 64
    snapshot = DataSnapshot(
        id=uuid4(),
        competition_id=competition_id,
        primary_competition_season_id=season_id,
        build_key="b" * 64,
        through_week=8,
        as_of_date=date(2026, 8, 23),
        status=SnapshotStatus.READY,
        snapshot_projection_version="2",
        code_version="test",
        input_revision=digest,
        included_seasons=(
            SnapshotSeasonMembership(
                competition_id=competition_id,
                competition_season_id=season_id,
                sleeper_league_id="sleeper-2026",
                season_year=2026,
                sequence_number=1,
                role=SnapshotSeasonRole.PRIMARY,
                through_week=8,
            ),
        ),
        completeness_warnings=(),
        failure=None,
        artifact=StoredLocalArtifact(
            storage_key=f"snapshots/sha256/{digest[:2]}/{digest}.sqlite",
            sha256=digest,
            byte_length=123,
        ),
        created_at=NOW,
        completed_at=NOW,
    )
    readiness_season = SnapshotReadinessSeason(
        competition_season_id=season_id,
        sleeper_league_id="sleeper-2026",
        season_year=2026,
        sequence_number=1,
        role=SnapshotSeasonRole.PRIMARY,
        through_week=8,
    )
    ready_snapshot = ReadyDataSnapshot(
        id=snapshot.id,
        competition_id=competition_id,
        primary_competition_season_id=season_id,
        through_week=8,
        as_of_date=date(2026, 8, 23),
        build_key=snapshot.build_key,
        snapshot_projection_version="3",
        artifact=VerifiedLocalArtifact(
            path=Path(__file__).resolve(),
            storage_key=f"snapshots/sha256/{digest[:2]}/{digest}.sqlite",
            sha256=digest,
            byte_length=123,
        ),
        input_revision=digest,
        included_seasons=(
            ReadySnapshotSeason(
                competition_season_id=season_id,
                sleeper_league_id="sleeper-2026",
                season_year=2026,
                sequence_number=1,
                role=SnapshotSeasonRole.PRIMARY,
                through_week=8,
            ),
        ),
    )
    receipt = RefreshReceipt(
        claim_id=uuid4(),
        competition_season_id=season_id,
        through_week=8,
        refresh_run_id=refresh_id,
        status=RefreshStatus.SUCCEEDED,
        disposition=RefreshReceiptDisposition.CLAIMED,
    )
    refreshes = StubRefreshManager(refresh)
    return SimpleNamespace(
        competition_id=competition_id,
        season_id=season_id,
        refresh=StubRefreshService(outcome),
        refreshes=refreshes,
        league_seasons=StubLeagueSeasons(overview),
        snapshots=StubSnapshots(snapshot),
        readiness=StubReadiness(
            ReadySnapshotReadiness(
                input_revision=digest,
                included_seasons=(readiness_season,),
            )
        ),
        preparation=StubPreparation(
            PreparedSnapshot(snapshot=ready_snapshot, refresh_receipts=(receipt,))
        ),
    )


async def _client(dependencies: SimpleNamespace) -> tuple[Any, AsyncClient]:
    app = create_app(runtime_factory=runtime_factory)
    app.dependency_overrides[get_data_api_dependencies] = lambda: dependencies
    return app, AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_data_routes_preserve_scoped_transport_contracts() -> None:
    dependencies = _dependencies()
    app, client = await _client(dependencies)
    base = (
        f"/api/v1/data/competitions/{dependencies.competition_id}"
        f"/seasons/{dependencies.season_id}"
    )

    async with app.router.lifespan_context(app), client:
        omitted = await client.post(f"{base}/refreshes")
        created = await client.post(f"{base}/refreshes", json={})
        nullable = await client.post(
            f"{base}/refreshes",
            json={"through_week": None},
        )
        explicit = await client.post(
            f"{base}/refreshes",
            json={"through_week": 8},
        )
        listed = await client.get(f"{base}/refreshes?limit=7&offset=2")
        detail = await client.get(
            f"{base}/refreshes/{dependencies.refreshes.refresh.id}"
        )
        overview = await client.get(f"{base}/overview")
        readiness = await client.get(
            f"{base}/snapshot-readiness?through_week=8&mode=readiness_only"
        )
        preparation = await client.post(
            f"{base}/snapshot-preparations",
            json={"through_week": 8, "mode": "live"},
        )
        snapshots = await client.get(f"{base}/snapshots?limit=4&offset=1")

    assert omitted.status_code == 201
    assert created.status_code == 201
    assert nullable.status_code == 201
    assert explicit.status_code == 201
    assert created.json()["effective_through_week"] == 8
    assert created.json()["refresh"]["trigger"] == "manual"
    assert [request.trigger.value for request in dependencies.refresh.requests] == [
        "manual",
        "manual",
        "manual",
        "manual",
    ]
    assert [request.through_week for request in dependencies.refresh.requests] == [
        None,
        None,
        None,
        8,
    ]
    assert listed.json()["page"]["total"] == 1
    assert dependencies.refreshes.queries[0].competition_season_id == (
        dependencies.season_id
    )
    assert detail.json()["refresh"]["id"] == str(
        dependencies.refreshes.refresh.id
    )
    assert overview.json()["overview"]["league_name"] == "Sleeper League"
    assert readiness.status_code == 200
    assert readiness.json()["state"]["kind"] == "ready"
    assert readiness.json()["state"]["included_seasons"][0]["season_year"] == 2026
    readiness_request = dependencies.readiness.requests[0]
    assert readiness_request.mode is SnapshotPreparationMode.READINESS_ONLY
    assert readiness_request.snapshot.through_week == 8
    assert readiness_request.requested_at.tzinfo is not None
    assert preparation.status_code == 200
    assert preparation.json()["snapshot"]["snapshot_projection_version"] == "3"
    assert preparation.json()["snapshot"]["input_revision"] == "a" * 64
    assert preparation.json()["refresh_receipts"][0]["status"] == "succeeded"
    preparation_request = dependencies.preparation.requests[0]
    assert preparation_request.mode is SnapshotPreparationMode.LIVE
    assert preparation_request.snapshot.as_of_date == (
        preparation_request.requested_at.date()
    )
    snapshot_json = snapshots.json()["page"]["items"][0]
    assert snapshot_json["artifact"] == {"sha256": "a" * 64, "byte_length": 123}
    assert snapshot_json["input_revision"] == "a" * 64
    assert snapshot_json["included_seasons"][0]["role"] == "primary"
    assert "storage_key" not in snapshots.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"through_week": True},
        {"through_week": 0},
        {"through_week": 19},
        {"through_week": "8"},
        {"unexpected": 8},
    ],
)
async def test_manual_refresh_rejects_invalid_bodies(
    payload: dict[str, object],
) -> None:
    dependencies = _dependencies()
    app, client = await _client(dependencies)
    base = (
        f"/api/v1/data/competitions/{dependencies.competition_id}"
        f"/seasons/{dependencies.season_id}/refreshes"
    )

    async with app.router.lifespan_context(app), client:
        response = await client.post(base, json=payload)

    assert response.status_code == 422
    assert dependencies.refresh.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (
            InvalidDatalayerRequest("invalid page"),
            400,
            "invalid_data_request",
        ),
        (
            DatalayerResourceNotFound("refresh", "missing"),
            404,
            "data_resource_not_found",
        ),
        (
            DatalayerScopeConflict("safe conflict"),
            409,
            "data_scope_conflict",
        ),
        (
            EndpointPayloadRejected(
                EndpointKind.LEAGUE,
                "invalid_league",
                "Sleeper league payload was rejected",
            ),
            422,
            "endpoint_payload_rejected",
        ),
        (
            SnapshotUnavailable("snapshot inputs are unavailable"),
            503,
            "snapshot_unavailable",
        ),
        (
            RosterIdentityMappingRequired(
                "Sleeper rosters require durable franchise mappings",
                competition_season_id=UUID(
                    "10000000-0000-0000-0000-000000000001"
                ),
                sleeper_roster_ids=("1", "2"),
            ),
            409,
            "roster_identity_mapping_required",
        ),
        (
            SnapshotInputsUnavailable(
                UUID("10000000-0000-0000-0000-000000000001"),
            ),
            503,
            "snapshot_inputs_unavailable",
        ),
        (
            RefreshUnavailable(
                UUID("10000000-0000-0000-0000-000000000001"),
                claim_id=UUID("20000000-0000-0000-0000-000000000001"),
                refresh_run_id=UUID(
                    "30000000-0000-0000-0000-000000000001"
                ),
                retryable=True,
            ),
            503,
            "refresh_unavailable",
        ),
        (
            SnapshotArtifactInvalid("private artifact detail"),
            500,
            "snapshot_artifact_invalid",
        ),
    ],
)
async def test_datalayer_errors_use_stable_safe_envelopes(
    error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    dependencies = _dependencies()
    dependencies.refreshes.error = error
    app, client = await _client(dependencies)
    url = (
        f"/api/v1/data/competitions/{dependencies.competition_id}"
        f"/seasons/{dependencies.season_id}/refreshes/{uuid4()}"
    )

    async with app.router.lifespan_context(app), client:
        response = await client.get(url)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    if isinstance(error, DatalayerResourceNotFound):
        assert "missing" not in response.text
    if isinstance(error, SnapshotArtifactInvalid):
        assert "private artifact detail" not in response.text


@pytest.mark.asyncio
async def test_actionable_preparation_errors_keep_only_safe_identifiers() -> None:
    dependencies = _dependencies()
    season_id = UUID("10000000-0000-0000-0000-000000000001")
    dependencies.refreshes.error = RosterIdentityMappingRequired(
        "Sleeper rosters require durable franchise mappings",
        competition_season_id=season_id,
        sleeper_roster_ids=("1", "2"),
    )
    app, client = await _client(dependencies)
    url = (
        f"/api/v1/data/competitions/{dependencies.competition_id}"
        f"/seasons/{dependencies.season_id}/refreshes/{uuid4()}"
    )

    async with app.router.lifespan_context(app), client:
        response = await client.get(url)

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "roster_identity_mapping_required",
        "summary": "Sleeper rosters require durable franchise mappings",
        "competition_season_id": str(season_id),
        "sleeper_roster_ids": ["1", "2"],
    }


@pytest.mark.asyncio
async def test_snapshot_preparation_translates_mapping_requirement() -> None:
    dependencies = _dependencies()
    blocked_season_id = UUID("10000000-0000-0000-0000-000000000001")
    dependencies.preparation.error = RosterIdentityMappingRequired(
        "Sleeper rosters require durable franchise mappings",
        competition_season_id=blocked_season_id,
        sleeper_roster_ids=("3", "4"),
    )
    app, client = await _client(dependencies)
    url = (
        f"/api/v1/data/competitions/{dependencies.competition_id}"
        f"/seasons/{dependencies.season_id}/snapshot-preparations"
    )

    async with app.router.lifespan_context(app), client:
        response = await client.post(
            url,
            json={"through_week": 8, "mode": "readiness_only"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["competition_season_id"] == str(
        blocked_season_id
    )
    assert response.json()["error"]["sleeper_roster_ids"] == ["3", "4"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"through_week": True, "mode": "live"},
        {"through_week": 0, "mode": "live"},
        {"through_week": 19, "mode": "readiness_only"},
        {"through_week": "8", "mode": "live"},
        {"through_week": 8, "mode": "unknown"},
        {"through_week": 8, "mode": "live", "unexpected": True},
    ],
)
async def test_snapshot_preparation_rejects_invalid_bodies(
    payload: dict[str, object],
) -> None:
    dependencies = _dependencies()
    app, client = await _client(dependencies)
    url = (
        f"/api/v1/data/competitions/{dependencies.competition_id}"
        f"/seasons/{dependencies.season_id}/snapshot-preparations"
    )

    async with app.router.lifespan_context(app), client:
        response = await client.post(url, json=payload)

    assert response.status_code == 422
    assert dependencies.preparation.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "through_week=0&mode=live",
        "through_week=19&mode=readiness_only",
        "through_week=8&mode=unknown",
    ],
)
async def test_snapshot_readiness_rejects_invalid_query(query: str) -> None:
    dependencies = _dependencies()
    app, client = await _client(dependencies)
    url = (
        f"/api/v1/data/competitions/{dependencies.competition_id}"
        f"/seasons/{dependencies.season_id}/snapshot-readiness?{query}"
    )

    async with app.router.lifespan_context(app), client:
        response = await client.get(url)

    assert response.status_code == 422
    assert dependencies.readiness.requests == []


def test_openapi_contains_refresh_and_data_audit_boundaries() -> None:
    schema = create_app(runtime_factory=runtime_factory).openapi()
    base = "/api/v1/data/competitions/{competition_id}/seasons/{season_id}"

    assert {
        f"{base}/refreshes",
        f"{base}/refreshes/{{refresh_id}}",
        f"{base}/overview",
        f"{base}/snapshot-readiness",
        f"{base}/snapshot-preparations",
        f"{base}/snapshots",
    }.issubset(schema["paths"])
    assert schema["paths"][f"{base}/refreshes"]["post"]["responses"]["201"]


def test_data_dependency_closes_its_owned_source(monkeypatch: pytest.MonkeyPatch) -> None:
    class ClosableDependencies:
        closed = False

        def close(self) -> None:
            self.closed = True

    dependencies = ClosableDependencies()
    monkeypatch.setattr(
        data_dependencies_module,
        "build_data_api_dependencies",
        lambda _sessions, _context: dependencies,
    )
    iterator = get_data_api_dependencies(
        uuid4(),
        uuid4(),
        SimpleNamespace(session_factory=object()),
    )

    assert next(iterator) is dependencies
    iterator.close()

    assert dependencies.closed
