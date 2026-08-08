"""players table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Index, Integer, Table, Text

from ._base import RowMixin, metadata

players = Table(
    "players",
    metadata,
    Column("player_id", Text, primary_key=True),
    Column("full_name", Text),
    Column("position", Text),
    Column("nfl_team", Text),
    Column("status", Text),
    Column("injury_status", Text),
    Column("age", Integer),
    Column("years_exp", Integer),
    Column("metadata_json", Text),
    Column("updated_at", Text),
    Index("idx_players_full_name", "full_name"),
)


@dataclass
class Player(RowMixin):
    table_name: ClassVar[str] = "players"

    player_id: str
    full_name: Optional[str] = None
    position: Optional[str] = None
    nfl_team: Optional[str] = None
    status: Optional[str] = None
    injury_status: Optional[str] = None
    age: Optional[int] = None
    years_exp: Optional[int] = None
    metadata_json: Optional[str] = None
    updated_at: Optional[str] = None
