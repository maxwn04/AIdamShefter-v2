"""roster_players table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy import Column, Index, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

roster_players = Table(
    "roster_players",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("roster_id", Integer, nullable=False),
    Column("player_id", Text, nullable=False),
    Column("role", Text, nullable=False),
    PrimaryKeyConstraint("league_id", "roster_id", "player_id"),
    Index("idx_roster_players_league_roster", "league_id", "roster_id"),
    Index("idx_roster_players_player", "player_id"),
)


@dataclass
class RosterPlayer(RowMixin):
    table_name: ClassVar[str] = "roster_players"

    league_id: str
    roster_id: int
    player_id: str
    role: str
