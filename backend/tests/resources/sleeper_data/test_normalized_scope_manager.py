from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.sleeper import (
    ApiRequest as StoredApiRequest,
    NormalizedScope,
    Player,
)
from backend.database.sessions import SessionFactory
from backend.resources.sleeper_data.normalized_scopes import NormalizedScopeManager
from backend.resources.sleeper_data.refreshes import RefreshRunManager
from backend.resources.sleeper_data.requests import (
    ApiRequestManager,
    RecordApiAttempt,
)
from backend.services.datalayer.contracts import (
    ApplyDisposition,
    NormalizationStatus,
)
from backend.services.datalayer.errors import (
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
)
from backend.services.datalayer.sleeper.endpoints import (
    build_nfl_state_request,
    build_player_catalog_request,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    CompletenessFinding,
    LeagueEndpointRecords,
    LeagueRecord,
    NflStateEndpointRecords,
    NflStateRecord,
    PlayerCatalogEndpointRecords,
    PlayerRecord,
)
from backend.tests.resources.sleeper_data.conftest import (
    Domain,
    manager_context,
    record_complete_attempt,
    seed_domain,
    start_refresh,
    successful_attempt,
)


def test_apply_scope_tracks_applied_identical_stale_and_replayed_observations(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    endpoint = build_player_catalog_request()
    refresh = start_refresh(refresh_manager, domain, endpoint)
    now = datetime.now(UTC)
    records = PlayerCatalogEndpointRecords(
        players=(PlayerRecord(sleeper_player_id="p1", full_name="First", metadata={}),)
    )
    first = record_complete_attempt(
        request_manager, refresh.id, endpoint, {"same": 1}, requested_at=now
    )
    identical = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        {"same": 1},
        requested_at=now + timedelta(seconds=2),
    )
    stale = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        {"older": True},
        requested_at=now + timedelta(seconds=1),
    )

    applied = normalized_scope_manager.apply_scope(first.id, records)
    advanced = normalized_scope_manager.apply_scope(identical.id, records)
    ignored = normalized_scope_manager.apply_scope(stale.id, records)
    replayed = normalized_scope_manager.apply_scope(identical.id, records)

    assert applied.disposition is ApplyDisposition.APPLIED
    assert advanced.disposition is ApplyDisposition.IDENTICAL_HEAD_ADVANCED
    assert ignored.disposition is ApplyDisposition.STALE_IGNORED
    assert replayed.disposition is ApplyDisposition.ALREADY_APPLIED
    assert not advanced.changed_current_view
    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(
                NormalizedScope.source_api_request_id,
                NormalizedScope.response_sha256,
                NormalizedScope.normalized_row_count,
            ).where(NormalizedScope.scope_key == endpoint.scope_key.value)
        ).one() == (identical.id, identical.response_sha256, 1)
        assert connection.execute(
            sa.select(Player.full_name, Player.source_api_request_id).where(
                Player.sleeper_player_id == "p1"
            )
        ).one() == ("First", first.id)
        attempts = connection.execute(
            sa.select(
                StoredApiRequest.normalization_status,
                StoredApiRequest.normalizer_version,
            )
            .where(StoredApiRequest.id.in_((first.id, identical.id, stale.id)))
            .order_by(StoredApiRequest.requested_at)
        ).all()
        assert attempts == [
            (NormalizationStatus.SUCCEEDED.value, "test-normalizer"),
            (NormalizationStatus.SUCCEEDED.value, "test-normalizer"),
            (NormalizationStatus.SUCCEEDED.value, "test-normalizer"),
        ]


def test_apply_scope_rejects_incomplete_mismatched_and_foreign_requests(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
    session_factory: SessionFactory,
) -> None:
    endpoint = build_player_catalog_request()
    refresh = start_refresh(refresh_manager, domain, endpoint)
    incomplete = request_manager.record_attempt(
        RecordApiAttempt(
            refresh_run_id=refresh.id,
            attempt=successful_attempt(endpoint, {"partial": True}),
            completeness=CompletenessFinding(
                is_complete=False, reason="catalog_incomplete"
            ),
        )
    )
    with pytest.raises(DatalayerScopeConflict, match="eligible"):
        normalized_scope_manager.apply_scope(
            incomplete.id, PlayerCatalogEndpointRecords(players=())
        )

    complete = record_complete_attempt(
        request_manager, refresh.id, endpoint, {"complete": True}
    )
    with pytest.raises(DatalayerScopeConflict, match="do not match"):
        normalized_scope_manager.apply_scope(
            complete.id,
            LeagueEndpointRecords(
                league=LeagueRecord(
                    sleeper_league_id=domain.sleeper_league_id,
                    name="Wrong endpoint",
                    season="2026",
                    sport="nfl",
                    scoring_settings={},
                    roster_positions=(),
                    provider_settings={},
                )
            ),
        )

    other = seed_domain(database_engine, label="Other")
    foreign_manager = NormalizedScopeManager(session_factory, manager_context(other))
    with pytest.raises(DatalayerResourceNotFound):
        foreign_manager.apply_scope(
            complete.id, PlayerCatalogEndpointRecords(players=())
        )

    with database_engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(NormalizedScope))
            == 0
        )


def test_concurrent_scope_claim_keeps_the_newest_observation(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    endpoint = build_player_catalog_request()
    refresh = start_refresh(refresh_manager, domain, endpoint)
    now = datetime.now(UTC)
    older = record_complete_attempt(
        request_manager, refresh.id, endpoint, {"version": 1}, requested_at=now
    )
    newer = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        {"version": 2},
        requested_at=now + timedelta(seconds=1),
    )
    records = {
        older.id: PlayerCatalogEndpointRecords(
            players=(
                PlayerRecord(sleeper_player_id="p1", full_name="Older", metadata={}),
            )
        ),
        newer.id: PlayerCatalogEndpointRecords(
            players=(
                PlayerRecord(sleeper_player_id="p1", full_name="Newer", metadata={}),
            )
        ),
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            executor.map(
                lambda request_id: normalized_scope_manager.apply_scope(
                    request_id, records[request_id]
                ),
                (newer.id, older.id),
            )
        )

    assert all(
        result.disposition in {ApplyDisposition.APPLIED, ApplyDisposition.STALE_IGNORED}
        for result in outcomes
    )
    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(Player.full_name, Player.source_api_request_id).where(
                Player.sleeper_player_id == "p1"
            )
        ).one() == ("Newer", newer.id)
        assert (
            connection.scalar(
                sa.select(NormalizedScope.source_api_request_id).where(
                    NormalizedScope.scope_key == endpoint.scope_key.value
                )
            )
            == newer.id
        )


def test_nfl_state_advances_only_observation_provenance(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    endpoint = build_nfl_state_request()
    refresh = start_refresh(refresh_manager, domain, endpoint)
    request = record_complete_attempt(
        request_manager, refresh.id, endpoint, {"week": 4, "season": "2026"}
    )
    result = normalized_scope_manager.apply_scope(
        request.id,
        NflStateEndpointRecords(
            state=NflStateRecord(
                week=4,
                season="2026",
                provider_state={"display_week": 4},
            )
        ),
    )

    assert result.disposition is ApplyDisposition.APPLIED
    assert result.normalized_row_count == 1
    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(
                NormalizedScope.source_api_request_id,
                NormalizedScope.normalized_row_count,
            ).where(NormalizedScope.scope_key == endpoint.scope_key.value)
        ).one() == (request.id, 1)
        assert (
            connection.scalar(
                sa.select(StoredApiRequest.normalization_status).where(
                    StoredApiRequest.id == request.id
                )
            )
            == NormalizationStatus.SUCCEEDED.value
        )
