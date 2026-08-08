"""season_context table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Integer, Table, Text

from ._base import RowMixin, metadata

season_context = Table(
    "season_context",
    metadata,
    Column("league_id", Text, primary_key=True),
    Column("computed_week", Integer, nullable=False),
    Column("override_week", Integer),
    Column("effective_week", Integer, nullable=False),
    Column("generated_at", Text, nullable=False),
)


@dataclass
class SeasonContext(RowMixin):
    table_name: ClassVar[str] = "season_context"

    league_id: str
    computed_week: int
    override_week: Optional[int]
    effective_week: int
    generated_at: str
