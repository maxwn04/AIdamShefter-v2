"""Hardened read-only SQL escape hatch for frozen snapshot artifacts."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import math
import sqlite3
import time
from typing import Any


MAX_SQL_ROWS = 200
SQL_DEADLINE_SECONDS = 2.0
_PROGRESS_INSTRUCTIONS = 1_000
_FILESYSTEM_FUNCTIONS = {"load_extension", "readfile", "writefile"}


def run_guarded_sql(
    connection: sqlite3.Connection,
    query: str,
    params: Mapping[str, Any] | None = None,
    *,
    limit: int = MAX_SQL_ROWS,
    allowed_tables: frozenset[str],
) -> dict[str, Any]:
    """Execute one bounded read statement against an immutable artifact."""

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("SQL row limit must be an integer from 1 through 200")
    statement = _validate_statement(query)
    deadline = time.monotonic() + SQL_DEADLINE_SECONDS
    timed_out = False

    def progress() -> int:
        nonlocal timed_out
        timed_out = time.monotonic() >= deadline
        return 1 if timed_out else 0

    connection.set_authorizer(_authorizer(allowed_tables))
    connection.set_progress_handler(progress, _PROGRESS_INSTRUCTIONS)
    cursor: sqlite3.Cursor | None = None
    try:
        cursor = connection.execute(statement, params or {})
        columns = [item[0] for item in cursor.description or ()]
        rows = [
            tuple(_json_safe_cell(value) for value in row)
            for row in cursor.fetchmany(limit)
        ]
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except sqlite3.Error as error:
        if timed_out:
            raise TimeoutError("SQL execution deadline exceeded") from error
        raise ValueError(f"SQL query could not be executed: {error}") from error
    finally:
        if cursor is not None:
            cursor.close()
        connection.set_progress_handler(None, 0)
        connection.set_authorizer(None)


def _authorizer(allowed_tables: frozenset[str]):
    allowed_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION}
    recursive = getattr(sqlite3, "SQLITE_RECURSIVE", None)
    if recursive is not None:
        allowed_actions.add(recursive)

    def authorize(
        action: int,
        argument_1: str | None,
        argument_2: str | None,
        database: str | None,
        source: str | None,
    ) -> int:
        del source
        if action == sqlite3.SQLITE_READ:
            return (
                sqlite3.SQLITE_OK
                if database == "main" and argument_1 in allowed_tables
                else sqlite3.SQLITE_DENY
            )
        if action == sqlite3.SQLITE_FUNCTION:
            function_name = (argument_2 or argument_1 or "").lower()
            if function_name in _FILESYSTEM_FUNCTIONS:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed_actions else sqlite3.SQLITE_DENY

    return authorize


def _validate_statement(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("SQL query must be a non-empty string")
    masked = _mask_comments_and_quotes(query)
    segments = [segment for segment in masked.split(";") if segment.strip()]
    if len(segments) != 1:
        raise ValueError("Exactly one SQL statement is allowed")
    semicolon = masked.find(";")
    if semicolon >= 0 and any(part.strip() for part in masked.split(";")[1:]):
        raise ValueError("Exactly one SQL statement is allowed")
    first = segments[0].lstrip().split(None, 1)[0].lower()
    if first not in {"select", "with"}:
        raise ValueError("Only SELECT or WITH ... SELECT queries are allowed")
    statement = query[:semicolon] if semicolon >= 0 else query
    return statement.strip()


def _mask_comments_and_quotes(query: str) -> str:
    masked = list(query)
    index = 0
    length = len(query)
    while index < length:
        char = query[index]
        next_char = query[index + 1] if index + 1 < length else ""
        if char == "-" and next_char == "-":
            start = index
            index += 2
            while index < length and query[index] not in "\r\n":
                index += 1
            _blank(masked, start, index)
            continue
        if char == "/" and next_char == "*":
            start = index
            end = query.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unterminated SQL block comment")
            index = end + 2
            _blank(masked, start, index)
            continue
        if char in {"'", '"', "`"}:
            start = index
            quote = char
            index += 1
            while index < length:
                if query[index] == quote:
                    if index + 1 < length and query[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise ValueError("Unterminated SQL quoted value")
            _blank(masked, start, index)
            continue
        if char == "[":
            start = index
            end = query.find("]", index + 1)
            if end < 0:
                raise ValueError("Unterminated SQL quoted identifier")
            index = end + 1
            _blank(masked, start, index)
            continue
        index += 1
    return "".join(masked)


def _blank(masked: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if masked[index] not in "\r\n":
            masked[index] = " "


def _json_safe_cell(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("SQL result contains a non-finite number")
        return value
    if isinstance(value, bytes):
        return "base64:" + base64.b64encode(value).decode("ascii")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("SQL result contains a non-finite number")
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise ValueError(f"SQL result contains unsupported {type(value).__name__} value")
