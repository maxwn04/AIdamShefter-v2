"""Transaction-scoped writer for playoff bracket nodes."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.sleeper import ApiRequest, PlayoffMatchup
from backend.resources.sleeper_data.projections.common import (
    optional_identity,
    season_roster_identities,
)
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.sleeper.endpoints.contracts import (
    LosersBracketEndpointRecords,
    WinnersBracketEndpointRecords,
)


def write_playoff_matchups(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: WinnersBracketEndpointRecords | LosersBracketEndpointRecords,
) -> None:
    """Replace one exact season/bracket-kind of playoff nodes."""

    season, identities = season_roster_identities(session, competition_id, request)
    bracket_kind = (
        "winners" if isinstance(records, WinnersBracketEndpointRecords) else "losers"
    )
    if request.bracket_kind != bracket_kind:
        raise DatalayerScopeConflict("bracket records do not match the request kind")
    session.execute(
        sa.delete(PlayoffMatchup).where(
            PlayoffMatchup.competition_season_id == season.id,
            PlayoffMatchup.bracket_kind == bracket_kind,
        )
    )
    for record in records.matchups:
        roster_fields = (
            record.t1_sleeper_roster_id,
            record.t2_sleeper_roster_id,
            record.winner_sleeper_roster_id,
            record.loser_sleeper_roster_id,
        )
        mapped = [optional_identity(identities, value) for value in roster_fields]
        session.add(
            PlayoffMatchup(
                competition_season_id=season.id,
                bracket_kind=bracket_kind,
                node_key=record.node_key,
                round=record.round,
                t1_season_roster_id=None if mapped[0] is None else mapped[0].id,
                t2_season_roster_id=None if mapped[1] is None else mapped[1].id,
                t1_from_node_key=record.t1_from_node_key,
                t1_from_outcome=record.t1_from_outcome,
                t2_from_node_key=record.t2_from_node_key,
                t2_from_outcome=record.t2_from_outcome,
                winner_season_roster_id=(None if mapped[2] is None else mapped[2].id),
                loser_season_roster_id=(None if mapped[3] is None else mapped[3].id),
                placement=record.placement,
                source_api_request_id=request.id,
            )
        )
