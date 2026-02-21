# 06 — SQLAlchemy Core Migration

## Motivation

The datalayer currently uses raw `sqlite3` for all database operations: connection management, DDL, bulk inserts, and queries. This works well for the current in-memory, load-once architecture, but two upcoming changes make it worth revisiting:

1. **Persistence** — The app will persist league data and agent memory (facts, storylines) across runs. This introduces incremental updates, upserts, and schema evolution against a real database file.
2. **Future Postgres option** — While staying on SQLite for now, the persistent store should be portable enough that switching to Postgres later is a connection-string change rather than a rewrite.

SQLAlchemy Core (not ORM) addresses both without adding unnecessary abstraction over the current dict-based query pattern.

## Scope

**In scope:**
- Replace `sqlite3` connection with SQLAlchemy `create_engine` + `Connection`
- Convert `DDL_REGISTRY` (`TableSpec` → `sqlalchemy.Table` on a `MetaData`)
- Update `sqlite_store.py` (create_tables, bulk_insert) to use SQLAlchemy
- Update `_helpers.py` (`fetch_all`, `fetch_one`) to use `connection.execute(text(...))`
- Update `sql_tool.py` (`run_sql`) to use `text()`
- Update `sleeper_league_data.py` facade to manage an engine instead of a raw connection
- Preserve all existing query functions and return shapes (no public API changes)

**Out of scope:**
- SQLAlchemy ORM (Session, mapped classes, relationships)
- Postgres migration (future work; this just makes it possible)
- Persistence/incremental load logic (separate design doc)
- Agent memory tables (separate design doc; will use the new SQLAlchemy schema layer)
- Alembic migrations (separate; add when persistence lands)

## Current Architecture

### sqlite3 touchpoints

| Location | What it does |
|---|---|
| `sleeper_league_data.py:84` | `sqlite3.connect(":memory:", check_same_thread=False)` |
| `sqlite_store.py:11-15` | PRAGMAs (foreign_keys, journal_mode, temp_store) + `create_all_tables(conn)` |
| `sqlite_store.py:28-47` | `bulk_insert()` — `executemany()` with `?` placeholders, `conn.commit()` |
| `ddl.py:373-396` | `create_all_tables()` — `conn.execute()` for CREATE TABLE/INDEX |
| `_helpers.py:15-29` | `fetch_all()`/`fetch_one()` — `conn.execute(sql, params)`, named `:param` style |
| `sql_tool.py:29-93` | `run_sql()` — guarded SELECT with `conn.execute()` |
| `sleeper_league_data.py:376` | `_get_effective_week()` — direct `conn.execute()` |
| `sleeper_league_data.py:290-295` | `save_to_file()` — `conn.backup()` |

### Key patterns
- Single `sqlite3.Connection` stored on the facade, passed to all query functions
- Named parameters (`:param_name`) in queries, positional (`?`) in bulk insert
- Results built from `cursor.description` + `cursor.fetchall()` → `list[dict]`
- No explicit cursor management — `conn.execute()` returns implicit cursor
- `conn.commit()` called after each `bulk_insert`

## Target Architecture

### Engine + Connection

Replace the raw `sqlite3.Connection` with a SQLAlchemy `Engine`. Query functions receive a SQLAlchemy `Connection` instead.

```python
# sleeper_league_data.py — before
self.conn = sqlite3.connect(":memory:", check_same_thread=False)

# sleeper_league_data.py — after
from sqlalchemy import create_engine
self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
```

The `sqlite://` URL (no path) creates an in-memory database, equivalent to `":memory:"`. The facade stores the engine and provides connections to query functions.

### Connection passing strategy

Two options for how query functions get their connection:

**Option A — Pass engine, let each function open a connection:**
```python
def get_team_dossier(engine, league_id, roster_key, week):
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
```

**Option B — Pass a connection, caller manages lifecycle:**
```python
def get_team_dossier(conn, league_id, roster_key, week):
    rows = conn.execute(text(sql), params).mappings().all()
```

**Decision: Option B.** This matches the current pattern (functions receive `conn`), keeps the facade in control of connection lifecycle, and allows grouping multiple operations in one connection/transaction during load.

The facade manages the connection:
```python
# During load
with self.engine.begin() as conn:  # auto-commits on exit
    create_tables(conn, metadata)
    bulk_insert(conn, ...)

# During queries
with self.engine.connect() as conn:
    return get_team_dossier(conn, ...)
```

For the agent tool call path (which needs a long-lived connection for multiple sequential queries), the facade can hold an open connection:

```python
class SleeperLeagueData:
    def load(self):
        self.engine = create_engine(...)
        with self.engine.begin() as conn:
            # all load operations
            ...
        # Open a long-lived connection for queries
        self._query_conn = self.engine.connect()

    def get_team_dossier(self, roster_key, week=None):
        return get_team_dossier(self._query_conn, ...)
```

### Schema definition — `MetaData` + `Table`

Replace `DDL_REGISTRY` (custom `TableSpec`/`ColumnSpec` dataclasses) with SQLAlchemy `Table` objects on a shared `MetaData`. This eliminates the custom DDL generation code (`create_table_sql`, `create_index_sql`, `_column_sql`).

Foreign keys are intentionally dropped. All data comes from a single trusted source (Sleeper API), so referential integrity is guaranteed by construction. FKs add write-order constraints that complicate incremental updates, and joins work identically without them. Primary keys and unique indexes are retained to protect against duplicate data.

```python
# schema/tables.py (new file, replaces ddl.py)
from sqlalchemy import MetaData, Table, Column, Integer, Text, Float, Index

metadata = MetaData()

leagues = Table(
    "leagues", metadata,
    Column("league_id", Text, primary_key=True),
    Column("season", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("sport", Text, nullable=False),
    Column("scoring_settings_json", Text),
    Column("roster_positions_json", Text),
    Column("playoff_week_start", Integer),
    Column("playoff_teams", Integer),
    Column("league_average_match", Integer),
)

rosters = Table(
    "rosters", metadata,
    Column("league_id", Text, nullable=False),
    Column("roster_id", Integer, nullable=False),
    Column("owner_user_id", Text),
    Column("settings_json", Text),
    Column("metadata_json", Text),
    Column("record_string", Text),
    # ...
)
# ... (all 15 tables)
```

Type mapping from current DDL:

| Current `col_type` | SQLAlchemy type |
|---|---|
| `TEXT` | `Text` |
| `INTEGER` | `Integer` |
| `REAL` | `Float` |

Table creation becomes:
```python
# sqlite_store.py
def create_tables(conn, meta: MetaData):
    meta.create_all(conn)
```

### Query helpers — `text()` + `.mappings()`

The `_helpers.py` functions are the main abstraction used by all query modules. The changes are minimal:

```python
# _helpers.py — before
def fetch_all(conn, sql, params=None):
    cur = conn.execute(sql, params or {})
    columns = [col[0] for col in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]

# _helpers.py — after
from sqlalchemy import text

def fetch_all(conn, sql, params=None):
    result = conn.execute(text(sql), params or {})
    return [dict(row) for row in result.mappings().all()]
```

SQLAlchemy's `.mappings()` returns `RowMapping` objects (dict-like), eliminating the manual `cursor.description` → `zip` pattern. This is the single biggest ergonomic win — it removes the most repeated boilerplate.

`fetch_one` follows the same pattern:
```python
def fetch_one(conn, sql, params=None):
    result = conn.execute(text(sql), params or {})
    row = result.mappings().first()
    return dict(row) if row else None
```

### Bulk insert

```python
# sqlite_store.py — before
placeholders = ", ".join(["?"] * len(columns))
sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders});"
conn.executemany(sql, values)

# sqlite_store.py — after
from sqlalchemy import text

def bulk_insert(conn, table_name, rows):
    normalized = [_normalize_row(row) for row in rows]
    if not normalized:
        return 0
    columns = list(normalized[0].keys())
    placeholders = ", ".join(f":{col}" for col in columns)
    col_list = ", ".join(columns)
    sql = text(f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})")
    conn.execute(sql, normalized)
    return len(normalized)
```

Key changes:
- Named placeholders (`:col`) instead of positional (`?`) — consistent with query style
- `conn.execute(text(sql), list_of_dicts)` replaces `executemany` — SQLAlchemy handles batching
- No explicit `conn.commit()` — the caller uses `engine.begin()` for transactional blocks
- Boolean conversion can be dropped — SQLAlchemy handles `bool` → `int` for SQLite

### Guarded SQL (`run_sql`)

Minimal change — the validation logic stays the same, only the execution changes:

```python
# sql_tool.py — after
from sqlalchemy import text

def run_sql(conn, query, params=None, *, limit=200):
    _ensure_select_only(query)
    sql = _ensure_limit(query, limit)
    result = conn.execute(text(sql), params or {})
    columns = list(result.keys())
    rows = [tuple(row) for row in result.all()]
    return {"columns": columns, "rows": rows, "row_count": len(rows)}
```

The agent's raw SQL still works — `text()` executes arbitrary SQL strings. The guard rails (`_ensure_select_only`, `_ensure_limit`) remain unchanged.

### Parameter binding style

SQLAlchemy's `text()` uses `:param_name` style, which is what the query modules already use. No changes needed to any SQL strings in the query modules.

The only SQL that uses positional `?` placeholders is `bulk_insert`, which switches to named `:col` placeholders as shown above.

### `save_to_file`

The `conn.backup()` method is a `sqlite3`-specific API. With SQLAlchemy on SQLite, we can access the underlying connection:

```python
def save_to_file(self, output_path):
    raw_conn = self.engine.raw_connection()
    try:
        file_conn = sqlite3.connect(output_path)
        raw_conn.backup(file_conn)
        file_conn.commit()
        file_conn.close()
    finally:
        raw_conn.close()
```

This is a SQLite-specific escape hatch. When/if Postgres is adopted, this method would be replaced with `pg_dump` or similar.

### `_get_effective_week`

This method does a direct `conn.execute()` on the facade. Update to use `text()`:

```python
def _get_effective_week(self, week=None):
    if week is not None:
        return week
    if not self._query_conn:
        return None
    result = self._query_conn.execute(
        text("SELECT effective_week FROM season_context LIMIT 1")
    ).first()
    return result[0] if result else None
```

## Implementation Steps

### Step 1: Add SQLAlchemy dependency

Add `sqlalchemy` to `pyproject.toml` / `setup.cfg`. No version pinning beyond `>=2.0` (we use the 2.0-style API exclusively).

### Step 2: Create `schema/tables.py`

Translate all 15 `DDL_REGISTRY` entries into SQLAlchemy `Table` objects on a shared `MetaData`. Keep `ddl.py` temporarily for reference but nothing should import from it after this step.

Validation: `metadata.create_all(engine)` produces identical tables to current DDL. Write a test that compares `PRAGMA table_info` output before/after.

### Step 3: Update `sqlite_store.py`

- `create_tables()` → `metadata.create_all(conn)` (+ PRAGMAs via events or direct execute)
- `bulk_insert()` → named-placeholder `text()` with `conn.execute(sql, list_of_dicts)`
- Drop boolean conversion (SQLAlchemy handles it)

### Step 4: Update `_helpers.py`

- `fetch_all()` and `fetch_one()` → use `text()` + `.mappings()`
- No changes to function signatures (still `conn, sql, params`)

### Step 5: Update `sql_tool.py`

- `run_sql()` → `text()` + `result.keys()` + `result.all()`
- Guard logic unchanged

### Step 6: Update `sleeper_league_data.py`

- Replace `sqlite3.connect()` with `create_engine("sqlite://", ...)`
- `load()` uses `engine.begin()` context manager for all inserts
- Query methods use a long-lived connection (or open per-call)
- `save_to_file()` uses `engine.raw_connection()` for backup
- `_get_effective_week()` uses `text()`
- Remove `import sqlite3` (except in `save_to_file` which still needs it for the file target)

### Step 7: Update query modules

Each query module file (`league.py`, `team.py`, `player.py`, `transactions.py`, `playoffs.py`, `_resolvers.py`) already uses `fetch_all`/`fetch_one` from `_helpers.py`. If any module calls `conn.execute()` directly, wrap those in `text()`.

Scan for any direct `conn.execute()` calls outside of `_helpers.py` and update them.

### Step 8: Delete `ddl.py`

Once `tables.py` is verified and all imports are updated, remove `ddl.py` and its custom spec classes (`ColumnSpec`, `TableSpec`, `ForeignKeySpec`, `IndexSpec`, `create_table_sql`, `create_index_sql`).

### Step 9: Run tests, verify identical behavior

All existing tests should pass without changes to test code (the public API doesn't change). The fixtures and query assertions remain the same.

Key things to verify:
- All 15 tables created with correct columns, types, PKs, and indexes
- `bulk_insert` works with dataclass instances and dicts
- Named parameter binding works in all query modules
- `run_sql` guard rails still block write operations
- `save_to_file` produces a valid SQLite file
- `check_same_thread=False` still works for async agent calls

## What This Enables

After this migration, adding persistence and agent memory becomes straightforward:

- **Persistent SQLite**: Change `"sqlite://"` to `"sqlite:///path/to/league.db"` — everything else works
- **Incremental loads**: Use `insert().on_conflict_do_update()` or conditional logic against existing data
- **Alembic migrations**: Point Alembic at the `MetaData` object to auto-generate migration scripts when tables change
- **Memory tables**: Define new `Table` objects on the same `MetaData` — they get created alongside league tables
- **Postgres**: Change the URL to `"postgresql://..."` and address any dialect-specific SQL in query modules

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| SQLAlchemy `text()` parameter binding differs subtly from `sqlite3` | Both use `:name` style for named params; bulk insert switches from `?` to `:name` which is safer |
| `.mappings()` returns `RowMapping` not `dict` | Wrap in `dict()` to match current return types exactly |
| `conn.backup()` is SQLite-specific | Use `raw_connection()` escape hatch; document as SQLite-only |
| Performance regression from SQLAlchemy overhead | Negligible for this workload (one-time load + read-only queries); in-memory SQLite is the bottleneck ceiling |
| Query modules with direct `conn.execute()` missed | Grep for `conn.execute` across all query files in step 7 |
