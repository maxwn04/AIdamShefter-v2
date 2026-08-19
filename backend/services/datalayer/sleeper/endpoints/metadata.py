"""Pure apply ordering and dependency declarations for Sleeper endpoints."""

from __future__ import annotations

from typing import Iterable, assert_never
from uuid import UUID

from backend.services.datalayer.sleeper.endpoints.contracts import (
    EndpointApplyMetadata,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


def get_endpoint_apply_metadata(request: EndpointRequest) -> EndpointApplyMetadata:
    """Return deterministic apply stage and concrete prerequisite scopes."""

    kind = request.endpoint_kind
    if kind in {
        EndpointKind.LEAGUE,
        EndpointKind.LEAGUE_USERS,
        EndpointKind.NFL_STATE,
        EndpointKind.PLAYER_CATALOG,
    }:
        _validate_stage_one_scope(request)
        return EndpointApplyMetadata(apply_stage=1)

    season_id = _competition_season_id(request)
    roster_scope = ScopeKey.from_parts(EndpointKind.LEAGUE_ROSTERS, season_id)
    player_scope = ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl")
    if kind is EndpointKind.LEAGUE_ROSTERS:
        return EndpointApplyMetadata(
            apply_stage=2,
            dependency_scope_keys=(
                ScopeKey.from_parts(EndpointKind.LEAGUE, season_id),
                ScopeKey.from_parts(EndpointKind.LEAGUE_USERS, season_id),
                player_scope,
            ),
        )
    if kind in {EndpointKind.MATCHUPS, EndpointKind.TRANSACTIONS}:
        return EndpointApplyMetadata(
            apply_stage=3,
            dependency_scope_keys=(roster_scope, player_scope),
        )
    if kind in {
        EndpointKind.TRADED_PICKS,
        EndpointKind.WINNERS_BRACKET,
        EndpointKind.LOSERS_BRACKET,
    }:
        return EndpointApplyMetadata(
            apply_stage=3,
            dependency_scope_keys=(roster_scope,),
        )
    assert_never(kind)


def missing_dependency_scope_keys(
    metadata: EndpointApplyMetadata,
    available_scope_keys: Iterable[ScopeKey],
) -> tuple[ScopeKey, ...]:
    """Return declared prerequisites absent from the available scope set."""

    available = set(available_scope_keys)
    return tuple(
        scope_key
        for scope_key in metadata.dependency_scope_keys
        if scope_key not in available
    )


def _competition_season_id(request: EndpointRequest) -> UUID:
    parts = request.scope_key.value.split(":")
    expected_parts = (
        3
        if request.endpoint_kind
        in {
            EndpointKind.MATCHUPS,
            EndpointKind.TRANSACTIONS,
            EndpointKind.WINNERS_BRACKET,
            EndpointKind.LOSERS_BRACKET,
        }
        else 2
    )
    if len(parts) != expected_parts or parts[0] != request.endpoint_kind.value:
        raise ValueError(
            f"request has an invalid {request.endpoint_kind.value} scope key"
        )
    if request.endpoint_kind in {EndpointKind.MATCHUPS, EndpointKind.TRANSACTIONS}:
        if request.week is None or parts[2] != str(request.week):
            raise ValueError(
                f"request has an invalid {request.endpoint_kind.value} scope key"
            )
    if request.endpoint_kind in {
        EndpointKind.WINNERS_BRACKET,
        EndpointKind.LOSERS_BRACKET,
    }:
        expected_kind = (
            "winners"
            if request.endpoint_kind is EndpointKind.WINNERS_BRACKET
            else "losers"
        )
        if request.bracket_kind != expected_kind or parts[2] != expected_kind:
            raise ValueError(
                f"request has an invalid {request.endpoint_kind.value} scope key"
            )
    try:
        return UUID(parts[1])
    except ValueError as error:
        raise ValueError(
            f"request has an invalid {request.endpoint_kind.value} scope key"
        ) from error


def _validate_stage_one_scope(request: EndpointRequest) -> None:
    if request.endpoint_kind in {EndpointKind.NFL_STATE, EndpointKind.PLAYER_CATALOG}:
        expected = ScopeKey.from_parts(request.endpoint_kind, "nfl")
        if request.scope_key != expected:
            raise ValueError(
                f"request has an invalid {request.endpoint_kind.value} scope key"
            )
        return
    parts = request.scope_key.value.split(":")
    if len(parts) != 2 or parts[0] != request.endpoint_kind.value:
        raise ValueError(
            f"request has an invalid {request.endpoint_kind.value} scope key"
        )
    try:
        UUID(parts[1])
    except ValueError as error:
        raise ValueError(
            f"request has an invalid {request.endpoint_kind.value} scope key"
        ) from error
