from __future__ import annotations

from uuid import UUID

import pytest

from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_rosters_request,
    build_league_users_request,
    build_losers_bracket_request,
    build_matchups_request,
    build_nfl_state_request,
    build_player_catalog_request,
    build_traded_picks_request,
    build_transactions_request,
    build_winners_bracket_request,
    get_endpoint_apply_metadata,
    missing_dependency_scope_keys,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")


def _requests() -> dict[EndpointKind, EndpointRequest]:
    return {
        EndpointKind.LEAGUE: build_league_request(SEASON_ID, "123"),
        EndpointKind.LEAGUE_USERS: build_league_users_request(SEASON_ID, "123"),
        EndpointKind.LEAGUE_ROSTERS: build_league_rosters_request(SEASON_ID, "123"),
        EndpointKind.NFL_STATE: build_nfl_state_request(),
        EndpointKind.PLAYER_CATALOG: build_player_catalog_request(),
        EndpointKind.MATCHUPS: build_matchups_request(SEASON_ID, "123", 8),
        EndpointKind.TRANSACTIONS: build_transactions_request(SEASON_ID, "123", 8),
        EndpointKind.TRADED_PICKS: build_traded_picks_request(SEASON_ID, "123"),
        EndpointKind.WINNERS_BRACKET: build_winners_bracket_request(SEASON_ID, "123"),
        EndpointKind.LOSERS_BRACKET: build_losers_bracket_request(SEASON_ID, "123"),
    }


def test_apply_metadata_is_exhaustive_and_has_deterministic_stages() -> None:
    requests = _requests()

    assert set(requests) == set(EndpointKind)
    assert {
        kind: get_endpoint_apply_metadata(request).apply_stage
        for kind, request in requests.items()
    } == {
        EndpointKind.LEAGUE: 1,
        EndpointKind.LEAGUE_USERS: 1,
        EndpointKind.NFL_STATE: 1,
        EndpointKind.PLAYER_CATALOG: 1,
        EndpointKind.LEAGUE_ROSTERS: 2,
        EndpointKind.MATCHUPS: 3,
        EndpointKind.TRANSACTIONS: 3,
        EndpointKind.TRADED_PICKS: 3,
        EndpointKind.WINNERS_BRACKET: 3,
        EndpointKind.LOSERS_BRACKET: 3,
    }
    ordered = sorted(
        requests.values(),
        key=lambda request: (
            get_endpoint_apply_metadata(request).apply_stage,
            request.scope_key.value,
        ),
    )
    assert [
        get_endpoint_apply_metadata(request).apply_stage for request in ordered
    ] == sorted(
        get_endpoint_apply_metadata(request).apply_stage
        for request in requests.values()
    )


def test_apply_metadata_declares_concrete_dependency_scopes() -> None:
    requests = _requests()
    roster_scope = ScopeKey.from_parts(EndpointKind.LEAGUE_ROSTERS, SEASON_ID)
    player_scope = ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl")

    assert get_endpoint_apply_metadata(
        requests[EndpointKind.LEAGUE_ROSTERS]
    ).dependency_scope_keys == (
        ScopeKey.from_parts(EndpointKind.LEAGUE, SEASON_ID),
        ScopeKey.from_parts(EndpointKind.LEAGUE_USERS, SEASON_ID),
        player_scope,
    )
    for kind in (EndpointKind.MATCHUPS, EndpointKind.TRANSACTIONS):
        assert get_endpoint_apply_metadata(requests[kind]).dependency_scope_keys == (
            roster_scope,
            player_scope,
        )
    for kind in (
        EndpointKind.TRADED_PICKS,
        EndpointKind.WINNERS_BRACKET,
        EndpointKind.LOSERS_BRACKET,
    ):
        assert get_endpoint_apply_metadata(requests[kind]).dependency_scope_keys == (
            roster_scope,
        )


def test_missing_dependencies_are_reported_in_declaration_order() -> None:
    metadata = get_endpoint_apply_metadata(
        build_league_rosters_request(SEASON_ID, "123")
    )
    available = [ScopeKey.from_parts(EndpointKind.LEAGUE, SEASON_ID)]

    assert missing_dependency_scope_keys(metadata, available) == (
        ScopeKey.from_parts(EndpointKind.LEAGUE_USERS, SEASON_ID),
        ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl"),
    )


def test_dependency_metadata_rejects_noncanonical_scope() -> None:
    request = EndpointRequest(
        endpoint_kind=EndpointKind.MATCHUPS,
        scope_key=ScopeKey.from_parts(EndpointKind.TRANSACTIONS, SEASON_ID, 8),
        path="/league/123/matchups/8",
        week=8,
    )

    with pytest.raises(ValueError, match="invalid matchups scope"):
        get_endpoint_apply_metadata(request)
