"""SQLite store helpers for the in-memory data layer.

Contract: accepts SQLAlchemy Connection + row DTOs (RowMixin) or mappings.
Does not fetch from the API or run curated queries.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping, Sequence, Union

from sqlalchemy import Table, text
from sqlalchemy.engine import Connection

from ..schema import RowMixin, metadata

TableRef = Union[Table, str]


def create_tables(conn: Connection) -> None:
    conn.execute(text("PRAGMA journal_mode = MEMORY"))
    conn.execute(text("PRAGMA temp_store = MEMORY"))
    metadata.create_all(conn.engine)


def _normalize_row(row: Any) -> Mapping[str, Any]:
    if isinstance(row, RowMixin) or is_dataclass(row):
        if hasattr(row, "to_row"):
            return row.to_row()
        return asdict(row)
    if isinstance(row, Mapping):
        return row
    raise TypeError("Row must be RowMixin, dataclass, Mapping, or expose to_row().")


def _table_name(table: TableRef) -> str:
    if isinstance(table, Table):
        return table.name
    if isinstance(table, str):
        return table
    raise TypeError("table must be a SQLAlchemy Table or table name string.")


def bulk_insert(conn: Connection, table: TableRef, rows: Iterable[Any]) -> int:
    """Insert rows into ``table`` (Table object or name). Returns row count."""
    normalized: Sequence[dict[str, Any]] = [dict(_normalize_row(row)) for row in rows]

    if not normalized:
        return 0

    name = _table_name(table)
    columns = list(normalized[0].keys())
    placeholders = ", ".join(f":{col}" for col in columns)
    col_list = ", ".join(columns)
    sql = text(f"INSERT INTO {name} ({col_list}) VALUES ({placeholders})")
    conn.execute(sql, normalized)
    return len(normalized)
