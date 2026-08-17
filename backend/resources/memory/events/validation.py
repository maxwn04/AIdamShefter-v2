"""Competition-scoped reference validation for complete event content."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.database.models.core import Franchise
from backend.database.models.sleeper import DraftPick, Player
from backend.resources.memory.common.errors import (
    CrossCompetitionEntityReferenceError,
    EntityReferenceNotFoundError,
)
from backend.resources.memory.common.receipt_validation import (
    validate_api_receipt,
    validate_tool_receipt,
)
from backend.resources.memory.events.objects import EventContent
from backend.resources.memory.events.payloads.matchup import MatchupEventPayload
from backend.resources.memory.events.payloads.trade import (
    DraftPickTradeAsset,
    PlayerTradeAsset,
    TradeEventPayload,
)


@dataclass(frozen=True, slots=True)
class ValidatedEventContent:
    competition_id: UUID
    content: EventContent
    primary_tool_call_generation_id: UUID | None


def validate_event_content(
    session: Session,
    competition_id: UUID,
    content: EventContent,
) -> ValidatedEventContent:
    """Validate all database-backed event references in the active transaction."""

    _validate_details(session, competition_id, content)
    receipt_generation_id = validate_tool_receipt(
        session, competition_id, content.primary_tool_call_id
    )
    validate_api_receipt(session, competition_id, content.primary_api_request_id)
    return ValidatedEventContent(
        competition_id=competition_id,
        content=content,
        primary_tool_call_generation_id=receipt_generation_id,
    )


def _validate_details(
    session: Session,
    competition_id: UUID,
    content: EventContent,
) -> None:
    details = content.details
    if isinstance(details, TradeEventPayload):
        _validate_scoped_entities(
            session,
            competition_id,
            "franchise",
            Franchise.id,
            Franchise.competition_id,
            [details.sender_franchise_id, details.receiver_franchise_id],
        )
        player_ids = [
            asset.player_id
            for asset in details.assets
            if isinstance(asset, PlayerTradeAsset)
        ]
        if player_ids:
            found_players = set(
                session.scalars(
                    sa.select(Player.sleeper_player_id).where(
                        Player.sleeper_player_id.in_(set(player_ids))
                    )
                )
            )
            for player_id in player_ids:
                if player_id not in found_players:
                    raise EntityReferenceNotFoundError("player", player_id)
        draft_pick_ids = [
            asset.draft_pick_id
            for asset in details.assets
            if isinstance(asset, DraftPickTradeAsset)
        ]
        _validate_scoped_entities(
            session,
            competition_id,
            "draft_pick",
            DraftPick.id,
            DraftPick.competition_id,
            draft_pick_ids,
        )
        return

    if isinstance(details, MatchupEventPayload):
        _validate_scoped_entities(
            session,
            competition_id,
            "franchise",
            Franchise.id,
            Franchise.competition_id,
            [details.winner_franchise_id, details.loser_franchise_id],
        )
        return

    raise TypeError(f"unsupported event payload: {type(details).__name__}")


def _validate_scoped_entities(
    session: Session,
    competition_id: UUID,
    entity_kind: str,
    id_column: InstrumentedAttribute[UUID],
    competition_column: InstrumentedAttribute[UUID],
    ids: list[UUID],
) -> None:
    if not ids:
        return
    rows = session.execute(
        sa.select(id_column, competition_column).where(id_column.in_(set(ids)))
    )
    found: dict[UUID, UUID] = {entity_id: scope for entity_id, scope in rows}
    for entity_id in ids:
        actual_scope = found.get(entity_id)
        if actual_scope is None:
            raise EntityReferenceNotFoundError(entity_kind, entity_id)
        if actual_scope != competition_id:
            raise CrossCompetitionEntityReferenceError(
                entity_kind, entity_id, competition_id
            )
