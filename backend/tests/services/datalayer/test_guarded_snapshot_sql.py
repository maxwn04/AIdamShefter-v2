from __future__ import annotations

import json

import pytest

from backend.services.datalayer import FrozenLeagueData, ReadyDataSnapshot
from backend.services.datalayer.query import guarded_sql
from backend.tests.services.datalayer.test_frozen_query_runtime import ready_snapshot


def test_select_cte_named_params_comments_and_quoted_keywords_are_allowed(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        assert data.run_sql(
            "-- safe\nWITH chosen AS ("
            "SELECT roster_id, points FROM matchups WHERE week = :week"
            ") SELECT roster_id, 'DROP TABLE players' AS note "
            "FROM chosen ORDER BY roster_id",
            {"week": 2},
        ) == {
            "columns": ["roster_id", "note"],
            "rows": [(1, "DROP TABLE players"), (2, "DROP TABLE players")],
            "row_count": 2,
        }


@pytest.mark.parametrize(
    "statement",
    [
        "",
        "DELETE FROM players",
        "PRAGMA table_info(players)",
        "ATTACH DATABASE 'elsewhere.sqlite' AS other",
        "SELECT * FROM players; DROP TABLE players",
        "SELECT * FROM sqlite_schema",
        "SELECT * FROM pragma_database_list",
        "WITH changed AS (DELETE FROM players RETURNING *) SELECT * FROM changed",
        "SELECT load_extension('elsewhere')",
        "SELECT readfile('elsewhere')",
    ],
)
def test_non_read_or_artifact_escape_sql_is_rejected(
    ready_snapshot: ReadyDataSnapshot,
    statement: str,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        with pytest.raises(ValueError):
            data.run_sql(statement)


def test_runtime_limit_cannot_be_bypassed_by_query_limit(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        result = data.run_sql(
            "WITH RECURSIVE numbers(n) AS ("
            "SELECT 1 UNION ALL SELECT n + 1 FROM numbers WHERE n < 500"
            ") SELECT n FROM numbers LIMIT 500",
            limit=7,
        )
        assert result["row_count"] == 7
        assert result["rows"][-1] == (7,)
        for invalid in (0, 201, True, 1.5):
            with pytest.raises(ValueError, match="limit"):
                data.run_sql("SELECT 1", limit=invalid)  # type: ignore[arg-type]


def test_deadline_interrupts_expensive_recursive_query(
    ready_snapshot: ReadyDataSnapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(guarded_sql, "SQL_DEADLINE_SECONDS", 0.0)
    with FrozenLeagueData.open(ready_snapshot) as data:
        with pytest.raises(TimeoutError, match="deadline"):
            data.run_sql(
                "WITH RECURSIVE numbers(n) AS ("
                "SELECT 1 UNION ALL SELECT n + 1 FROM numbers"
                ") SELECT SUM(n) FROM numbers"
            )
        assert data.run_sql("SELECT 1")["rows"] == [(1,)]


def test_results_are_json_safe_and_non_finite_values_fail_closed(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        result = data.run_sql("SELECT CAST('abc' AS BLOB) AS content")
        assert result["rows"] == [("base64:YWJj",)]
        json.dumps(result, allow_nan=False)
        with pytest.raises(ValueError, match="non-finite"):
            data.run_sql("SELECT 1e999 AS infinity")


def test_immutable_connection_rejects_writes_even_beyond_parser(
    ready_snapshot: ReadyDataSnapshot,
) -> None:
    with FrozenLeagueData.open(ready_snapshot) as data:
        with pytest.raises(ValueError):
            data.run_sql("WITH candidate AS (SELECT 1) UPDATE players SET age = 0")
