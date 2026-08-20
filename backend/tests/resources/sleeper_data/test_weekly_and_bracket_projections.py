from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.sleeper import (
    ApiRequest as StoredApiRequest,
    Matchup,
    NormalizedScope,
    PlayerPerformance,
    PlayoffMatchup,
    Transaction,
    TransactionMove,
)
from backend.resources.sleeper_data.normalized_scopes import NormalizedScopeManager
from backend.resources.sleeper_data.refreshes import RefreshRunManager
from backend.resources.sleeper_data.requests import ApiRequestManager
from backend.services.datalayer.contracts import NormalizationStatus
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_rosters_request,
    build_losers_bracket_request,
    build_matchups_request,
    build_player_catalog_request,
    build_transactions_request,
    build_winners_bracket_request,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    BracketMatchupRecord,
    LeagueEndpointRecords,
    LeagueRecord,
    LeagueRostersEndpointRecords,
    LosersBracketEndpointRecords,
    MatchupRecord,
    MatchupsEndpointRecords,
    PlayerCatalogEndpointRecords,
    PlayerPerformanceRecord,
    PlayerRecord,
    RosterRecord,
    TransactionMoveRecord,
    TransactionRecord,
    TransactionsEndpointRecords,
    WinnersBracketEndpointRecords,
)
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


def test_matchups_replace_exact_week_child_first_and_accept_complete_empty(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    catalog = build_player_catalog_request()
    week_one = build_matchups_request(domain.season_id, domain.sleeper_league_id, 1)
    week_two = build_matchups_request(domain.season_id, domain.sleeper_league_id, 2)
    refresh = start_refresh(
        refresh_manager, domain, catalog, week_one, week_two, requested_through_week=2
    )
    now = datetime.now(UTC)
    player_request = record_complete_attempt(
        request_manager, refresh.id, catalog, {"players": 1}, requested_at=now
    )
    normalized_scope_manager.apply_scope(
        player_request.id,
        PlayerCatalogEndpointRecords(
            players=(
                PlayerRecord(sleeper_player_id="p1", full_name="One", metadata={}),
            )
        ),
    )
    week_requests = []
    for week, endpoint in ((1, week_one), (2, week_two)):
        request = record_complete_attempt(
            request_manager,
            refresh.id,
            endpoint,
            {"week": week},
            requested_at=now + timedelta(seconds=week),
        )
        normalized_scope_manager.apply_scope(
            request.id,
            MatchupsEndpointRecords(
                matchups=(
                    MatchupRecord(
                        week=week,
                        sleeper_roster_id="1",
                        sleeper_matchup_id=week,
                        points=Decimal(10 + week),
                    ),
                ),
                player_performances=(
                    PlayerPerformanceRecord(
                        week=week,
                        sleeper_roster_id="1",
                        sleeper_matchup_id=week,
                        sleeper_player_id="p1",
                        points=Decimal(week),
                        role="starter",
                    ),
                ),
            ),
        )
        week_requests.append(request)
    empty = record_complete_attempt(
        request_manager,
        refresh.id,
        week_one,
        [],
        requested_at=now + timedelta(seconds=3),
    )
    result = normalized_scope_manager.apply_scope(
        empty.id, MatchupsEndpointRecords(matchups=(), player_performances=())
    )

    assert result.normalized_row_count == 0
    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(Matchup.week, Matchup.source_api_request_id)
        ).all() == [(2, week_requests[1].id)]
        assert connection.execute(
            sa.select(PlayerPerformance.week, PlayerPerformance.source_api_request_id)
        ).all() == [(2, week_requests[1].id)]
        assert (
            connection.scalar(
                sa.select(NormalizedScope.normalized_row_count).where(
                    NormalizedScope.scope_key == week_one.scope_key.value
                )
            )
            == 0
        )


def test_transactions_replace_exact_week_and_roll_back_invalid_pick_move(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    league = build_league_request(domain.season_id, domain.sleeper_league_id)
    rosters = build_league_rosters_request(domain.season_id, domain.sleeper_league_id)
    week_one = build_transactions_request(domain.season_id, domain.sleeper_league_id, 1)
    week_two = build_transactions_request(domain.season_id, domain.sleeper_league_id, 2)
    refresh = start_refresh(
        refresh_manager,
        domain,
        league,
        rosters,
        week_one,
        week_two,
        requested_through_week=2,
    )
    now = datetime.now(UTC)
    league_request = record_complete_attempt(
        request_manager, refresh.id, league, {"league": 1}, requested_at=now
    )
    normalized_scope_manager.apply_scope(
        league_request.id,
        LeagueEndpointRecords(
            league=LeagueRecord(
                sleeper_league_id=domain.sleeper_league_id,
                name="Transaction League",
                season="2026",
                sport="nfl",
                scoring_settings={},
                roster_positions=(),
                provider_settings={"draft_rounds": 1},
            )
        ),
    )
    roster_request = record_complete_attempt(
        request_manager,
        refresh.id,
        rosters,
        {"rosters": 1},
        requested_at=now + timedelta(milliseconds=1),
    )
    normalized_scope_manager.apply_scope(
        roster_request.id,
        LeagueRostersEndpointRecords(
            rosters=(_roster_record("1"), _roster_record("2")),
            managers=(),
            players=(),
        ),
    )
    good_requests = []
    for week, endpoint in ((1, week_one), (2, week_two)):
        request = record_complete_attempt(
            request_manager,
            refresh.id,
            endpoint,
            {"week": week},
            requested_at=now + timedelta(seconds=week),
        )
        normalized_scope_manager.apply_scope(
            request.id,
            TransactionsEndpointRecords(
                transactions=(
                    TransactionRecord(
                        week=week,
                        sleeper_transaction_id=f"tx{week}",
                        transaction_type="trade",
                        settings={},
                        metadata={},
                    ),
                ),
                moves=(
                    TransactionMoveRecord(
                        sleeper_transaction_id=f"tx{week}",
                        move_index=0,
                        move_kind="pick",
                        from_sleeper_roster_id="1",
                        to_sleeper_roster_id="2",
                        draft_season_year=2027,
                        draft_round=1,
                        original_sleeper_roster_id="1",
                    ),
                ),
            ),
        )
        good_requests.append(request)
    bad = record_complete_attempt(
        request_manager,
        refresh.id,
        week_one,
        {"week": 1, "bad": True},
        requested_at=now + timedelta(seconds=3),
    )
    with pytest.raises(DatalayerScopeConflict, match="seeded coordinates"):
        normalized_scope_manager.apply_scope(
            bad.id,
            TransactionsEndpointRecords(
                transactions=(
                    TransactionRecord(
                        week=1,
                        sleeper_transaction_id="bad",
                        transaction_type="trade",
                        settings={},
                        metadata={},
                    ),
                ),
                moves=(
                    TransactionMoveRecord(
                        sleeper_transaction_id="bad",
                        move_index=0,
                        move_kind="pick",
                        draft_season_year=2099,
                        draft_round=1,
                        original_sleeper_roster_id="1",
                    ),
                ),
            ),
        )

    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(
                Transaction.week,
                Transaction.sleeper_transaction_id,
                Transaction.source_api_request_id,
            ).order_by(Transaction.week)
        ).all() == [
            (1, "tx1", good_requests[0].id),
            (2, "tx2", good_requests[1].id),
        ]
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(TransactionMove))
            == 2
        )
        assert (
            connection.scalar(
                sa.select(NormalizedScope.source_api_request_id).where(
                    NormalizedScope.scope_key == week_one.scope_key.value
                )
            )
            == good_requests[0].id
        )
        assert (
            connection.scalar(
                sa.select(StoredApiRequest.normalization_status).where(
                    StoredApiRequest.id == bad.id
                )
            )
            == NormalizationStatus.PENDING.value
        )


def test_playoff_brackets_replace_exact_kind(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    winners = build_winners_bracket_request(domain.season_id, domain.sleeper_league_id)
    losers = build_losers_bracket_request(domain.season_id, domain.sleeper_league_id)
    refresh = start_refresh(refresh_manager, domain, winners, losers)
    now = datetime.now(UTC)
    winner_request = record_complete_attempt(
        request_manager, refresh.id, winners, {"winners": 1}, requested_at=now
    )
    normalized_scope_manager.apply_scope(
        winner_request.id,
        WinnersBracketEndpointRecords(
            matchups=(
                BracketMatchupRecord(
                    bracket_kind="winners",
                    node_key="w1",
                    round=1,
                    t1_sleeper_roster_id="1",
                    t2_sleeper_roster_id="2",
                    winner_sleeper_roster_id="1",
                    loser_sleeper_roster_id="2",
                ),
            )
        ),
    )
    loser_request = record_complete_attempt(
        request_manager,
        refresh.id,
        losers,
        {"losers": 1},
        requested_at=now + timedelta(seconds=1),
    )
    normalized_scope_manager.apply_scope(
        loser_request.id,
        LosersBracketEndpointRecords(
            matchups=(
                BracketMatchupRecord(
                    bracket_kind="losers",
                    node_key="l1",
                    round=1,
                    t1_sleeper_roster_id="1",
                    t2_sleeper_roster_id="2",
                    winner_sleeper_roster_id="2",
                    loser_sleeper_roster_id="1",
                ),
            )
        ),
    )
    empty = record_complete_attempt(
        request_manager,
        refresh.id,
        winners,
        [],
        requested_at=now + timedelta(seconds=2),
    )
    normalized_scope_manager.apply_scope(
        empty.id, WinnersBracketEndpointRecords(matchups=())
    )

    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(
                PlayoffMatchup.bracket_kind,
                PlayoffMatchup.node_key,
                PlayoffMatchup.winner_season_roster_id,
                PlayoffMatchup.source_api_request_id,
            )
        ).all() == [("losers", "l1", domain.roster_ids[1], loser_request.id)]
        assert connection.execute(
            sa.select(
                NormalizedScope.scope_key,
                NormalizedScope.source_api_request_id,
                NormalizedScope.normalized_row_count,
            )
            .where(
                NormalizedScope.scope_key.in_(
                    (winners.scope_key.value, losers.scope_key.value)
                )
            )
            .order_by(NormalizedScope.scope_key)
        ).all() == [
            (losers.scope_key.value, loser_request.id, 1),
            (winners.scope_key.value, empty.id, 0),
        ]
