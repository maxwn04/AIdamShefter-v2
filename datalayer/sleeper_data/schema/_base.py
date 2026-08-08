"""Shared schema primitives for the Sleeper data layer."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, ClassVar

from sqlalchemy import MetaData

metadata = MetaData()


class RowMixin:
    """Insert DTO helper: dataclasses expose table_name + to_row()."""

    table_name: ClassVar[str]

    def to_row(self) -> dict[str, Any]:
        return asdict(self)
