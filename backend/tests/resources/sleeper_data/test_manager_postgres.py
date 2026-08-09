from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import os
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import create_engine, func, select

from backend.database.models.core.competitions import Competition, CompetitionSeason
from backend.database.models.core.franchises import Franchise, SeasonRoster
from backend.database.models.sleeper.normalized import (
    DraftPick,
    League,
    Matchup,
    PlayoffMatchup,
    Roster,
)
from backend.database.models.sleeper.requests import ApiPayload, NormalizedScope
from backend.database.sessions import create_session_factory, transaction_session
from backend.resources.context import ActorKind, ManagerContext
from backend.resources.errors import ResourceNotFound
from backend.resources.sleeper_data.manager import SleeperDataManager
from backend.resources.sleeper_data.objects import (
    ApplyDisposition,
    BracketScopeRecords,
    BracketValue,
    CompletenessRecord,
    LeagueScopeRecords,
    LeagueValue,
    MatchupsScopeRecords,
    MatchupValue,
    PayloadReceipt,
    RecordApiAttempt,
    RefreshScopePlan,
    RefreshStatus,
    RequestStatus,
    RosterValue,
    RostersScopeRecords,
    StartRefresh,
    TradedPicksScopeRecords,
    TradedPickValue,
    TransactionMoveValue,
    TransactionsScopeRecords,
    TransactionValue,
)
from backend.tests.database.conftest import (
    _alembic_config,
    _temporary_database,
    _test_database_base_url,
)


@pytest.fixture
def manager_database_url() -> str:
    with _temporary_database(_test_database_base_url()) as test_url:
        old_tls = os.environ.get("AIDAM_MIGRATION_REQUIRE_TLS")
        old_role = os.environ.get("AIDAM_MIGRATION_ROLE")
        os.environ["AIDAM_MIGRATION_REQUIRE_TLS"] = "false"
        os.environ["AIDAM_MIGRATION_ROLE"] = "aidam_owner"
        command.upgrade(_alembic_config(test_url), "head")
        try:
            yield test_url
        finally:
            if old_tls is None:
                os.environ.pop("AIDAM_MIGRATION_REQUIRE_TLS", None)
            else:
                os.environ["AIDAM_MIGRATION_REQUIRE_TLS"] = old_tls
            if old_role is None:
                os.environ.pop("AIDAM_MIGRATION_ROLE", None)
            else:
                os.environ["AIDAM_MIGRATION_ROLE"] = old_role


def test_manager_records_applies_and_orders_one_scope(
    manager_database_url: str,
) -> None:
    engine = create_engine(manager_database_url)
    factory = create_session_factory(engine)
    competition_id = uuid4()
    other_competition_id = uuid4()
    season_id = uuid4()
    other_season_id = uuid4()
    franchise_id = uuid4()
    other_franchise_id = uuid4()
    season_roster_id = uuid4()
    other_season_roster_id = uuid4()
    sleeper_league_id = f"league-{uuid4().hex}"
    with transaction_session(factory) as session:
        session.add(Competition(id=competition_id, display_name="Test League"))
        session.add(
            Competition(id=other_competition_id, display_name="Other League")
        )
        session.add(
            CompetitionSeason(
                id=season_id,
                competition_id=competition_id,
                season_year=2025,
                sequence_number=1,
                sleeper_league_id=sleeper_league_id,
            )
        )
        session.add(
            CompetitionSeason(
                id=other_season_id,
                competition_id=other_competition_id,
                season_year=2025,
                sequence_number=1,
                sleeper_league_id=f"other-{uuid4().hex}",
            )
        )
        session.add(
            Franchise(
                id=franchise_id,
                competition_id=competition_id,
                display_name="Team One",
            )
        )
        session.add(
            Franchise(
                id=other_franchise_id,
                competition_id=competition_id,
                display_name="Team Two",
            )
        )
        session.add(
            SeasonRoster(
                id=season_roster_id,
                competition_id=competition_id,
                competition_season_id=season_id,
                franchise_id=franchise_id,
                sleeper_roster_id="1",
            )
        )
        session.add(
            SeasonRoster(
                id=other_season_roster_id,
                competition_id=competition_id,
                competition_season_id=season_id,
                franchise_id=other_franchise_id,
                sleeper_roster_id="2",
            )
        )

    context = ManagerContext.competition(
        actor_kind=ActorKind.WORKER,
        actor_id="datalayer-test",
        competition_id=competition_id,
    )
    now = datetime(2025, 9, 1, 12, tzinfo=UTC)
    manager = SleeperDataManager(factory, context, clock=lambda: now)
    with pytest.raises(ResourceNotFound):
        manager.get_season_identity_map(other_season_id)
    plan = (
        RefreshScopePlan(
            scope_key=f"league:{season_id}",
            endpoint_kind="league",
            required=True,
        ),
    )
    records = LeagueScopeRecords(
        LeagueValue(
            sleeper_league_id=sleeper_league_id,
            season="2025",
            name="Exact League",
            sport="nfl",
            status="in_season",
            previous_sleeper_league_id=None,
            sleeper_draft_id=None,
            scoring_settings={"rec": 0},
            roster_positions=("QB", "WR"),
            provider_settings={"playoff_week_start": 15},
            playoff_start_week=15,
            playoff_team_count=6,
            league_average_match=0,
        )
    )
    content = '{"league_id":"exact"}'
    receipt = PayloadReceipt(
        sha256=sha256(content.encode()).hexdigest(),
        byte_length=len(content.encode()),
        media_type="application/json",
        inline_json_text=content,
    )

    first_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    assert first_refresh.requested_through_week == 1
    assert first_refresh.effective_through_week == 1
    first_request = manager.record_attempt(
        _attempt_command(
            refresh_id=first_refresh.id,
            season_id=season_id,
            scope_key=plan[0].scope_key,
            receipt=receipt,
            requested_at=now,
        )
    )
    first_apply = manager.apply_scope(first_request.id, records)
    finished = manager.finish_refresh(first_refresh.id)

    assert first_apply.disposition is ApplyDisposition.APPLIED
    assert finished.status is RefreshStatus.SUCCEEDED
    assert finished.attempt_count == 1
    assert manager.get_season_overview(season_id).name == "Exact League"
    verified_payload = manager.resolve_verified_payloads((first_request.id,))[0]
    assert verified_payload.inline_json_text == content

    second_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    second_request = manager.record_attempt(
        _attempt_command(
            refresh_id=second_refresh.id,
            season_id=season_id,
            scope_key=plan[0].scope_key,
            receipt=receipt,
            requested_at=now + timedelta(minutes=1),
        )
    )
    identical = manager.apply_scope(second_request.id, records)

    assert identical.disposition is ApplyDisposition.IDENTICAL_HEAD_ADVANCED
    with transaction_session(factory) as session:
        assert session.get(League, season_id).source_api_request_id == first_request.id
        assert session.get(NormalizedScope, plan[0].scope_key).source_api_request_id == second_request.id
        assert session.scalar(select(func.count()).select_from(ApiPayload)) == 1

    stale_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    stale_content = '{"league_id":"stale"}'
    stale_receipt = PayloadReceipt(
        sha256=sha256(stale_content.encode()).hexdigest(),
        byte_length=len(stale_content.encode()),
        media_type="application/json",
        inline_json_text=stale_content,
    )
    stale_request = manager.record_attempt(
        _attempt_command(
            refresh_id=stale_refresh.id,
            season_id=season_id,
            scope_key=plan[0].scope_key,
            receipt=stale_receipt,
            requested_at=now - timedelta(minutes=1),
        )
    )

    stale = manager.apply_scope(stale_request.id, records)

    assert stale.disposition is ApplyDisposition.STALE_IGNORED
    assert manager.get_season_overview(season_id).name == "Exact League"

    failed_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    manager.record_attempt(
        RecordApiAttempt(
            refresh_run_id=failed_refresh.id,
            competition_season_id=season_id,
            endpoint_kind="league",
            scope_key=plan[0].scope_key,
            request_path="/league/exact",
            request_parameters={},
            week=None,
            bracket_kind=None,
            requested_at=now + timedelta(minutes=2),
            completed_at=now + timedelta(minutes=2, milliseconds=1),
            latency_ms=1,
            status=RequestStatus.HTTP_ERROR,
            http_status=503,
            error={"code": "source_http_error", "summary": "unavailable"},
            completeness=CompletenessRecord(
                is_complete=False,
                code="source_attempt_failed",
                summary="incomplete",
            ),
            payload=None,
        )
    )
    assert manager.finish_refresh(failed_refresh.id).status is RefreshStatus.FAILED
    assert manager.get_season_overview(season_id).name == "Exact League"

    roster_scope = f"rosters:{season_id}"
    roster_plan = (
        RefreshScopePlan(roster_scope, "league_rosters", True),
    )
    populated_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=roster_plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    populated_request = manager.record_attempt(
        _attempt_command(
            refresh_id=populated_refresh.id,
            season_id=season_id,
            scope_key=roster_scope,
            receipt=receipt,
            requested_at=now + timedelta(minutes=3),
            endpoint_kind="league_rosters",
        )
    )
    manager.apply_scope(
        populated_request.id,
        RostersScopeRecords(
            rosters=(
                RosterValue(
                    season_roster_id=season_roster_id,
                    settings={},
                    metadata={},
                    record_string="1-0",
                    wins=1,
                    losses=0,
                    ties=0,
                    points_for=100,
                    points_against=90,
                ),
            ),
            managers=(),
            players=(),
        ),
    )
    empty_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=roster_plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    empty_content = "[]"
    empty_receipt = PayloadReceipt(
        sha256=sha256(empty_content.encode()).hexdigest(),
        byte_length=2,
        media_type="application/json",
        inline_json_text=empty_content,
    )
    empty_request = manager.record_attempt(
        _attempt_command(
            refresh_id=empty_refresh.id,
            season_id=season_id,
            scope_key=roster_scope,
            receipt=empty_receipt,
            requested_at=now + timedelta(minutes=4),
            endpoint_kind="league_rosters",
        )
    )
    empty_apply = manager.apply_scope(
        empty_request.id,
        RostersScopeRecords(rosters=(), managers=(), players=()),
    )
    with transaction_session(factory) as session:
        assert session.scalar(
            select(Roster).where(Roster.competition_season_id == season_id)
        ) is None
    assert empty_apply.disposition is ApplyDisposition.APPLIED
    assert empty_apply.normalized_row_count == 0

    matchup_scope = f"matchups:{season_id}:1"
    matchup_plan = (
        RefreshScopePlan(matchup_scope, "matchups", True),
    )
    populated_matchup_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=matchup_plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    populated_matchup_request = manager.record_attempt(
        _attempt_command(
            refresh_id=populated_matchup_refresh.id,
            season_id=season_id,
            scope_key=matchup_scope,
            receipt=_receipt('[{"roster_id":1}]'),
            requested_at=now + timedelta(minutes=5),
            endpoint_kind="matchups",
            week=1,
        )
    )
    manager.apply_scope(
        populated_matchup_request.id,
        MatchupsScopeRecords(
            week=1,
            matchups=(
                MatchupValue(
                    season_roster_id=season_roster_id,
                    sleeper_matchup_id=1,
                    points=Decimal("100.25"),
                ),
            ),
            player_performances=(),
        ),
    )
    empty_matchup_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=matchup_plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    empty_matchup_request = manager.record_attempt(
        _attempt_command(
            refresh_id=empty_matchup_refresh.id,
            season_id=season_id,
            scope_key=matchup_scope,
            receipt=_receipt("[]"),
            requested_at=now + timedelta(minutes=6),
            endpoint_kind="matchups",
            week=1,
        )
    )
    manager.apply_scope(
        empty_matchup_request.id,
        MatchupsScopeRecords(week=1, matchups=(), player_performances=()),
    )
    with transaction_session(factory) as session:
        assert session.scalar(
            select(Matchup).where(Matchup.competition_season_id == season_id)
        ) is None

    bracket_scope = f"bracket:{season_id}:winners"
    bracket_plan = (
        RefreshScopePlan(bracket_scope, "winners_bracket", True),
    )
    populated_bracket_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=bracket_plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    populated_bracket_request = manager.record_attempt(
        _attempt_command(
            refresh_id=populated_bracket_refresh.id,
            season_id=season_id,
            scope_key=bracket_scope,
            receipt=_receipt('[{"m":1}]'),
            requested_at=now + timedelta(minutes=7),
            endpoint_kind="winners_bracket",
            bracket_kind="winners",
        )
    )
    manager.apply_scope(
        populated_bracket_request.id,
        BracketScopeRecords(
            bracket_kind="winners",
            matchups=(
                BracketValue(
                    node_key="1",
                    round=1,
                    t1_season_roster_id=season_roster_id,
                    t2_season_roster_id=other_season_roster_id,
                    t1_from_node_key=None,
                    t1_from_outcome=None,
                    t2_from_node_key=None,
                    t2_from_outcome=None,
                    winner_season_roster_id=None,
                    loser_season_roster_id=None,
                    placement=None,
                ),
            ),
        ),
    )
    empty_bracket_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=bracket_plan,
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    empty_bracket_request = manager.record_attempt(
        _attempt_command(
            refresh_id=empty_bracket_refresh.id,
            season_id=season_id,
            scope_key=bracket_scope,
            receipt=_receipt("[]"),
            requested_at=now + timedelta(minutes=8),
            endpoint_kind="winners_bracket",
            bracket_kind="winners",
        )
    )
    manager.apply_scope(
        empty_bracket_request.id,
        BracketScopeRecords(bracket_kind="winners", matchups=()),
    )
    with transaction_session(factory) as session:
        assert session.scalar(
            select(PlayoffMatchup).where(
                PlayoffMatchup.competition_season_id == season_id
            )
        ) is None

    traded_scope = f"traded_picks:{season_id}"
    traded_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=(
                RefreshScopePlan(traded_scope, "traded_picks", True),
            ),
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    traded_request = manager.record_attempt(
        _attempt_command(
            refresh_id=traded_refresh.id,
            season_id=season_id,
            scope_key=traded_scope,
            receipt=receipt,
            requested_at=now + timedelta(minutes=9),
            endpoint_kind="traded_picks",
        )
    )
    manager.apply_scope(
        traded_request.id,
        TradedPicksScopeRecords(
            picks=(
                TradedPickValue(
                    draft_season_year=2026,
                    round=1,
                    original_franchise_id=franchise_id,
                    current_franchise_id=other_franchise_id,
                    sleeper_pick_id="pick-1",
                ),
            )
        ),
    )

    transaction_scope = f"transactions:{season_id}:1"
    transaction_refresh = manager.start_refresh(
        StartRefresh(
            competition_season_id=season_id,
            requested_through_week=1,
            endpoint_plan=(
                RefreshScopePlan(transaction_scope, "transactions", True),
            ),
            trigger_source="manual",
            code_version="test",
            normalizer_version="1",
        )
    )
    transaction_request = manager.record_attempt(
        _attempt_command(
            refresh_id=transaction_refresh.id,
            season_id=season_id,
            scope_key=transaction_scope,
            receipt=receipt,
            requested_at=now + timedelta(minutes=10),
            endpoint_kind="transactions",
            week=1,
        )
    )
    manager.apply_scope(
        transaction_request.id,
        TransactionsScopeRecords(
            week=1,
            transactions=(
                TransactionValue(
                    sleeper_transaction_id="transaction-1",
                    transaction_type="trade",
                    status="complete",
                    provider_created_at_ms=1,
                    settings={},
                    metadata={},
                    moves=(
                        TransactionMoveValue(
                            move_index=0,
                            move_kind="pick",
                            from_season_roster_id=other_season_roster_id,
                            to_season_roster_id=season_roster_id,
                            sleeper_player_id=None,
                            draft_season_year=2026,
                            draft_round=1,
                            original_franchise_id=franchise_id,
                            sleeper_pick_id="pick-1",
                            budget_amount=None,
                        ),
                    ),
                ),
            ),
        ),
    )
    with transaction_session(factory) as session:
        pick = session.execute(
            select(DraftPick).where(
                DraftPick.competition_id == competition_id,
                DraftPick.draft_season_year == 2026,
                DraftPick.round == 1,
                DraftPick.original_franchise_id == franchise_id,
            )
        ).scalar_one()
        assert pick.current_franchise_id == other_franchise_id
        assert pick.source_api_request_id == traded_request.id
    engine.dispose()


def _attempt_command(
    *,
    refresh_id,
    season_id,
    scope_key: str,
    receipt: PayloadReceipt,
    requested_at: datetime,
    endpoint_kind: str = "league",
    week: int | None = None,
    bracket_kind: str | None = None,
) -> RecordApiAttempt:
    return RecordApiAttempt(
        refresh_run_id=refresh_id,
        competition_season_id=season_id,
        endpoint_kind=endpoint_kind,
        scope_key=scope_key,
        request_path="/league/exact",
        request_parameters={},
        week=week,
        bracket_kind=bracket_kind,
        requested_at=requested_at,
        completed_at=requested_at + timedelta(milliseconds=1),
        latency_ms=1,
        status=RequestStatus.SUCCEEDED,
        http_status=200,
        error=None,
        completeness=CompletenessRecord(
            is_complete=True,
            code="league_payload_complete",
            summary="complete",
        ),
        payload=receipt,
    )


def _receipt(content: str) -> PayloadReceipt:
    encoded = content.encode()
    return PayloadReceipt(
        sha256=sha256(encoded).hexdigest(),
        byte_length=len(encoded),
        media_type="application/json",
        inline_json_text=content,
    )
