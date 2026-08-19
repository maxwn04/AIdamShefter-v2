"""Pure Sleeper endpoint-family request and normalization behavior."""

from backend.services.datalayer.sleeper.endpoints.contracts import (
    CompletenessFinding,
    EndpointRecords,
    LeagueEndpointRecords,
    LeagueRecord,
    LeagueUserRecord,
    LeagueUsersEndpointRecords,
    NflStateEndpointRecords,
    NflStateRecord,
    PlayerCatalogEndpointRecords,
    PlayerRecord,
    UserRecord,
)
from backend.services.datalayer.sleeper.endpoints.league import (
    build_league_request,
    build_league_users_request,
    build_nfl_state_request,
    normalize_league,
    normalize_league_users,
    normalize_nfl_state,
    validate_league_completeness,
    validate_league_users_completeness,
    validate_nfl_state_completeness,
)
from backend.services.datalayer.sleeper.endpoints.players import (
    build_player_catalog_request,
    normalize_player_catalog,
    validate_player_catalog_completeness,
)

__all__ = [
    "CompletenessFinding",
    "EndpointRecords",
    "LeagueEndpointRecords",
    "LeagueRecord",
    "LeagueUserRecord",
    "LeagueUsersEndpointRecords",
    "NflStateEndpointRecords",
    "NflStateRecord",
    "PlayerCatalogEndpointRecords",
    "PlayerRecord",
    "UserRecord",
    "build_league_request",
    "build_league_users_request",
    "build_nfl_state_request",
    "build_player_catalog_request",
    "normalize_league",
    "normalize_league_users",
    "normalize_nfl_state",
    "normalize_player_catalog",
    "validate_league_completeness",
    "validate_league_users_completeness",
    "validate_nfl_state_completeness",
    "validate_player_catalog_completeness",
]
