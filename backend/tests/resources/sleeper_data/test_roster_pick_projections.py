from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from backend.database.models.sleeper import (
    ApiRequest as StoredApiRequest,
    DraftPick,
    NormalizedScope,
    Roster,
    RosterManager,
    RosterPlayer,
)
from backend.resources.sleeper_data.normalized_scopes import NormalizedScopeManager
from backend.resources.sleeper_data.refreshes import RefreshRun, RefreshRunManager
from backend.resources.sleeper_data.requests import ApiRequestManager
from backend.services.datalayer.contracts import NormalizationStatus
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_rosters_request,
    build_league_users_request,
    build_player_catalog_request,
    build_traded_picks_request,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    LeagueEndpointRecords,
    LeagueRecord,
    LeagueRostersEndpointRecords,
    LeagueUserRecord,
    LeagueUsersEndpointRecords,
    PlayerCatalogEndpointRecords,
    PlayerRecord,
    RosterManagerRecord,
    RosterPlayerRecord,
    RosterRecord,
    TradedPickRecord,
    TradedPicksEndpointRecords,
    UserRecord,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.tests.resources.sleeper_data.conftest import (
    Domain,
    record_complete_attempt,
    start_refresh,
)


def _roster_record(roster_id: str) -> RosterRecord:
    return RosterRecord(
        sleeper_roster_id=roster_id,
        settings={},
        metadata={},
        wins=0,
        losses=0,
        ties=0,
        points_for=Decimal(0),
        points_against=Decimal(0),
    )


def _start_roster_refresh(
    domain: Domain,
    refresh_manager: RefreshRunManager,
    *,
    include_traded_picks: bool = False,
) -> tuple[RefreshRun, tuple[EndpointRequest, ...]]:
    endpoints = (
        build_league_request(domain.season_id, domain.sleeper_league_id),
        build_league_users_request(domain.season_id, domain.sleeper_league_id),
        build_player_catalog_request(),
        build_league_rosters_request(domain.season_id, domain.sleeper_league_id),
    )
    if include_traded_picks:
        endpoints += (
            build_traded_picks_request(domain.season_id, domain.sleeper_league_id),
        )
    return start_refresh(refresh_manager, domain, *endpoints), endpoints


def _apply_roster_prerequisites(
    domain: Domain,
    request_manager: ApiRequestManager,
    scope_manager: NormalizedScopeManager,
    refresh: RefreshRun,
    endpoints: tuple[EndpointRequest, ...],
    now: datetime,
) -> None:
    league = record_complete_attempt(
        request_manager, refresh.id, endpoints[0], {"league": 1}, requested_at=now
    )
    scope_manager.apply_scope(
        league.id,
        LeagueEndpointRecords(
            league=LeagueRecord(
                sleeper_league_id=domain.sleeper_league_id,
                name="Roster League",
                season="2026",
                sport="nfl",
                scoring_settings={},
                roster_positions=("QB",),
                provider_settings={"draft_rounds": 2},
            )
        ),
    )
    users = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[1],
        {"users": 1},
        requested_at=now + timedelta(milliseconds=1),
    )
    scope_manager.apply_scope(
        users.id,
        LeagueUsersEndpointRecords(
            users=(
                UserRecord(sleeper_user_id="u1", display_name="One", metadata={}),
                UserRecord(sleeper_user_id="u2", display_name="Two", metadata={}),
            ),
            league_users=(
                LeagueUserRecord(sleeper_user_id="u1", metadata={}),
                LeagueUserRecord(sleeper_user_id="u2", metadata={}),
            ),
        ),
    )
    players = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[2],
        {"players": 1},
        requested_at=now + timedelta(milliseconds=2),
    )
    scope_manager.apply_scope(
        players.id,
        PlayerCatalogEndpointRecords(
            players=(
                PlayerRecord(sleeper_player_id="p1", full_name="One", metadata={}),
            )
        ),
    )


def test_rosters_replace_children_and_seed_three_year_pick_coordinates(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    refresh, endpoints = _start_roster_refresh(domain, refresh_manager)
    now = datetime.now(UTC)
    _apply_roster_prerequisites(
        domain, request_manager, normalized_scope_manager, refresh, endpoints, now
    )
    first = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[3],
        {"rosters": 1},
        requested_at=now + timedelta(seconds=1),
    )
    first_result = normalized_scope_manager.apply_scope(
        first.id,
        LeagueRostersEndpointRecords(
            rosters=(_roster_record("1"), _roster_record("2")),
            managers=(
                RosterManagerRecord(
                    sleeper_roster_id="1",
                    sleeper_user_id="u1",
                    role="owner",
                    source_order=0,
                ),
                RosterManagerRecord(
                    sleeper_roster_id="2",
                    sleeper_user_id="u2",
                    role="owner",
                    source_order=0,
                ),
            ),
            players=(
                RosterPlayerRecord(
                    sleeper_roster_id="1", sleeper_player_id="p1", role="starter"
                ),
            ),
        ),
    )
    second = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[3],
        [],
        requested_at=now + timedelta(seconds=2),
    )
    second_result = normalized_scope_manager.apply_scope(
        second.id,
        LeagueRostersEndpointRecords(
            rosters=(_roster_record("2"),), managers=(), players=()
        ),
    )

    assert (first_result.normalized_row_count, second_result.normalized_row_count) == (
        5,
        1,
    )
    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(Roster.season_roster_id, Roster.source_api_request_id)
        ).all() == [(domain.roster_ids[1], second.id)]
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(RosterManager))
            == 0
        )
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(RosterPlayer)) == 0
        )
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(DraftPick)) == 12
        )


def test_traded_picks_reset_and_reapply_complete_ownership_view(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    refresh, endpoints = _start_roster_refresh(
        domain, refresh_manager, include_traded_picks=True
    )
    now = datetime.now(UTC)
    _apply_roster_prerequisites(
        domain, request_manager, normalized_scope_manager, refresh, endpoints, now
    )
    rosters = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[3],
        {"rosters": 1},
        requested_at=now + timedelta(seconds=1),
    )
    normalized_scope_manager.apply_scope(
        rosters.id,
        LeagueRostersEndpointRecords(
            rosters=(_roster_record("1"), _roster_record("2")),
            managers=(),
            players=(),
        ),
    )
    traded = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[4],
        {"traded": 1},
        requested_at=now + timedelta(seconds=2),
    )
    normalized_scope_manager.apply_scope(
        traded.id,
        TradedPicksEndpointRecords(
            picks=(
                TradedPickRecord(
                    draft_season_year=2027,
                    draft_round=1,
                    original_sleeper_roster_id="1",
                    current_owner_sleeper_roster_id="2",
                ),
            )
        ),
    )
    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(DraftPick.current_franchise_id, DraftPick.source).where(
                DraftPick.competition_id == domain.competition_id,
                DraftPick.draft_season_year == 2027,
                DraftPick.round == 1,
                DraftPick.original_franchise_id == domain.franchise_ids[0],
            )
        ).one() == (domain.franchise_ids[1], "traded_pick")

    empty = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[4],
        [],
        requested_at=now + timedelta(seconds=3),
    )
    normalized_scope_manager.apply_scope(empty.id, TradedPicksEndpointRecords(picks=()))
    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(
                DraftPick.current_franchise_id,
                DraftPick.source,
                DraftPick.source_api_request_id,
            ).where(
                DraftPick.competition_id == domain.competition_id,
                DraftPick.draft_season_year == 2027,
                DraftPick.round == 1,
                DraftPick.original_franchise_id == domain.franchise_ids[0],
            )
        ).one() == (domain.franchise_ids[0], "seeded", empty.id)


def test_roster_constraint_failure_rolls_back_replacement_and_head(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    refresh, endpoints = _start_roster_refresh(domain, refresh_manager)
    now = datetime.now(UTC)
    _apply_roster_prerequisites(
        domain, request_manager, normalized_scope_manager, refresh, endpoints, now
    )
    good = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[3],
        {"version": 1},
        requested_at=now + timedelta(seconds=1),
    )
    normalized_scope_manager.apply_scope(
        good.id,
        LeagueRostersEndpointRecords(
            rosters=(_roster_record("1"),),
            managers=(
                RosterManagerRecord(
                    sleeper_roster_id="1",
                    sleeper_user_id="u1",
                    role="owner",
                    source_order=0,
                ),
            ),
            players=(),
        ),
    )
    bad = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoints[3],
        {"version": 2},
        requested_at=now + timedelta(seconds=2),
    )
    with pytest.raises(IntegrityError):
        normalized_scope_manager.apply_scope(
            bad.id,
            LeagueRostersEndpointRecords(
                rosters=(_roster_record("1"),),
                managers=(
                    RosterManagerRecord(
                        sleeper_roster_id="1",
                        sleeper_user_id="u1",
                        role="owner",
                        source_order=0,
                    ),
                    RosterManagerRecord(
                        sleeper_roster_id="1",
                        sleeper_user_id="u2",
                        role="owner",
                        source_order=1,
                    ),
                ),
                players=(),
            ),
        )

    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(Roster.source_api_request_id, RosterManager.sleeper_user_id).join(
                RosterManager, RosterManager.season_roster_id == Roster.season_roster_id
            )
        ).one() == (good.id, "u1")
        assert (
            connection.scalar(
                sa.select(NormalizedScope.source_api_request_id).where(
                    NormalizedScope.scope_key == endpoints[3].scope_key.value
                )
            )
            == good.id
        )
        assert (
            connection.scalar(
                sa.select(StoredApiRequest.normalization_status).where(
                    StoredApiRequest.id == bad.id
                )
            )
            == NormalizationStatus.PENDING.value
        )
