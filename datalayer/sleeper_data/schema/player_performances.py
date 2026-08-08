"""player_performances table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Float, Index, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

player_performances = Table(
    "player_performances",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("season", Text, nullable=False),
    Column("week", Integer, nullable=False),
    Column("player_id", Text, nullable=False),
    Column("roster_id", Integer, nullable=False),
    Column("matchup_id", Integer, nullable=False),
    Column("points", Float, nullable=False),
    Column("role", Text),
    PrimaryKeyConstraint("league_id", "season", "week", "player_id", "roster_id"),
    Index("idx_player_perf_league_week", "league_id", "week"),
    Index("idx_player_perf_player_week", "player_id", "season", "week"),
    Index("idx_player_perf_roster_week", "league_id", "roster_id", "week"),
)


@dataclass
class PlayerPerformance(RowMixin):
    table_name: ClassVar[str] = "player_performances"

    league_id: str
    season: str
    week: int
    player_id: str
    roster_id: int
    matchup_id: int
    points: float
    role: Optional[str] = None
