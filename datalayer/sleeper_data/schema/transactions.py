"""transactions table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Index, Integer, Table, Text

from ._base import RowMixin, metadata

transactions = Table(
    "transactions",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("season", Text, nullable=False),
    Column("week", Integer, nullable=False),
    Column("transaction_id", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("status", Text),
    Column("created_ts", Integer),
    Column("settings_json", Text),
    Column("metadata_json", Text),
    Index("idx_transactions_league_season_week", "league_id", "season", "week"),
)


@dataclass
class Transaction(RowMixin):
    table_name: ClassVar[str] = "transactions"

    league_id: str
    season: str
    week: int
    transaction_id: str
    type: str
    status: Optional[str] = None
    created_ts: Optional[int] = None
    settings_json: Optional[str] = None
    metadata_json: Optional[str] = None
