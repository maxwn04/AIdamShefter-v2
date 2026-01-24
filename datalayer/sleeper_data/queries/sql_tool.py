"""Guarded SQL execution for the data layer."""

from __future__ import annotations

import re
from typing import Any, Mapping


_DISALLOWED = re.compile(
    r"\b(pragma|attach|detach|insert|update|delete|drop|alter|create|replace)\b",
    re.IGNORECASE,
)


def _ensure_select_only(query: str) -> None:
    trimmed = query.strip().lstrip("(")
    if not trimmed.lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")
    if _DISALLOWED.search(trimmed):
        raise ValueError("Disallowed SQL keyword detected.")


def _ensure_limit(query: str, limit: int) -> str:
    if re.search(r"\blimit\b", query, re.IGNORECASE):
        return query
    return f"{query.rstrip(';')} LIMIT {limit};"


def run_sql(
    conn,
    query: str,
    params: Mapping[str, Any] | None = None,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    _ensure_select_only(query)
    sql = _ensure_limit(query, limit)
    cur = conn.execute(sql, params or {})
    columns = [col[0] for col in cur.description]
    rows = cur.fetchall()
    return {"columns": columns, "rows": rows, "row_count": len(rows)}
