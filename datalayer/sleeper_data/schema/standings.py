"""standings table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Float, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

standings = Table(
    "standings",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("season", Text, nullable=False),
    Column("week", Integer, nullable=False),
    Column("roster_id", Integer, nullable=False),
    Column("wins", Integer, nullable=False),
    Column("losses", Integer, nullable=False),
    Column("ties", Integer, nullable=False),
    Column("points_for", Float, nullable=False),
    Column("points_against", Float, nullable=False),
    Column("rank", Integer),
    Column("streak_type", Text),
    Column("streak_len", Integer),
    PrimaryKeyConstraint("league_id", "week", "roster_id"),
)


@dataclass
class StandingsWeek(RowMixin):
    table_name: ClassVar[str] = "standings"

    league_id: str
    season: str
    week: int
    roster_id: int
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    rank: Optional[int] = None
    streak_type: Optional[str] = None
    streak_len: Optional[int] = None
