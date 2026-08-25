"""Transaction-scoped writers for rosters and draft-pick seed coordinates."""

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason, SeasonRoster
from backend.database.models.sleeper import (
    ApiRequest,
    DraftPick,
    League,
    Roster,
    RosterManager,
    RosterPlayer,
)
from backend.resources.sleeper_data.common.codec import jsonb_expression
from backend.resources.sleeper_data.projections.common import (
    require_players,
    require_users,
    season_roster_identities,
)
from backend.services.datalayer.errors import (
    DatalayerScopeConflict,
    RosterIdentityMappingRequired,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    LeagueRostersEndpointRecords,
)


def write_rosters(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: LeagueRostersEndpointRecords,
) -> None:
    """Replace roster current state and seed its draft-pick coordinates."""

    season, identities = season_roster_identities(session, competition_id, request)
    roster_ids = {row.sleeper_roster_id for row in records.rosters}
    if any(roster_id not in identities for roster_id in roster_ids):
        raise RosterIdentityMappingRequired(
            "roster response contains an unmapped Sleeper roster"
        )
    if any(row.sleeper_roster_id not in roster_ids for row in records.managers):
        raise DatalayerScopeConflict("roster manager references an unknown roster")
    if any(row.sleeper_roster_id not in roster_ids for row in records.players):
        raise DatalayerScopeConflict("roster player references an unknown roster")
    require_users(session, [row.sleeper_user_id for row in records.managers])
    require_players(session, [row.sleeper_player_id for row in records.players])

    session.execute(
        sa.delete(RosterPlayer).where(RosterPlayer.competition_season_id == season.id)
    )
    delete_managers = sa.delete(RosterManager).where(
        RosterManager.competition_season_id == season.id
    )
    session.execute(delete_managers)
    session.execute(sa.delete(Roster).where(Roster.competition_season_id == season.id))
    for record in records.rosters:
        identity = identities[record.sleeper_roster_id]
        session.execute(
            sa.insert(Roster.__table__).values(
                season_roster_id=identity.id,
                competition_season_id=season.id,
                source_api_request_id=request.id,
                settings=jsonb_expression(record.settings),
                metadata=jsonb_expression(record.metadata),
                record_string=record.record_string,
                wins=record.wins,
                losses=record.losses,
                ties=record.ties,
                points_for=record.points_for,
                points_against=record.points_against,
            )
        )
    for record in records.managers:
        session.add(
            RosterManager(
                season_roster_id=identities[record.sleeper_roster_id].id,
                competition_season_id=season.id,
                sleeper_user_id=record.sleeper_user_id,
                role=record.role,
                source_order=record.source_order,
                source_api_request_id=request.id,
            )
        )
    for record in records.players:
        session.add(
            RosterPlayer(
                season_roster_id=identities[record.sleeper_roster_id].id,
                competition_season_id=season.id,
                sleeper_player_id=record.sleeper_player_id,
                role=record.role,
                source_api_request_id=request.id,
            )
        )
    _seed_draft_picks(
        session,
        competition_id,
        request,
        season,
        records,
        identities,
    )


def _seed_draft_picks(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    season: CompetitionSeason,
    records: LeagueRostersEndpointRecords,
    identities: dict[str, SeasonRoster],
) -> None:
    league = session.get(League, season.id)
    if league is None:
        raise DatalayerScopeConflict("roster normalization requires league metadata")
    raw_rounds = league.provider_settings.get("draft_rounds")
    if isinstance(raw_rounds, bool) or not isinstance(raw_rounds, int):
        draft_rounds = 0
    else:
        draft_rounds = max(raw_rounds, 0)
    for offset in range(1, 4):
        draft_year = season.season_year + offset
        for roster in records.rosters:
            identity = identities[roster.sleeper_roster_id]
            for round_number in range(1, draft_rounds + 1):
                values = {
                    "id": uuid4(),
                    "competition_id": competition_id,
                    "draft_season_year": draft_year,
                    "round": round_number,
                    "original_franchise_id": identity.franchise_id,
                    "current_franchise_id": identity.franchise_id,
                    "sleeper_pick_id": None,
                    "source": "seeded",
                    "source_api_request_id": request.id,
                    "source_api_request_competition_season_id": season.id,
                }
                session.execute(
                    pg_insert(DraftPick.__table__)
                    .values(**values)
                    .on_conflict_do_update(
                        constraint="uq_draft_picks_natural",
                        set_={
                            key: value
                            for key, value in values.items()
                            if key
                            not in {
                                "id",
                                "competition_id",
                                "draft_season_year",
                                "round",
                                "original_franchise_id",
                            }
                        },
                    )
                )
