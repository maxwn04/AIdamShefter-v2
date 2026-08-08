"""transaction_moves table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Index, Integer, Table, Text

from ._base import RowMixin, metadata

transaction_moves = Table(
    "transaction_moves",
    metadata,
    Column("transaction_id", Text, nullable=False),
    Column("roster_id", Integer),
    Column("player_id", Text),
    Column("asset_type", Text, nullable=False),
    Column("direction", Text, nullable=False),
    Column("bid_amount", Integer),
    Column("from_roster_id", Integer),
    Column("to_roster_id", Integer),
    Column("pick_season", Text),
    Column("pick_round", Integer),
    Column("pick_original_roster_id", Integer),
    Column("pick_id", Text),
    Index("idx_transaction_moves_tx", "transaction_id"),
    Index("idx_transaction_moves_roster", "roster_id"),
)


@dataclass
class TransactionMove(RowMixin):
    table_name: ClassVar[str] = "transaction_moves"

    transaction_id: str
    roster_id: Optional[int]
    player_id: Optional[str]
    asset_type: str
    direction: str
    bid_amount: Optional[int] = None
    from_roster_id: Optional[int] = None
    to_roster_id: Optional[int] = None
    pick_season: Optional[str] = None
    pick_round: Optional[int] = None
    pick_original_roster_id: Optional[int] = None
    pick_id: Optional[str] = None
