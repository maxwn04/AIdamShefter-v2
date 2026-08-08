"""leagues table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Integer, Table, Text

from ._base import RowMixin, metadata

leagues = Table(
    "leagues",
    metadata,
    Column("league_id", Text, primary_key=True),
    Column("season", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("sport", Text, nullable=False),
    Column("scoring_settings_json", Text),
    Column("roster_positions_json", Text),
    Column("playoff_week_start", Integer),
    Column("playoff_teams", Integer),
    Column("league_average_match", Integer),
)


@dataclass
class League(RowMixin):
    table_name: ClassVar[str] = "leagues"

    league_id: str
    season: str
    name: str
    sport: str
    scoring_settings_json: Optional[str] = None
    roster_positions_json: Optional[str] = None
    playoff_week_start: Optional[int] = None
    playoff_teams: Optional[int] = None
    league_average_match: Optional[int] = None
