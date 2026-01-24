"""SQLite DDL helpers for canonical schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    col_type: str
    nullable: bool = True


@dataclass(frozen=True)
class ForeignKeySpec:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass(frozen=True)
class IndexSpec:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[ColumnSpec, ...]
    primary_key: tuple[str, ...] | None = None
    foreign_keys: tuple[ForeignKeySpec, ...] = ()
    indexes: tuple[IndexSpec, ...] = ()


def _column_sql(column: ColumnSpec) -> str:
    parts = [column.name, column.col_type]
    if not column.nullable:
        parts.append("NOT NULL")
    return " ".join(parts)


def create_table_sql(spec: TableSpec) -> str:
    column_defs = [_column_sql(column) for column in spec.columns]
    if spec.primary_key:
        column_defs.append(f"PRIMARY KEY ({', '.join(spec.primary_key)})")
    for fk in spec.foreign_keys:
        cols = ", ".join(fk.columns)
        ref_cols = ", ".join(fk.ref_columns)
        column_defs.append(
            f"FOREIGN KEY ({cols}) REFERENCES {fk.ref_table} ({ref_cols})"
        )
    joined = ", ".join(column_defs)
    return f"CREATE TABLE IF NOT EXISTS {spec.name} ({joined});"


def create_index_sql(table: str, index: IndexSpec) -> str:
    unique = "UNIQUE " if index.unique else ""
    cols = ", ".join(index.columns)
    return f"CREATE {unique}INDEX IF NOT EXISTS {index.name} ON {table} ({cols});"


DDL_REGISTRY: dict[str, TableSpec] = {
    "leagues": TableSpec(
        name="leagues",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("season", "TEXT", nullable=False),
            ColumnSpec("name", "TEXT", nullable=False),
            ColumnSpec("sport", "TEXT", nullable=False),
            ColumnSpec("scoring_settings_json", "TEXT"),
            ColumnSpec("roster_positions_json", "TEXT"),
            ColumnSpec("playoff_week_start", "INTEGER"),
            ColumnSpec("playoff_teams", "INTEGER"),
        ),
        primary_key=("league_id",),
    ),
    "season_context": TableSpec(
        name="season_context",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("computed_week", "INTEGER", nullable=False),
            ColumnSpec("override_week", "INTEGER"),
            ColumnSpec("effective_week", "INTEGER", nullable=False),
            ColumnSpec("generated_at", "TEXT", nullable=False),
        ),
        primary_key=("league_id",),
        foreign_keys=(
            ForeignKeySpec(("league_id",), "leagues", ("league_id",)),
        ),
    ),
    "users": TableSpec(
        name="users",
        columns=(
            ColumnSpec("user_id", "TEXT", nullable=False),
            ColumnSpec("display_name", "TEXT", nullable=False),
            ColumnSpec("avatar", "TEXT"),
            ColumnSpec("metadata_json", "TEXT"),
        ),
        primary_key=("user_id",),
    ),
    "rosters": TableSpec(
        name="rosters",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("roster_id", "INTEGER", nullable=False),
            ColumnSpec("owner_user_id", "TEXT"),
            ColumnSpec("settings_json", "TEXT"),
            ColumnSpec("metadata_json", "TEXT"),
        ),
        primary_key=("league_id", "roster_id"),
        foreign_keys=(
            ForeignKeySpec(("league_id",), "leagues", ("league_id",)),
            ForeignKeySpec(("owner_user_id",), "users", ("user_id",)),
        ),
        indexes=(
            IndexSpec("idx_rosters_league_roster", ("league_id", "roster_id")),
        ),
    ),
    "team_profiles": TableSpec(
        name="team_profiles",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("roster_id", "INTEGER", nullable=False),
            ColumnSpec("team_name", "TEXT"),
            ColumnSpec("manager_name", "TEXT"),
            ColumnSpec("avatar_url", "TEXT"),
        ),
        primary_key=("league_id", "roster_id"),
        foreign_keys=(
            ForeignKeySpec(("league_id", "roster_id"), "rosters", ("league_id", "roster_id")),
        ),
        indexes=(
            IndexSpec("idx_team_profiles_team_name", ("team_name",)),
            IndexSpec("idx_team_profiles_manager_name", ("manager_name",)),
        ),
    ),
    "draft_picks": TableSpec(
        name="draft_picks",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("season", "TEXT", nullable=False),
            ColumnSpec("round", "INTEGER", nullable=False),
            ColumnSpec("original_roster_id", "INTEGER", nullable=False),
            ColumnSpec("current_roster_id", "INTEGER", nullable=False),
            ColumnSpec("pick_id", "TEXT"),
            ColumnSpec("source", "TEXT"),
        ),
        primary_key=("league_id", "season", "round", "original_roster_id"),
        foreign_keys=(
            ForeignKeySpec(("league_id", "original_roster_id"), "rosters", ("league_id", "roster_id")),
            ForeignKeySpec(("league_id", "current_roster_id"), "rosters", ("league_id", "roster_id")),
        ),
        indexes=(
            IndexSpec("idx_draft_picks_current", ("league_id", "current_roster_id")),
            IndexSpec("idx_draft_picks_original", ("league_id", "original_roster_id")),
            IndexSpec("idx_draft_picks_season_round", ("league_id", "season", "round")),
        ),
    ),
    "matchups": TableSpec(
        name="matchups",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("season", "TEXT", nullable=False),
            ColumnSpec("week", "INTEGER", nullable=False),
            ColumnSpec("matchup_id", "INTEGER", nullable=False),
            ColumnSpec("roster_id", "INTEGER", nullable=False),
            ColumnSpec("points", "REAL", nullable=False),
            ColumnSpec("starters_json", "TEXT"),
            ColumnSpec("players_json", "TEXT"),
            ColumnSpec("players_points_json", "TEXT"),
        ),
        primary_key=("league_id", "week", "matchup_id", "roster_id"),
        foreign_keys=(
            ForeignKeySpec(("league_id",), "leagues", ("league_id",)),
            ForeignKeySpec(("league_id", "roster_id"), "rosters", ("league_id", "roster_id")),
        ),
        indexes=(
            IndexSpec("idx_matchups_league_season_week", ("league_id", "season", "week")),
            IndexSpec("idx_matchups_week_matchup", ("week", "matchup_id")),
        ),
    ),
    "games": TableSpec(
        name="games",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("season", "TEXT", nullable=False),
            ColumnSpec("week", "INTEGER", nullable=False),
            ColumnSpec("matchup_id", "INTEGER", nullable=False),
            ColumnSpec("roster_id_a", "INTEGER", nullable=False),
            ColumnSpec("roster_id_b", "INTEGER", nullable=False),
            ColumnSpec("points_a", "REAL", nullable=False),
            ColumnSpec("points_b", "REAL", nullable=False),
            ColumnSpec("winner_roster_id", "INTEGER"),
            ColumnSpec("is_playoffs", "INTEGER", nullable=False),
        ),
        primary_key=("league_id", "week", "matchup_id"),
        foreign_keys=(
            ForeignKeySpec(("league_id",), "leagues", ("league_id",)),
            ForeignKeySpec(("league_id", "roster_id_a"), "rosters", ("league_id", "roster_id")),
            ForeignKeySpec(("league_id", "roster_id_b"), "rosters", ("league_id", "roster_id")),
            ForeignKeySpec(("league_id", "winner_roster_id"), "rosters", ("league_id", "roster_id")),
        ),
        indexes=(
            IndexSpec("idx_games_league_season_week", ("league_id", "season", "week")),
        ),
    ),
    "players": TableSpec(
        name="players",
        columns=(
            ColumnSpec("player_id", "TEXT", nullable=False),
            ColumnSpec("full_name", "TEXT"),
            ColumnSpec("position", "TEXT"),
            ColumnSpec("nfl_team", "TEXT"),
            ColumnSpec("status", "TEXT"),
            ColumnSpec("injury_status", "TEXT"),
            ColumnSpec("age", "INTEGER"),
            ColumnSpec("years_exp", "INTEGER"),
            ColumnSpec("metadata_json", "TEXT"),
            ColumnSpec("updated_at", "TEXT"),
        ),
        primary_key=("player_id",),
        indexes=(
            IndexSpec("idx_players_full_name", ("full_name",)),
        ),
    ),
    "roster_players": TableSpec(
        name="roster_players",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("roster_id", "INTEGER", nullable=False),
            ColumnSpec("player_id", "TEXT", nullable=False),
            ColumnSpec("role", "TEXT", nullable=False),
        ),
        primary_key=("league_id", "roster_id", "player_id"),
        foreign_keys=(
            ForeignKeySpec(("league_id", "roster_id"), "rosters", ("league_id", "roster_id")),
            ForeignKeySpec(("player_id",), "players", ("player_id",)),
        ),
        indexes=(
            IndexSpec("idx_roster_players_league_roster", ("league_id", "roster_id")),
            IndexSpec("idx_roster_players_player", ("player_id",)),
        ),
    ),
    "transactions": TableSpec(
        name="transactions",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("season", "TEXT", nullable=False),
            ColumnSpec("week", "INTEGER", nullable=False),
            ColumnSpec("transaction_id", "TEXT", nullable=False),
            ColumnSpec("type", "TEXT", nullable=False),
            ColumnSpec("status", "TEXT"),
            ColumnSpec("created_ts", "INTEGER"),
            ColumnSpec("settings_json", "TEXT"),
            ColumnSpec("metadata_json", "TEXT"),
        ),
        primary_key=("transaction_id",),
        foreign_keys=(
            ForeignKeySpec(("league_id",), "leagues", ("league_id",)),
        ),
        indexes=(
            IndexSpec("idx_transactions_league_season_week", ("league_id", "season", "week")),
        ),
    ),
    "transaction_moves": TableSpec(
        name="transaction_moves",
        columns=(
            ColumnSpec("transaction_id", "TEXT", nullable=False),
            ColumnSpec("roster_id", "INTEGER"),
            ColumnSpec("player_id", "TEXT"),
            ColumnSpec("asset_type", "TEXT", nullable=False),
            ColumnSpec("direction", "TEXT", nullable=False),
            ColumnSpec("bid_amount", "INTEGER"),
            ColumnSpec("from_roster_id", "INTEGER"),
            ColumnSpec("to_roster_id", "INTEGER"),
            ColumnSpec("pick_season", "TEXT"),
            ColumnSpec("pick_round", "INTEGER"),
            ColumnSpec("pick_original_roster_id", "INTEGER"),
            ColumnSpec("pick_id", "TEXT"),
        ),
        foreign_keys=(
            ForeignKeySpec(("transaction_id",), "transactions", ("transaction_id",)),
        ),
        indexes=(
            IndexSpec("idx_transaction_moves_tx", ("transaction_id",)),
            IndexSpec("idx_transaction_moves_roster", ("roster_id",)),
        ),
    ),
    "standings": TableSpec(
        name="standings",
        columns=(
            ColumnSpec("league_id", "TEXT", nullable=False),
            ColumnSpec("season", "TEXT", nullable=False),
            ColumnSpec("week", "INTEGER", nullable=False),
            ColumnSpec("roster_id", "INTEGER", nullable=False),
            ColumnSpec("wins", "INTEGER", nullable=False),
            ColumnSpec("losses", "INTEGER", nullable=False),
            ColumnSpec("ties", "INTEGER", nullable=False),
            ColumnSpec("points_for", "REAL", nullable=False),
            ColumnSpec("points_against", "REAL", nullable=False),
            ColumnSpec("rank", "INTEGER"),
            ColumnSpec("streak_type", "TEXT"),
            ColumnSpec("streak_len", "INTEGER"),
        ),
        primary_key=("league_id", "week", "roster_id"),
        foreign_keys=(
            ForeignKeySpec(("league_id", "roster_id"), "rosters", ("league_id", "roster_id")),
        ),
    ),
}


def create_all_tables(conn, table_names: Sequence[str] | None = None) -> None:
    ordered_tables = (
        "leagues",
        "users",
        "rosters",
        "team_profiles",
        "draft_picks",
        "players",
        "roster_players",
        "season_context",
        "matchups",
        "games",
        "transactions",
        "transaction_moves",
        "standings",
    )
    tables = table_names or ordered_tables
    for table in tables:
        spec = DDL_REGISTRY[table]
        conn.execute(create_table_sql(spec))
        for index in spec.indexes:
            conn.execute(create_index_sql(spec.name, index))
