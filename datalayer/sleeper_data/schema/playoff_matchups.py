"""playoff_matchups table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Index, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

playoff_matchups = Table(
    "playoff_matchups",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("season", Text, nullable=False),
    Column("bracket_type", Text, nullable=False),
    Column("round", Integer, nullable=False),
    Column("matchup_id", Integer, nullable=False),
    Column("t1_roster_id", Integer),
    Column("t2_roster_id", Integer),
    Column("t1_from_matchup_id", Integer),
    Column("t1_from_outcome", Text),
    Column("t2_from_matchup_id", Integer),
    Column("t2_from_outcome", Text),
    Column("winner_roster_id", Integer),
    Column("loser_roster_id", Integer),
    Column("placement", Integer),
    PrimaryKeyConstraint("league_id", "season", "bracket_type", "matchup_id"),
    Index(
        "idx_playoff_matchups_bracket_round",
        "league_id",
        "season",
        "bracket_type",
        "round",
    ),
    Index("idx_playoff_matchups_winner", "league_id", "winner_roster_id"),
)


@dataclass
class PlayoffMatchup(RowMixin):
    table_name: ClassVar[str] = "playoff_matchups"

    league_id: str
    season: str
    bracket_type: str
    round: int
    matchup_id: int
    t1_roster_id: Optional[int] = None
    t2_roster_id: Optional[int] = None
    t1_from_matchup_id: Optional[int] = None
    t1_from_outcome: Optional[str] = None
    t2_from_matchup_id: Optional[int] = None
    t2_from_outcome: Optional[str] = None
    winner_roster_id: Optional[int] = None
    loser_roster_id: Optional[int] = None
    placement: Optional[int] = None
