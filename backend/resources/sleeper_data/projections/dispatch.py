"""Explicit endpoint-kind dispatch for transaction-scoped projections."""

from typing import assert_never
from uuid import UUID

from sqlalchemy.orm import Session

from backend.database.models.sleeper import ApiRequest
from backend.resources.sleeper_data.projections.draft_picks import (
    write_traded_picks,
)
from backend.resources.sleeper_data.projections.leagues import (
    write_league,
    write_league_users,
)
from backend.resources.sleeper_data.projections.matchups import write_matchups
from backend.resources.sleeper_data.projections.players import write_players
from backend.resources.sleeper_data.projections.playoff_matchups import (
    write_playoff_matchups,
)
from backend.resources.sleeper_data.projections.rosters import write_rosters
from backend.resources.sleeper_data.projections.transactions import (
    write_transactions,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    EndpointRecords,
    LeagueEndpointRecords,
    LeagueRostersEndpointRecords,
    LeagueUsersEndpointRecords,
    LosersBracketEndpointRecords,
    MatchupsEndpointRecords,
    NflStateEndpointRecords,
    PlayerCatalogEndpointRecords,
    TradedPicksEndpointRecords,
    TransactionsEndpointRecords,
    WinnersBracketEndpointRecords,
)


def write_endpoint_records(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: EndpointRecords,
) -> None:
    """Project endpoint records using only the caller-owned transaction."""

    if isinstance(records, LeagueEndpointRecords):
        write_league(session, competition_id, request, records)
    elif isinstance(records, LeagueUsersEndpointRecords):
        write_league_users(session, competition_id, request, records)
    elif isinstance(records, NflStateEndpointRecords):
        return
    elif isinstance(records, PlayerCatalogEndpointRecords):
        write_players(session, competition_id, request, records)
    elif isinstance(records, LeagueRostersEndpointRecords):
        write_rosters(session, competition_id, request, records)
    elif isinstance(records, TradedPicksEndpointRecords):
        write_traded_picks(session, competition_id, request, records)
    elif isinstance(records, MatchupsEndpointRecords):
        write_matchups(session, competition_id, request, records)
    elif isinstance(records, TransactionsEndpointRecords):
        write_transactions(session, competition_id, request, records)
    elif isinstance(
        records, (WinnersBracketEndpointRecords, LosersBracketEndpointRecords)
    ):
        write_playoff_matchups(session, competition_id, request, records)
    else:
        assert_never(records)
