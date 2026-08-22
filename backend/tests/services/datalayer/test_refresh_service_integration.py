from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.engine import Engine

from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.sleeper_data import (
    ApiRequestManager,
    LeagueSeasonManager,
    MatchupManager,
    NormalizedScopeManager,
    PlayerManager,
    PlayerSearch,
    RefreshRunManager,
    RosterManager,
    TransactionManager,
    TransactionQuery,
)
from backend.services.datalayer import (
    EndpointKind,
    LocalDatalayerFileStore,
    RefreshRequest,
    RefreshStatus,
    RefreshTrigger,
    RequestStatus,
    SanitizedSourceError,
    SuccessfulSourceAttempt,
)
from backend.services.datalayer.canonical_json import canonical_json_bytes
from backend.services.datalayer.refresh_service import DatalayerRefreshService
from backend.services.datalayer.sleeper.responses import (
    EndpointRequest,
    FailedSourceAttempt,
    SourceAttempt,
)
from backend.tests.resources.sleeper_data.conftest import (
    Domain,
    manager_context,
    seed_domain,
)
from backend.tests.database.conftest import database_engine, migrated_database


@pytest.fixture
def session_factory(database_engine: Engine) -> SessionFactory:
    return create_session_factory(database_engine)


def test_fixture_refresh_populates_current_postgresql_reads(
    database_engine: Engine,
    session_factory: SessionFactory,
    tmp_path: Path,
) -> None:
    domain = seed_domain(database_engine, label="Refresh Workflow")
    context = manager_context(domain)
    service = DatalayerRefreshService(
        source=FixtureSource(domain),
        identities=LeagueSeasonManager(session_factory, context),
        refreshes=RefreshRunManager(session_factory, context),
        attempts=ApiRequestManager(session_factory, context),
        scopes=NormalizedScopeManager(session_factory, context),
        files=LocalDatalayerFileStore(tmp_path),
        code_version="test",
        delay=lambda _: None,
    )

    outcome = service.refresh(
        RefreshRequest(
            competition_season_id=domain.season_id,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )

    assert outcome.status is RefreshStatus.SUCCEEDED
    assert outcome.requested_scope_count == 10
    overview = LeagueSeasonManager(session_factory, context).get_season_overview(
        domain.season_id
    )
    assert overview.league_name == "Refresh Workflow League"
    roster = RosterManager(session_factory, context).get_roster(domain.roster_ids[0])
    assert roster.competition_season_id == domain.season_id
    assert PlayerManager(session_factory, context).search_players(
        PlayerSearch()
    ).total == 4
    assert len(
        MatchupManager(session_factory, context).list_matchups(
            domain.season_id, 1
        )
    ) == 2
    assert len(
        TransactionManager(session_factory, context).list_transactions(
            TransactionQuery(competition_season_id=domain.season_id, week=1)
        )
    ) == 1


def test_partial_refresh_preserves_previous_good_scope_head(
    database_engine: Engine,
    session_factory: SessionFactory,
    tmp_path: Path,
) -> None:
    domain = seed_domain(database_engine, label="Refresh Preservation")
    context = manager_context(domain)

    def service(source: FixtureSource) -> DatalayerRefreshService:
        return DatalayerRefreshService(
            source=source,
            identities=LeagueSeasonManager(session_factory, context),
            refreshes=RefreshRunManager(session_factory, context),
            attempts=ApiRequestManager(session_factory, context),
            scopes=NormalizedScopeManager(session_factory, context),
            files=LocalDatalayerFileStore(tmp_path),
            code_version="test",
            max_attempts=1,
            delay=lambda _: None,
        )

    first = service(FixtureSource(domain)).refresh(
        RefreshRequest(
            competition_season_id=domain.season_id,
            through_week=1,
            trigger=RefreshTrigger.MANUAL,
        )
    )
    before = MatchupManager(session_factory, context).list_matchups(
        domain.season_id, 1
    )

    second = service(
        FixtureSource(domain, failures={EndpointKind.MATCHUPS})
    ).refresh(
        RefreshRequest(
            competition_season_id=domain.season_id,
            through_week=1,
            trigger=RefreshTrigger.SCHEDULED,
        )
    )
    after = MatchupManager(session_factory, context).list_matchups(
        domain.season_id, 1
    )

    assert first.status is RefreshStatus.SUCCEEDED
    assert second.status is RefreshStatus.PARTIAL
    assert tuple(item.source_api_request_id for item in after) == tuple(
        item.source_api_request_id for item in before
    )


class FixtureSource:
    def __init__(
        self,
        domain: Domain,
        *,
        failures: set[EndpointKind] | None = None,
    ) -> None:
        self._domain = domain
        self._failures = failures or set()

    def execute(self, request: EndpointRequest) -> SourceAttempt:
        if request.endpoint_kind in self._failures:
            now = datetime.now(UTC)
            return FailedSourceAttempt(
                endpoint=request,
                requested_at=now,
                completed_at=now,
                status=RequestStatus.HTTP_ERROR,
                http_status=404,
                latency_ms=0,
                error=SanitizedSourceError(
                    code="sleeper_http_error",
                    summary="Sleeper returned HTTP 404",
                ),
            )
        payload = self._payload(request.endpoint_kind)
        content = canonical_json_bytes(payload)
        now = datetime.now(UTC)
        return SuccessfulSourceAttempt(
            endpoint=request,
            requested_at=now,
            completed_at=now,
            http_status=200,
            latency_ms=0,
            payload=payload,
            raw_sha256=hashlib.sha256(content).hexdigest(),
            byte_length=len(content),
            media_type="application/json",
        )

    def _payload(self, kind: EndpointKind) -> Any:
        if kind is EndpointKind.LEAGUE:
            return {
                "league_id": self._domain.sleeper_league_id,
                "name": "Refresh Workflow League",
                "season": "2026",
                "sport": "nfl",
                "settings": {"playoff_week_start": 1, "draft_rounds": 1},
                "scoring_settings": {"rec": 1},
                "roster_positions": ["QB", "RB"],
            }
        if kind is EndpointKind.LEAGUE_USERS:
            return [
                {"user_id": "u1", "display_name": "Alice"},
                {"user_id": "u2", "display_name": "Bob"},
            ]
        if kind is EndpointKind.NFL_STATE:
            return {"season": "2026", "week": 1}
        if kind is EndpointKind.PLAYER_CATALOG:
            return {
                player_id: {"player_id": player_id, "full_name": player_id.upper()}
                for player_id in ("p1", "p2", "p3", "p4")
            }
        if kind is EndpointKind.LEAGUE_ROSTERS:
            return [
                {
                    "roster_id": 1,
                    "owner_id": "u1",
                    "settings": {"wins": 1, "losses": 0, "ties": 0},
                    "metadata": {},
                    "players": ["p1", "p2"],
                    "starters": ["p1"],
                },
                {
                    "roster_id": 2,
                    "owner_id": "u2",
                    "settings": {"wins": 0, "losses": 1, "ties": 0},
                    "metadata": {},
                    "players": ["p3", "p4"],
                    "starters": ["p3"],
                },
            ]
        if kind is EndpointKind.TRADED_PICKS:
            return [
                {"season": "2027", "round": 1, "roster_id": 1, "owner_id": 2}
            ]
        if kind is EndpointKind.MATCHUPS:
            return [
                {
                    "matchup_id": 1,
                    "roster_id": 1,
                    "points": Decimal("100.5"),
                    "starters": ["p1"],
                    "players": ["p1", "p2"],
                    "players_points": {"p1": Decimal("60.5"), "p2": 40},
                },
                {
                    "matchup_id": 1,
                    "roster_id": 2,
                    "points": 90,
                    "starters": ["p3"],
                    "players": ["p3", "p4"],
                    "players_points": {"p3": 55, "p4": 35},
                },
            ]
        if kind is EndpointKind.TRANSACTIONS:
            return [
                {
                    "transaction_id": "tx1",
                    "type": "waiver",
                    "status": "complete",
                    "created": 1700000000,
                    "settings": {"waiver_bid": 5},
                    "metadata": {},
                    "adds": {"p2": 1},
                    "drops": {"p3": 2},
                    "draft_picks": [],
                }
            ]
        if kind in {EndpointKind.WINNERS_BRACKET, EndpointKind.LOSERS_BRACKET}:
            return [
                {"r": 1, "m": 1, "t1": 1, "t2": 2, "w": 1, "l": 2}
            ]
        raise AssertionError(f"unexpected endpoint kind: {kind}")
