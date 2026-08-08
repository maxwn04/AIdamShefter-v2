"""rosters table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Index, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

rosters = Table(
    "rosters",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("roster_id", Integer, nullable=False),
    Column("owner_user_id", Text),
    Column("settings_json", Text),
    Column("metadata_json", Text),
    Column("record_string", Text),
    PrimaryKeyConstraint("league_id", "roster_id"),
    Index("idx_rosters_league_roster", "league_id", "roster_id"),
)


@dataclass
class Roster(RowMixin):
    table_name: ClassVar[str] = "rosters"

    league_id: str
    roster_id: int
    owner_user_id: Optional[str] = None
    settings_json: Optional[str] = None
    metadata_json: Optional[str] = None
    record_string: Optional[str] = None
