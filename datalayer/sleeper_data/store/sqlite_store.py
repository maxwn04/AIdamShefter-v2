"""SQLite store helpers for in-memory data layer."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Mapping

from ..schema.ddl import create_all_tables


def create_tables(conn) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = MEMORY;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    create_all_tables(conn)


def _normalize_row(row: Any) -> Mapping[str, Any]:
    if is_dataclass(row):
        return asdict(row)
    if hasattr(row, "to_row"):
        return row.to_row()
    if isinstance(row, Mapping):
        return row
    raise TypeError("Row must be dataclass, Mapping, or expose to_row().")


def bulk_insert(conn, table: str, rows: Iterable[Any]) -> int:
    normalized = []
    for row in rows:
        row_data = dict(_normalize_row(row))
        for key, value in row_data.items():
            if isinstance(value, bool):
                row_data[key] = int(value)
        normalized.append(row_data)

    if not normalized:
        return 0

    columns = list(normalized[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    col_list = ", ".join(columns)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders});"
    values = [tuple(row[col] for col in columns) for row in normalized]
    conn.executemany(sql, values)
    conn.commit()
    return len(values)
