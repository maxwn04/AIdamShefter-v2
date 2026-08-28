"""Normalize one immutable selected payload for snapshot materialization."""

from __future__ import annotations

from typing import assert_never

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.snapshot_selection import SnapshotRequirement
from backend.services.datalayer.sleeper.endpoints import (
    EndpointRecords,
    normalize_league,
    normalize_league_rosters,
    normalize_league_users,
    normalize_losers_bracket,
    normalize_matchups,
    normalize_nfl_state,
    normalize_player_catalog,
    normalize_traded_picks,
    normalize_transactions,
    normalize_winners_bracket,
)
from backend.services.datalayer.sleeper.scope import EndpointKind


def normalize_snapshot_payload(
    payload: JsonValue,
    requirement: SnapshotRequirement,
) -> EndpointRecords:
    """Normalize through the endpoint contract frozen in one requirement."""

    endpoint = requirement.request
    match endpoint.endpoint_kind:
        case EndpointKind.LEAGUE:
            return normalize_league(payload, endpoint)
        case EndpointKind.LEAGUE_USERS:
            return normalize_league_users(payload, endpoint)
        case EndpointKind.LEAGUE_ROSTERS:
            return normalize_league_rosters(payload, endpoint)
        case EndpointKind.NFL_STATE:
            return normalize_nfl_state(payload, endpoint)
        case EndpointKind.PLAYER_CATALOG:
            return normalize_player_catalog(payload, endpoint)
        case EndpointKind.MATCHUPS:
            return normalize_matchups(payload, endpoint)
        case EndpointKind.TRANSACTIONS:
            return normalize_transactions(payload, endpoint)
        case EndpointKind.TRADED_PICKS:
            return normalize_traded_picks(payload, endpoint)
        case EndpointKind.WINNERS_BRACKET:
            return normalize_winners_bracket(payload, endpoint)
        case EndpointKind.LOSERS_BRACKET:
            return normalize_losers_bracket(payload, endpoint)
    assert_never(endpoint.endpoint_kind)


__all__ = ["normalize_snapshot_payload"]
