"""draft_picks table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Index, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

draft_picks = Table(
    "draft_picks",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("season", Text, nullable=False),
    Column("round", Integer, nullable=False),
    Column("original_roster_id", Integer, nullable=False),
    Column("current_roster_id", Integer, nullable=False),
    Column("pick_id", Text),
    Column("source", Text),
    PrimaryKeyConstraint("league_id", "season", "round", "original_roster_id"),
    Index("idx_draft_picks_current", "league_id", "current_roster_id"),
    Index("idx_draft_picks_original", "league_id", "original_roster_id"),
    Index("idx_draft_picks_season_round", "league_id", "season", "round"),
)


@dataclass
class DraftPick(RowMixin):
    table_name: ClassVar[str] = "draft_picks"

    league_id: str
    season: str
    round: int
    original_roster_id: int
    current_roster_id: int
    pick_id: Optional[str] = None
    source: Optional[str] = None
