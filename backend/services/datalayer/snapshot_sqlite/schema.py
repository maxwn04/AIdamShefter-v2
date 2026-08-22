"""Versioned SQLite schema for immutable reporter snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
)


SNAPSHOT_TABLE_ORDER = (
    "leagues",
    "season_context",
    "users",
    "rosters",
    "team_profiles",
    "draft_picks",
    "players",
    "matchups",
    "player_performances",
    "games",
    "roster_players",
    "transactions",
    "transaction_moves",
    "playoff_matchups",
    "standings",
    "snapshot_metadata",
)


@dataclass(frozen=True, slots=True)
class SnapshotSchema:
    projection_version: str
    metadata: MetaData
    tables: Mapping[str, Table]
    table_order: tuple[str, ...]


def _build_v1() -> SnapshotSchema:
    metadata = MetaData()

    Table(
        "leagues",
        metadata,
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
    Table(
        "season_context",
        metadata,
        Column("league_id", Text, primary_key=True),
        Column("computed_week", Integer, nullable=False),
        Column("override_week", Integer),
        Column("effective_week", Integer, nullable=False),
        Column("generated_at", Text),
    )
    Table(
        "users",
        metadata,
        Column("user_id", Text, primary_key=True),
        Column("display_name", Text, nullable=False),
        Column("avatar", Text),
        Column("metadata_json", Text),
    )
    Table(
        "rosters",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("roster_id", Integer, nullable=False),
        Column("owner_user_id", Text),
        Column("settings_json", Text),
        Column("metadata_json", Text),
        Column("record_string", Text),
        PrimaryKeyConstraint("league_id", "roster_id"),
        Index("idx_rosters_league_roster", "league_id", "roster_id"),
    )
    Table(
        "team_profiles",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("roster_id", Integer, nullable=False),
        Column("team_name", Text),
        Column("manager_name", Text),
        Column("avatar_url", Text),
        PrimaryKeyConstraint("league_id", "roster_id"),
        Index("idx_team_profiles_team_name", "team_name"),
        Index("idx_team_profiles_manager_name", "manager_name"),
    )
    Table(
        "draft_picks",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("season", Text, nullable=False),
        Column("round", Integer, nullable=False),
        Column("original_roster_id", Integer, nullable=False),
        Column("current_roster_id", Integer, nullable=False),
        Column("pick_id", Text),
        Column("source", Text),
        PrimaryKeyConstraint("league_id", "season", "round", "original_roster_id"),
        Index("idx_draft_picks_current", "league_id", "current_roster_id"),
        Index("idx_draft_picks_original", "league_id", "original_roster_id"),
        Index("idx_draft_picks_season_round", "league_id", "season", "round"),
    )
    Table(
        "players",
        metadata,
        Column("player_id", Text, primary_key=True),
        Column("full_name", Text),
        Column("position", Text),
        Column("nfl_team", Text),
        Column("status", Text),
        Column("injury_status", Text),
        Column("age", Integer),
        Column("years_exp", Integer),
        Column("metadata_json", Text),
        Column("updated_at", Text),
        Index("idx_players_full_name", "full_name"),
    )
    Table(
        "matchups",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("season", Text, nullable=False),
        Column("week", Integer, nullable=False),
        Column("matchup_id", Integer, nullable=False),
        Column("roster_id", Integer, nullable=False),
        Column("points", Float, nullable=False),
        PrimaryKeyConstraint("league_id", "week", "matchup_id", "roster_id"),
        Index("idx_matchups_league_season_week", "league_id", "season", "week"),
        Index("idx_matchups_week_matchup", "week", "matchup_id"),
    )
    Table(
        "player_performances",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("season", Text, nullable=False),
        Column("week", Integer, nullable=False),
        Column("player_id", Text, nullable=False),
        Column("roster_id", Integer, nullable=False),
        Column("matchup_id", Integer, nullable=False),
        Column("points", Float, nullable=False),
        Column("role", Text),
        PrimaryKeyConstraint("league_id", "season", "week", "player_id", "roster_id"),
        Index("idx_player_perf_league_week", "league_id", "week"),
        Index("idx_player_perf_player_week", "player_id", "season", "week"),
        Index("idx_player_perf_roster_week", "league_id", "roster_id", "week"),
    )
    Table(
        "games",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("season", Text, nullable=False),
        Column("week", Integer, nullable=False),
        Column("matchup_id", Integer, nullable=False),
        Column("roster_id_a", Integer, nullable=False),
        Column("roster_id_b", Integer, nullable=False),
        Column("points_a", Float, nullable=False),
        Column("points_b", Float, nullable=False),
        Column("winner_roster_id", Integer),
        Column("is_playoffs", Integer, nullable=False),
        PrimaryKeyConstraint("league_id", "week", "matchup_id"),
        Index("idx_games_league_season_week", "league_id", "season", "week"),
    )
    Table(
        "roster_players",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("roster_id", Integer, nullable=False),
        Column("player_id", Text, nullable=False),
        Column("role", Text, nullable=False),
        PrimaryKeyConstraint("league_id", "roster_id", "player_id"),
        Index("idx_roster_players_league_roster", "league_id", "roster_id"),
        Index("idx_roster_players_player", "player_id"),
    )
    Table(
        "transactions",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("season", Text, nullable=False),
        Column("week", Integer, nullable=False),
        Column("transaction_id", Text, primary_key=True),
        Column("type", Text, nullable=False),
        Column("status", Text),
        Column("created_ts", Integer),
        Column("settings_json", Text),
        Column("metadata_json", Text),
        Index("idx_transactions_league_season_week", "league_id", "season", "week"),
    )
    Table(
        "transaction_moves",
        metadata,
        Column("transaction_id", Text, nullable=False),
        Column("move_index", Integer, nullable=False),
        Column("roster_id", Integer),
        Column("player_id", Text),
        Column("asset_type", Text, nullable=False),
        Column("direction", Text, nullable=False),
        Column("bid_amount", Integer),
        Column("from_roster_id", Integer),
        Column("to_roster_id", Integer),
        Column("pick_season", Text),
        Column("pick_round", Integer),
        Column("pick_original_roster_id", Integer),
        Column("pick_id", Text),
        PrimaryKeyConstraint("transaction_id", "move_index", "direction"),
        Index("idx_transaction_moves_tx", "transaction_id"),
        Index("idx_transaction_moves_roster", "roster_id"),
    )
    Table(
        "playoff_matchups",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("season", Text, nullable=False),
        Column("bracket_type", Text, nullable=False),
        Column("node_key", Text, nullable=False),
        Column("round", Integer, nullable=False),
        Column("matchup_id", Integer),
        Column("t1_roster_id", Integer),
        Column("t2_roster_id", Integer),
        Column("t1_from_matchup_id", Integer),
        Column("t1_from_outcome", Text),
        Column("t2_from_matchup_id", Integer),
        Column("t2_from_outcome", Text),
        Column("winner_roster_id", Integer),
        Column("loser_roster_id", Integer),
        Column("placement", Integer),
        PrimaryKeyConstraint("league_id", "season", "bracket_type", "node_key"),
        Index(
            "idx_playoff_matchups_bracket_round",
            "league_id",
            "season",
            "bracket_type",
            "round",
        ),
        Index("idx_playoff_matchups_winner", "league_id", "winner_roster_id"),
    )
    Table(
        "standings",
        metadata,
        Column("league_id", Text, nullable=False),
        Column("season", Text, nullable=False),
        Column("week", Integer, nullable=False),
        Column("roster_id", Integer, nullable=False),
        Column("wins", Integer, nullable=False),
        Column("losses", Integer, nullable=False),
        Column("ties", Integer, nullable=False),
        Column("points_for", Float, nullable=False),
        Column("points_against", Float, nullable=False),
        Column("rank", Integer),
        Column("streak_type", Text),
        Column("streak_len", Integer),
        PrimaryKeyConstraint("league_id", "week", "roster_id"),
    )
    Table(
        "snapshot_metadata",
        metadata,
        Column("singleton_id", Integer, primary_key=True),
        Column("build_key", Text, nullable=False, unique=True),
        Column("competition_id", Text, nullable=False),
        Column("primary_competition_season_id", Text, nullable=False),
        Column("sleeper_league_id", Text, nullable=False),
        Column("season_year", Integer, nullable=False),
        Column("through_week", Integer, nullable=False),
        Column("as_of_date", Text, nullable=False),
        Column("snapshot_projection_version", Text, nullable=False),
        Column("selected_requests_json", Text, nullable=False),
        Column("completeness_warnings_json", Text, nullable=False),
        CheckConstraint("singleton_id = 1", name="ck_snapshot_metadata_singleton"),
    )
    tables = MappingProxyType(dict(metadata.tables))
    return SnapshotSchema("1", metadata, tables, SNAPSHOT_TABLE_ORDER)


_V1 = _build_v1()


def get_snapshot_schema(projection_version: str) -> SnapshotSchema:
    """Return the exact schema owned by a supported projection version."""

    if projection_version != "1":
        raise ValueError(
            f"unsupported snapshot projection version: {projection_version!r}"
        )
    return _V1
