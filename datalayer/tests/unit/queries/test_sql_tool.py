import pytest
from sqlalchemy import text

from datalayer.sleeper_data.queries.sql_tool import run_sql


def test_run_sql_applies_limit(sa_conn):
    sa_conn.execute(text("CREATE TABLE sample (id INTEGER)"))
    sa_conn.execute(text("INSERT INTO sample (id) VALUES (:v1), (:v2), (:v3)"), {"v1": 1, "v2": 2, "v3": 3})

    result = run_sql(sa_conn, "SELECT id FROM sample")

    assert result["columns"] == ["id"]
    assert result["row_count"] == 3


def test_run_sql_rejects_non_select(sa_conn):
    with pytest.raises(ValueError):
        run_sql(sa_conn, "DELETE FROM sample;")
