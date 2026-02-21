"""SQLite store helpers for in-memory data layer."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping

from sqlalchemy import text

from ..schema.tables import metadata


def create_tables(conn) -> None:
    conn.execute(text("PRAGMA journal_mode = MEMORY"))
    conn.execute(text("PRAGMA temp_store = MEMORY"))
    metadata.create_all(conn.engine)


def _normalize_row(row: Any) -> Mapping[str, Any]:
    if is_dataclass(row):
        return asdict(row)
    if hasattr(row, "to_row"):
        return row.to_row()
    if isinstance(row, Mapping):
        return row
    raise TypeError("Row must be dataclass, Mapping, or expose to_row().")


def bulk_insert(conn, table: str, rows: Iterable[Any]) -> int:
    normalized = [dict(_normalize_row(row)) for row in rows]

    if not normalized:
        return 0

    columns = list(normalized[0].keys())
    placeholders = ", ".join(f":{col}" for col in columns)
    col_list = ", ".join(columns)
    sql = text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})")
    conn.execute(sql, normalized)
    return len(normalized)
