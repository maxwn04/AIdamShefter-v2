"""matchups table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy import Column, Float, Index, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

matchups = Table(
    "matchups",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("season", Text, nullable=False),
    Column("week", Integer, nullable=False),
    Column("matchup_id", Integer, nullable=False),
    Column("roster_id", Integer, nullable=False),
    Column("points", Float, nullable=False),
    PrimaryKeyConstraint("league_id", "week", "matchup_id", "roster_id"),
    Index("idx_matchups_league_season_week", "league_id", "season", "week"),
    Index("idx_matchups_week_matchup", "week", "matchup_id"),
)


@dataclass
class MatchupRow(RowMixin):
    table_name: ClassVar[str] = "matchups"

    league_id: str
    season: str
    week: int
    matchup_id: int
    roster_id: int
    points: float
