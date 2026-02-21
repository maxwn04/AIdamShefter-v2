from sqlalchemy import text

from datalayer.sleeper_data.store.sqlite_store import create_tables


def test_create_tables_and_indexes(sa_conn):
    create_tables(sa_conn)

    tables = {
        row[0]
        for row in sa_conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'")
        ).fetchall()
    }
    assert "leagues" in tables
    assert "rosters" in tables
    assert "games" in tables

    indexes = {
        row[0]
        for row in sa_conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'index'")
        ).fetchall()
    }
    assert "idx_rosters_league_roster" in indexes
    assert "idx_matchups_league_season_week" in indexes
