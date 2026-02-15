"""Guarded SQL execution for the data layer."""

from __future__ import annotations

import re
from typing import Any, Mapping

from sqlalchemy import text


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
    """Execute a custom SELECT query against the league database.

    Provides an escape hatch for custom analysis when the curated query
    methods don't cover a specific need. Only SELECT queries are allowed;
    all write operations are blocked for safety.

    Args:
        conn: SQLite database connection.
        query: A SELECT SQL query. Must not contain INSERT, UPDATE, DELETE,
            DROP, ALTER, CREATE, or other write operations.
        params: Optional named parameters for the query (e.g., {"week": 5}).
        limit: Maximum rows to return. Defaults to 200. If the query already
            has a LIMIT clause, that takes precedence.

    Returns:
        {
            "columns": ["col1", "col2", ...],  # Column names
            "rows": [                          # List of tuples
                (val1, val2, ...),
                ...
            ],
            "row_count": int
        }

    Raises:
        ValueError: If the query is not a SELECT or contains disallowed keywords.

    Available Tables:
        - leagues: League metadata (name, season, playoff_week_start)
        - season_context: Current week info (effective_week)
        - team_profiles: Team/manager names (team_name, manager_name)
        - rosters: Roster slots and records
        - roster_players: Current player assignments (player_id, role)
        - players: NFL player data (full_name, position, nfl_team, status)
        - matchups: Weekly matchup scores
        - player_performances: Player points by week (points, role)
        - games: Head-to-head matchup results (winner_roster_id)
        - standings: Weekly standings (wins, losses, rank, points_for)
        - transactions: Trades, waivers, FA pickups
        - transaction_moves: Individual assets in transactions
        - draft_picks: Future draft pick ownership

    Example:
        >>> data.run_sql('''
        ...     SELECT p.full_name, SUM(pp.points) as total
        ...     FROM player_performances pp
        ...     JOIN players p ON pp.player_id = p.player_id
        ...     WHERE pp.roster_id = :roster_id
        ...     GROUP BY p.full_name
        ...     ORDER BY total DESC
        ... ''', {"roster_id": 1})
    """
    _ensure_select_only(query)
    sql = _ensure_limit(query, limit)
    result = conn.execute(text(sql), params or {})
    columns = list(result.keys())
    rows = [tuple(row) for row in result.all()]
    return {"columns": columns, "rows": rows, "row_count": len(rows)}
