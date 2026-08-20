from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.sleeper import (
    ApiRequest as StoredApiRequest,
    League,
    LeagueUser,
    NormalizedScope,
    Player,
    User,
)
from backend.database.sessions import SessionFactory
from backend.resources.sleeper_data.normalized_scopes import NormalizedScopeManager
from backend.resources.sleeper_data.refreshes import RefreshRunManager
from backend.resources.sleeper_data.requests import ApiRequestManager
from backend.services.datalayer.contracts import NormalizationStatus
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_users_request,
    build_player_catalog_request,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    LeagueEndpointRecords,
    LeagueRecord,
    LeagueUserRecord,
    LeagueUsersEndpointRecords,
    PlayerCatalogEndpointRecords,
    PlayerRecord,
    UserRecord,
)
from backend.tests.resources.sleeper_data.conftest import (
    Domain,
    manager_context,
    record_complete_attempt,
    seed_domain,
    start_refresh,
)


def test_league_projection_upserts_matching_season_and_rejects_identity_drift(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    endpoint = build_league_request(domain.season_id, domain.sleeper_league_id)
    refresh = start_refresh(refresh_manager, domain, endpoint)
    now = datetime.now(UTC)
    good = record_complete_attempt(
        request_manager, refresh.id, endpoint, {"version": 1}, requested_at=now
    )
    normalized_scope_manager.apply_scope(
        good.id,
        LeagueEndpointRecords(
            league=LeagueRecord(
                sleeper_league_id=domain.sleeper_league_id,
                name="Projection League",
                season="2026",
                sport="nfl",
                scoring_settings={"bonus": 1.125},
                roster_positions=("QB", "RB"),
                provider_settings={"draft_rounds": 2},
            )
        ),
    )
    bad = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        {"version": 2},
        requested_at=now + timedelta(seconds=1),
    )
    with pytest.raises(DatalayerScopeConflict, match="core season identity"):
        normalized_scope_manager.apply_scope(
            bad.id,
            LeagueEndpointRecords(
                league=LeagueRecord(
                    sleeper_league_id="wrong-league",
                    name="Bad League",
                    season="2026",
                    sport="nfl",
                    scoring_settings={},
                    roster_positions=(),
                    provider_settings={},
                )
            ),
        )

    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(
                League.name,
                League.roster_positions,
                League.provider_settings,
                League.source_api_request_id,
            ).where(League.competition_season_id == domain.season_id)
        ).one() == (
            "Projection League",
            ["QB", "RB"],
            {"draft_rounds": 2},
            good.id,
        )
        assert (
            connection.scalar(
                sa.select(NormalizedScope.source_api_request_id).where(
                    NormalizedScope.scope_key == endpoint.scope_key.value
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


def test_league_users_replace_membership_but_order_global_profiles_across_competitions(
    database_engine: Engine,
    domain: Domain,
    session_factory: SessionFactory,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    other = seed_domain(database_engine, label="Other")
    other_context = manager_context(other)
    other_refresh_manager = RefreshRunManager(session_factory, other_context)
    other_request_manager = ApiRequestManager(session_factory, other_context)
    other_scope_manager = NormalizedScopeManager(session_factory, other_context)
    endpoint = build_league_users_request(domain.season_id, domain.sleeper_league_id)
    other_endpoint = build_league_users_request(
        other.season_id, other.sleeper_league_id
    )
    refresh = start_refresh(refresh_manager, domain, endpoint)
    other_refresh = start_refresh(other_refresh_manager, other, other_endpoint)
    now = datetime.now(UTC)
    newer = record_complete_attempt(
        other_request_manager,
        other_refresh.id,
        other_endpoint,
        {"name": "new"},
        requested_at=now + timedelta(seconds=2),
    )
    other_scope_manager.apply_scope(
        newer.id,
        LeagueUsersEndpointRecords(
            users=(
                UserRecord(sleeper_user_id="shared", display_name="New", metadata={}),
            ),
            league_users=(
                LeagueUserRecord(sleeper_user_id="shared", team_name="B", metadata={}),
            ),
        ),
    )
    older = record_complete_attempt(
        request_manager, refresh.id, endpoint, {"name": "old"}, requested_at=now
    )
    normalized_scope_manager.apply_scope(
        older.id,
        LeagueUsersEndpointRecords(
            users=(
                UserRecord(sleeper_user_id="shared", display_name="Old", metadata={}),
            ),
            league_users=(
                LeagueUserRecord(sleeper_user_id="shared", team_name="A", metadata={}),
            ),
        ),
    )
    empty = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        [],
        requested_at=now + timedelta(seconds=3),
    )
    normalized_scope_manager.apply_scope(
        empty.id, LeagueUsersEndpointRecords(users=(), league_users=())
    )

    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(User.display_name, User.source_api_request_id).where(
                User.sleeper_user_id == "shared"
            )
        ).one() == ("New", newer.id)
        assert connection.execute(
            sa.select(
                LeagueUser.competition_season_id,
                LeagueUser.team_name,
                LeagueUser.source_api_request_id,
            )
        ).all() == [(other.season_id, "B", newer.id)]


def test_player_catalog_upserts_observed_players_without_deleting_omissions(
    database_engine: Engine,
    domain: Domain,
    refresh_manager: RefreshRunManager,
    request_manager: ApiRequestManager,
    normalized_scope_manager: NormalizedScopeManager,
) -> None:
    endpoint = build_player_catalog_request()
    refresh = start_refresh(refresh_manager, domain, endpoint)
    now = datetime.now(UTC)
    first = record_complete_attempt(
        request_manager, refresh.id, endpoint, {"version": 1}, requested_at=now
    )
    normalized_scope_manager.apply_scope(
        first.id,
        PlayerCatalogEndpointRecords(
            players=(
                PlayerRecord(sleeper_player_id="p1", full_name="Before", metadata={}),
                PlayerRecord(sleeper_player_id="p2", full_name="Omitted", metadata={}),
            )
        ),
    )
    second = record_complete_attempt(
        request_manager,
        refresh.id,
        endpoint,
        {"version": 2},
        requested_at=now + timedelta(seconds=1),
    )
    result = normalized_scope_manager.apply_scope(
        second.id,
        PlayerCatalogEndpointRecords(
            players=(
                PlayerRecord(sleeper_player_id="p1", full_name="After", metadata={}),
            )
        ),
    )

    assert result.normalized_row_count == 1
    with database_engine.connect() as connection:
        assert connection.execute(
            sa.select(
                Player.sleeper_player_id,
                Player.full_name,
                Player.source_api_request_id,
            ).order_by(Player.sleeper_player_id)
        ).all() == [
            ("p1", "After", second.id),
            ("p2", "Omitted", first.id),
        ]
        assert (
            connection.scalar(
                sa.select(NormalizedScope.normalized_row_count).where(
                    NormalizedScope.scope_key == endpoint.scope_key.value
                )
            )
            == 1
        )
