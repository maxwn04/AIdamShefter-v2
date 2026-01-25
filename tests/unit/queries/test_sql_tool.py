import sqlite3

import pytest

from datalayer.sleeper_data.queries.sql_tool import run_sql


def test_run_sql_applies_limit():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sample (id INTEGER);")
    conn.executemany("INSERT INTO sample (id) VALUES (?)", [(1,), (2,), (3,)])

    result = run_sql(conn, "SELECT id FROM sample")

    assert result["columns"] == ["id"]
    assert result["row_count"] == 3


def test_run_sql_rejects_non_select():
    conn = sqlite3.connect(":memory:")

    with pytest.raises(ValueError):
        run_sql(conn, "DELETE FROM sample;")
