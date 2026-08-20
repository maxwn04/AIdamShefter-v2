"""Competition-scoped current transaction reads."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa

from backend.database.models.core import CompetitionSeason
from backend.database.models.sleeper import DraftPick as StoredDraftPick
from backend.database.models.sleeper import Transaction as StoredTransaction
from backend.database.models.sleeper import TransactionMove as StoredTransactionMove
from backend.database.sessions import SessionFactory, read_only_session
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.sleeper_data.common.codec import parse_jsonb_text
from backend.resources.sleeper_data.transactions.objects import (
    Transaction,
    TransactionMove,
    TransactionQuery,
)
from backend.services.datalayer.errors import DatalayerResourceNotFound


class TransactionManager:
    """Read latest transaction observations within one competition."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext[CompetitionScope],
    ) -> None:
        self._session_factory = session_factory
        self._competition_id = context.scope.competition_id

    def list_transactions(self, query: TransactionQuery) -> tuple[Transaction, ...]:
        with read_only_session(self._session_factory) as session:
            season_exists = session.scalar(
                sa.select(sa.literal(True)).where(
                    sa.exists().where(
                        CompetitionSeason.id == query.competition_season_id,
                        CompetitionSeason.competition_id == self._competition_id,
                    )
                )
            )
            if not season_exists:
                raise DatalayerResourceNotFound(
                    "competition_season", str(query.competition_season_id)
                )
            statement = sa.select(StoredTransaction).where(
                StoredTransaction.competition_season_id == query.competition_season_id
            )
            if query.week is not None:
                statement = statement.where(StoredTransaction.week == query.week)
            if query.transaction_type is not None:
                statement = statement.where(
                    StoredTransaction.transaction_type == query.transaction_type
                )
            if query.status is not None:
                statement = statement.where(StoredTransaction.status == query.status)
            stored_transactions = session.scalars(
                statement.order_by(
                    StoredTransaction.week.desc(),
                    StoredTransaction.sleeper_transaction_id,
                )
            ).all()
            if not stored_transactions:
                return ()
            transaction_ids = [row.id for row in stored_transactions]
            move_rows = session.execute(
                sa.select(StoredTransactionMove, StoredDraftPick)
                .outerjoin(
                    StoredDraftPick,
                    StoredDraftPick.id == StoredTransactionMove.draft_pick_id,
                )
                .where(StoredTransactionMove.transaction_id.in_(transaction_ids))
                .order_by(
                    StoredTransactionMove.transaction_id,
                    StoredTransactionMove.move_index,
                )
            ).all()
            by_transaction: dict[UUID, list[TransactionMove]] = defaultdict(list)
            for move, pick in move_rows:
                by_transaction[move.transaction_id].append(
                    TransactionMove(
                        move_index=move.move_index,
                        move_kind=cast(Any, move.move_kind),
                        from_season_roster_id=move.from_season_roster_id,
                        to_season_roster_id=move.to_season_roster_id,
                        sleeper_player_id=move.sleeper_player_id,
                        draft_season_year=(
                            None if pick is None else pick.draft_season_year
                        ),
                        draft_round=None if pick is None else pick.round,
                        original_franchise_id=(
                            None if pick is None else pick.original_franchise_id
                        ),
                        sleeper_pick_id=None if pick is None else pick.sleeper_pick_id,
                        budget_amount=move.budget_amount,
                    )
                )
            result: list[Transaction] = []
            for stored in stored_transactions:
                settings, metadata = session.execute(
                    sa.select(
                        sa.cast(StoredTransaction.settings_json, sa.Text).label(
                            "settings_text"
                        ),
                        sa.cast(StoredTransaction.metadata_json, sa.Text).label(
                            "metadata_text"
                        ),
                    ).where(StoredTransaction.id == stored.id)
                ).one()
                result.append(
                    Transaction(
                        id=stored.id,
                        sleeper_transaction_id=stored.sleeper_transaction_id,
                        competition_season_id=stored.competition_season_id,
                        week=stored.week,
                        transaction_type=stored.transaction_type,
                        status=stored.status,
                        provider_created_at_ms=stored.provider_created_at_ms,
                        settings=cast(dict[str, Any], parse_jsonb_text(settings)),
                        metadata=cast(dict[str, Any], parse_jsonb_text(metadata)),
                        moves=tuple(by_transaction[stored.id]),
                        source_api_request_id=stored.source_api_request_id,
                    )
                )
            return tuple(result)
