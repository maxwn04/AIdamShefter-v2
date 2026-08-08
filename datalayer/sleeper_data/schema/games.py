"""games table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Float, Index, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

games = Table(
    "games",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("season", Text, nullable=False),
    Column("week", Integer, nullable=False),
    Column("matchup_id", Integer, nullable=False),
    Column("roster_id_a", Integer, nullable=False),
    Column("roster_id_b", Integer, nullable=False),
    Column("points_a", Float, nullable=False),
    Column("points_b", Float, nullable=False),
    Column("winner_roster_id", Integer),
    Column("is_playoffs", Integer, nullable=False),
    PrimaryKeyConstraint("league_id", "week", "matchup_id"),
    Index("idx_games_league_season_week", "league_id", "season", "week"),
)


@dataclass
class Game(RowMixin):
    table_name: ClassVar[str] = "games"

    league_id: str
    season: str
    week: int
    matchup_id: int
    roster_id_a: int
    roster_id_b: int
    points_a: float
    points_b: float
    winner_roster_id: Optional[int]
    is_playoffs: bool
