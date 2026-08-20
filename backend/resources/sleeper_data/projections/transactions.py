"""Transaction-scoped writer for transaction current state."""

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.sleeper import (
    ApiRequest,
    DraftPick,
    Transaction,
    TransactionMove,
)
from backend.resources.sleeper_data.common.codec import jsonb_expression
from backend.resources.sleeper_data.projections.common import (
    optional_identity,
    request_week,
    require_players,
    season_roster_identities,
)
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.sleeper.endpoints.contracts import (
    TransactionsEndpointRecords,
)


def write_transactions(
    session: Session,
    competition_id: UUID,
    request: ApiRequest,
    records: TransactionsEndpointRecords,
) -> None:
    """Replace one exact season/week of transactions and moves."""

    season, identities = season_roster_identities(session, competition_id, request)
    week = request_week(request)
    if any(row.week != week for row in records.transactions):
        raise DatalayerScopeConflict(
            "transaction records do not match the request week"
        )
    transaction_ids = session.scalars(
        sa.select(Transaction.id).where(
            Transaction.competition_season_id == season.id,
            Transaction.week == week,
        )
    ).all()
    if transaction_ids:
        session.execute(
            sa.delete(TransactionMove).where(
                TransactionMove.transaction_id.in_(transaction_ids)
            )
        )
        session.execute(
            sa.delete(Transaction).where(Transaction.id.in_(transaction_ids))
        )
    ids = {row.sleeper_transaction_id: uuid4() for row in records.transactions}
    if any(row.sleeper_transaction_id not in ids for row in records.moves):
        raise DatalayerScopeConflict(
            "transaction move references an unknown transaction"
        )
    require_players(
        session,
        [
            row.sleeper_player_id
            for row in records.moves
            if row.sleeper_player_id is not None
        ],
    )
    for record in records.transactions:
        session.execute(
            sa.insert(Transaction.__table__).values(
                id=ids[record.sleeper_transaction_id],
                competition_season_id=season.id,
                sleeper_transaction_id=record.sleeper_transaction_id,
                week=week,
                transaction_type=record.transaction_type,
                status=record.status,
                provider_created_at_ms=record.provider_created_at_ms,
                settings=jsonb_expression(record.settings),
                metadata=jsonb_expression(record.metadata),
                source_api_request_id=request.id,
            )
        )
    for record in records.moves:
        from_roster = optional_identity(identities, record.from_sleeper_roster_id)
        to_roster = optional_identity(identities, record.to_sleeper_roster_id)
        draft_pick: DraftPick | None = None
        if record.move_kind == "pick":
            original = optional_identity(identities, record.original_sleeper_roster_id)
            if original is None:
                raise DatalayerScopeConflict("pick move has no original roster")
            draft_pick = session.scalar(
                sa.select(DraftPick).where(
                    DraftPick.competition_id == competition_id,
                    DraftPick.draft_season_year == record.draft_season_year,
                    DraftPick.round == record.draft_round,
                    DraftPick.original_franchise_id == original.franchise_id,
                )
            )
            if draft_pick is None:
                raise DatalayerScopeConflict(
                    "transaction pick is outside seeded coordinates"
                )
        from_roster_id = None if from_roster is None else from_roster.id
        session.add(
            TransactionMove(
                transaction_id=ids[record.sleeper_transaction_id],
                competition_season_id=season.id,
                competition_id=competition_id,
                move_index=record.move_index,
                move_kind=record.move_kind,
                from_season_roster_id=from_roster_id,
                to_season_roster_id=None if to_roster is None else to_roster.id,
                sleeper_player_id=record.sleeper_player_id,
                draft_pick_id=None if draft_pick is None else draft_pick.id,
                budget_amount=record.budget_amount,
            )
        )
