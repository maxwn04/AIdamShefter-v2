"""Exhaustive endpoint-family dispatch shared by refresh and snapshot replay."""

from typing import TypeAlias, assert_never

from backend.json import JsonValue
from backend.sleeper import EndpointKind
from .endpoints.brackets import (
    BracketMatchupRecord,
    normalize_bracket,
    validate_bracket_completeness,
)
from .endpoints.league import (
    LeagueRecord,
    LeagueUsersEndpointRecords,
    NflStateRecord,
    normalize_league,
    normalize_league_users,
    normalize_nfl_state,
    validate_league_completeness,
    validate_league_users_completeness,
    validate_nfl_state_completeness,
)
from .endpoints.players import (
    PlayerRecord,
    normalize_player_catalog,
    validate_player_catalog_completeness,
)
from .endpoints.rosters import (
    RosterEndpointRecords,
    TradedPickRecord,
    normalize_rosters,
    normalize_traded_picks,
    validate_rosters_completeness,
    validate_traded_picks_completeness,
)
from .endpoints.weekly import (
    MatchupEndpointRecords,
    TransactionEndpointRecords,
    normalize_matchups,
    normalize_transactions,
    validate_matchups_completeness,
    validate_transactions_completeness,
)
from .responses import CompletenessFinding, EndpointRequest

EndpointRecords: TypeAlias = (
    LeagueRecord
    | LeagueUsersEndpointRecords
    | NflStateRecord
    | tuple[PlayerRecord, ...]
    | RosterEndpointRecords
    | tuple[TradedPickRecord, ...]
    | MatchupEndpointRecords
    | TransactionEndpointRecords
    | tuple[BracketMatchupRecord, ...]
)


def validate_completeness(
    request: EndpointRequest,
    payload: JsonValue,
    *,
    sleeper_league_id: str,
) -> CompletenessFinding:
    """Validate one parsed response using its owning endpoint contract."""

    match request.endpoint_kind:
        case EndpointKind.LEAGUE:
            return validate_league_completeness(
                payload,
                expected_sleeper_league_id=sleeper_league_id,
            )
        case EndpointKind.LEAGUE_USERS:
            return validate_league_users_completeness(payload)
        case EndpointKind.LEAGUE_ROSTERS:
            return validate_rosters_completeness(payload)
        case EndpointKind.NFL_STATE:
            return validate_nfl_state_completeness(payload)
        case EndpointKind.PLAYER_CATALOG:
            return validate_player_catalog_completeness(payload)
        case EndpointKind.MATCHUPS:
            return validate_matchups_completeness(payload)
        case EndpointKind.TRANSACTIONS:
            return validate_transactions_completeness(payload)
        case EndpointKind.TRADED_PICKS:
            return validate_traded_picks_completeness(payload)
        case EndpointKind.WINNERS_BRACKET | EndpointKind.LOSERS_BRACKET:
            return validate_bracket_completeness(payload)
        case unexpected:
            assert_never(unexpected)


def normalize_endpoint(
    request: EndpointRequest,
    payload: JsonValue,
    *,
    sleeper_league_id: str,
) -> EndpointRecords:
    """Normalize one complete response and enforce request metadata invariants."""

    match request.endpoint_kind:
        case EndpointKind.LEAGUE:
            return normalize_league(
                payload,
                expected_sleeper_league_id=sleeper_league_id,
            )
        case EndpointKind.LEAGUE_USERS:
            return normalize_league_users(payload)
        case EndpointKind.LEAGUE_ROSTERS:
            return normalize_rosters(payload)
        case EndpointKind.NFL_STATE:
            return normalize_nfl_state(payload)
        case EndpointKind.PLAYER_CATALOG:
            return normalize_player_catalog(payload)
        case EndpointKind.MATCHUPS:
            if request.week is None:
                raise ValueError("a matchup request must carry its week")
            return normalize_matchups(payload, week=request.week)
        case EndpointKind.TRANSACTIONS:
            if request.week is None:
                raise ValueError("a transaction request must carry its week")
            return normalize_transactions(payload, week=request.week)
        case EndpointKind.TRADED_PICKS:
            return normalize_traded_picks(payload)
        case EndpointKind.WINNERS_BRACKET:
            if request.bracket_kind != "winners":
                raise ValueError("a winners bracket request must carry winners metadata")
            return normalize_bracket(payload, bracket_kind="winners")
        case EndpointKind.LOSERS_BRACKET:
            if request.bracket_kind != "losers":
                raise ValueError("a losers bracket request must carry losers metadata")
            return normalize_bracket(payload, bracket_kind="losers")
        case unexpected:
            assert_never(unexpected)
