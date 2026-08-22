"""Transaction-scoped writer for the complete traded-pick ownership view."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.sleeper import ApiRequest, DraftPick
from backend.resources.sleeper_data.projections.common import (
    season_roster_identities,
)
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.sleeper.endpoints.contracts import (
    TradedPicksEndpointRecords,
)


def write_traded_picks(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: TradedPicksEndpointRecords,
) -> None:
    """Reset and reapply the complete ownership view in the caller transaction."""

    season, identities = season_roster_identities(session, competition_id, request)
    years = range(season.season_year + 1, season.season_year + 4)
    session.execute(
        sa.update(DraftPick)
        .where(
            DraftPick.competition_id == competition_id,
            DraftPick.draft_season_year.in_(years),
            DraftPick.source == "traded_pick",
        )
        .values(
            current_franchise_id=DraftPick.original_franchise_id,
            sleeper_pick_id=None,
            source="seeded",
            source_api_request_id=request.id,
            source_api_request_competition_season_id=season.id,
        )
    )
    for record in records.picks:
        original = identities.get(record.original_sleeper_roster_id)
        current = identities.get(record.current_owner_sleeper_roster_id)
        if original is None or current is None:
            raise DatalayerScopeConflict("traded pick references an unmapped roster")
        stored = session.scalar(
            sa.select(DraftPick).where(
                DraftPick.competition_id == competition_id,
                DraftPick.draft_season_year == record.draft_season_year,
                DraftPick.round == record.draft_round,
                DraftPick.original_franchise_id == original.franchise_id,
            )
        )
        if stored is None:
            raise DatalayerScopeConflict(
                "traded pick is outside the seeded pick coordinates"
            )
        stored.current_franchise_id = current.franchise_id
        stored.sleeper_pick_id = record.sleeper_pick_id
        stored.source = "traded_pick"
        stored.source_api_request_id = request.id
        stored.source_api_request_competition_season_id = season.id
