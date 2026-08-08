"""users table + row model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from sqlalchemy import Column, Table, Text

from ._base import RowMixin, metadata

users = Table(
    "users",
    metadata,
    Column("user_id", Text, primary_key=True),
    Column("display_name", Text, nullable=False),
    Column("avatar", Text),
    Column("metadata_json", Text),
)


@dataclass
class User(RowMixin):
    table_name: ClassVar[str] = "users"

    user_id: str
    display_name: str
    avatar: Optional[str] = None
    metadata_json: Optional[str] = None
