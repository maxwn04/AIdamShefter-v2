"""team_profiles table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Index, Integer, PrimaryKeyConstraint, Table, Text

from ._base import RowMixin, metadata

team_profiles = Table(
    "team_profiles",
    metadata,
    Column("league_id", Text, nullable=False),
    Column("roster_id", Integer, nullable=False),
    Column("team_name", Text),
    Column("manager_name", Text),
    Column("avatar_url", Text),
    PrimaryKeyConstraint("league_id", "roster_id"),
    Index("idx_team_profiles_team_name", "team_name"),
    Index("idx_team_profiles_manager_name", "manager_name"),
)


@dataclass
class TeamProfile(RowMixin):
    table_name: ClassVar[str] = "team_profiles"

    league_id: str
    roster_id: int
    team_name: Optional[str] = None
    manager_name: Optional[str] = None
    avatar_url: Optional[str] = None
