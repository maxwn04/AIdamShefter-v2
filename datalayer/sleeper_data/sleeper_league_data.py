"""Public facade for Sleeper league data: load orchestration + curated queries.

Layer contract:
- Owns engine/connection lifecycle and the public query API.
- Delegates fetch/normalize/store to ``load.load_league``.
- Delegates SQL to ``queries.*``; does not contain business SQL itself.
- Tools/CLI should call this class only.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from .config import SleeperConfig, load_config
from .load import load_league
from .sleeper_api import SleeperClient
from .queries import (
    get_bench_analysis,
    get_league_snapshot,
    get_player_summary,
    get_player_weekly_log,
    get_season_leaders,
    get_playoff_bracket as query_get_playoff_bracket,
    get_roster_current,
    get_roster_snapshot,
    get_standings,
    get_team_dossier,
    get_team_game,
    get_team_game_with_players,
    get_team_playoff_path as query_get_team_playoff_path,
    get_team_schedule,
    get_team_transactions,
    get_transactions as query_get_transactions,
    get_week_games,
    get_week_games_with_players,
    get_week_player_leaderboard,
    run_sql,
)


class SleeperLeagueData:
    def __init__(
        self,
        league_id: Optional[str] = None,
        *,
        client: Optional[SleeperClient] = None,
        config: Optional[SleeperConfig] = None,
    ) -> None:
        resolved_config = config or load_config()
        self.league_id = league_id or resolved_config.league_id
        self.week_override = resolved_config.week_override
        self.client = client or SleeperClient()
        self.engine = None
        self._query_conn: Connection | None = None
        self.effective_week: Optional[int] = None

    def _conn(self) -> Connection:
        if not self._query_conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return self._query_conn

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> "SleeperLeagueData":
        """Open a previously exported SQLite snapshot for querying.

        This bypasses Sleeper API loading entirely and is intended for
        multi-step agent runs that need a stable view of league data.
        """
        snapshot_path = Path(path).expanduser().resolve()
        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

        obj = cls.__new__(cls)
        obj.engine = create_engine(
            f"sqlite:///{snapshot_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        obj._query_conn = obj.engine.connect()

        league_row = obj._query_conn.execute(
            text("SELECT league_id FROM leagues LIMIT 1")
        ).first()
        if league_row is None:
            obj._query_conn.close()
            raise ValueError(f"Snapshot has no league row: {snapshot_path}")

        context_row = obj._query_conn.execute(
            text(
                "SELECT effective_week, override_week "
                "FROM season_context LIMIT 1"
            )
        ).first()

        obj.league_id = str(league_row._mapping["league_id"])
        obj.effective_week = (
            int(context_row._mapping["effective_week"])
            if context_row is not None
            else None
        )
        obj.week_override = (
            int(context_row._mapping["override_week"])
            if context_row is not None
            and context_row._mapping["override_week"] is not None
            else None
        )
        obj.client = SleeperClient()

        return obj

    def load(self) -> None:
        # check_same_thread=False allows the connection to be used from
        # different threads (needed for async agent tool calls)
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}
        )
        result = load_league(
            self.engine,
            client=self.client,
            league_id=self.league_id,
            week_override=self.week_override,
        )
        self.effective_week = result.effective_week
        # Open a long-lived connection for queries
        self._query_conn = self.engine.connect()

    def save_to_file(self, output_path: str) -> str:
        if not self.engine:
            raise RuntimeError("Data not loaded. Call load() before saving.")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        raw_conn = self.engine.raw_connection()
        try:
            file_conn = sqlite3.connect(output_path)
            raw_conn.backup(file_conn)
            file_conn.commit()
            file_conn.close()
        finally:
            raw_conn.close()

        return output_path

    def _get_effective_week(self, week: int | None = None) -> int | None:
        """Get effective week, defaulting to current week if not specified."""
        if week is not None:
            return week
        conn = self._query_conn
        if conn is None:
            return None
        result = conn.execute(
            text("SELECT effective_week FROM season_context LIMIT 1")
        ).first()
        return result[0] if result else None

    def get_league_snapshot(self, week: int | None = None) -> dict[str, Any]:
        """Get league standings, games, and transactions for a week.

        See queries.league.get_league_snapshot for full return structure.
        """
        return get_league_snapshot(self._conn(), week)

    def get_bench_analysis(
        self, roster_key: Any = None, week: int | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Get starter vs bench scoring breakdown for a week.

        Args:
            roster_key: Optional team name, manager name, or roster_id.
                If provided, returns team-specific breakdown with bench player details.
            week: Week number (defaults to current week).

        See queries.league.get_bench_analysis for full return structure.
        """
        conn = self._conn()
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            if roster_key is not None:
                return {"found": False, "roster_key": roster_key}
            return []
        return get_bench_analysis(
            conn, self.league_id, int(effective_week), roster_key
        )

    def get_standings(self, week: int | None = None) -> dict[str, Any]:
        """Get league standings for a specific week.

        Args:
            week: Week number (defaults to current week).

        See queries.league.get_standings for full return structure.
        """
        return get_standings(self._conn(), self.league_id, week)

    def get_team_dossier(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        """Get team profile, standings, and recent games.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week for standings (defaults to current week).

        See queries.team.get_team_dossier for full return structure.
        """
        return get_team_dossier(self._conn(), self.league_id, roster_key, week)

    def get_team_schedule(self, roster_key: Any) -> dict[str, Any]:
        """Get full season schedule with game-by-game results.

        Args:
            roster_key: Team name, manager name, or roster_id.

        See queries.team.get_team_schedule for full return structure.
        """
        return get_team_schedule(self._conn(), self.league_id, roster_key)

    def get_week_games(self, week: int | None = None) -> list[dict[str, Any]]:
        """Get all matchup games for a week with scores and winners.

        Args:
            week: Week number (defaults to current week).

        See queries.league.get_week_games for full return structure.
        """
        conn = self._conn()
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return []
        return get_week_games(conn, self.league_id, int(effective_week))

    def get_week_games_with_players(
        self, week: int | None = None
    ) -> list[dict[str, Any]]:
        """Get all matchup games for a week with player-by-player breakdowns.

        Args:
            week: Week number (defaults to current week).

        See queries.league.get_week_games_with_players for full return structure.
        """
        conn = self._conn()
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return []
        return get_week_games_with_players(
            conn, self.league_id, int(effective_week)
        )

    def get_team_game(self, roster_key: Any, week: int | None = None) -> dict[str, Any]:
        """Get a specific team's game for a week.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week number (defaults to current week).

        See queries.league.get_team_game for full return structure.
        """
        conn = self._conn()
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return {"found": False, "roster_key": roster_key}
        return get_team_game(conn, self.league_id, int(effective_week), roster_key)

    def get_team_game_with_players(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        """Get a specific team's game for a week with player breakdowns.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week number (defaults to current week).

        See queries.league.get_team_game_with_players for full return structure.
        """
        conn = self._conn()
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return {"found": False, "roster_key": roster_key}
        return get_team_game_with_players(
            conn, self.league_id, int(effective_week), roster_key
        )

    def get_week_player_leaderboard(
        self, week: int | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get top-scoring players for a week, ranked by points.

        Args:
            week: Week number (defaults to current week).
            limit: Maximum players to return (default 10).

        See queries.league.get_week_player_leaderboard for full return structure.
        """
        conn = self._conn()
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return []
        return get_week_player_leaderboard(
            conn, self.league_id, int(effective_week), limit=limit
        )

    def get_season_leaders(
        self,
        *,
        week_from: int | None = None,
        week_to: int | None = None,
        position: str | None = None,
        roster_key: Any = None,
        role: str | None = None,
        sort_by: str = "total",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get top players for the season ranked by total or average points.

        Args:
            week_from: Starting week (inclusive). Omit for full season.
            week_to: Ending week (inclusive). Omit for full season.
            position: Filter to a single position (e.g., "QB", "RB").
            roster_key: Filter to one team's players.
            role: Filter by role — "starter" to exclude bench performances.
            sort_by: "total" (default) or "avg" for average per game.
            limit: Maximum results (default 10, hard cap 30).

        See queries.league.get_season_leaders for full return structure.
        """
        return get_season_leaders(
            self._conn(),
            self.league_id,
            week_from=week_from,
            week_to=week_to,
            position=position,
            roster_key=roster_key,
            role=role,
            sort_by=sort_by,
            limit=limit,
        )

    def get_transactions(self, week_from: int, week_to: int) -> list[dict[str, Any]]:
        """Get all trades, waivers, and FA pickups in a week range.

        Args:
            week_from: Starting week (inclusive).
            week_to: Ending week (inclusive).

        See queries.transactions.get_transactions for full return structure.
        """
        return query_get_transactions(
            self._conn(), self.league_id, week_from, week_to
        )

    def get_team_transactions(
        self, roster_key: Any, week_from: int, week_to: int
    ) -> dict[str, Any]:
        """Get a specific team's transactions in a week range.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week_from: Starting week (inclusive).
            week_to: Ending week (inclusive).

        See queries.transactions.get_team_transactions for full return structure.
        """
        return get_team_transactions(
            self._conn(), self.league_id, week_from, week_to, roster_key
        )

    def get_week_transactions(self, week: int | None = None) -> list[dict[str, Any]]:
        """Get all trades, waivers, and FA pickups for a single week.

        Args:
            week: Week number (defaults to current week).

        See queries.transactions.get_transactions for full return structure.
        """
        conn = self._conn()
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return []
        return query_get_transactions(
            conn, self.league_id, effective_week, effective_week
        )

    def get_team_week_transactions(
        self,
        roster_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
    ) -> dict[str, Any]:
        """Get a specific team's transactions for a week or week range.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week_from: Starting week (inclusive). Defaults to current week.
            week_to: Ending week (inclusive). Defaults to week_from.

        See queries.transactions.get_team_transactions for full return structure.
        """
        conn = self._conn()
        if week_from is not None:
            resolved_from = week_from
            resolved_to = week_to if week_to is not None else week_from
        else:
            effective_week = self._get_effective_week()
            if effective_week is None:
                return {"found": False, "error": "No effective week"}
            resolved_from = effective_week
            resolved_to = week_to if week_to is not None else effective_week
        return get_team_transactions(
            conn, self.league_id, resolved_from, resolved_to, roster_key
        )

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        """Get basic metadata about an NFL player.

        Args:
            player_key: Player name or player_id.

        See queries.player.get_player_summary for full return structure.
        """
        return get_player_summary(self._conn(), player_key)

    def get_player_weekly_log(
        self,
        player_key: Any,
        week_from: int | None = None,
        week_to: int | None = None,
    ) -> dict[str, Any]:
        """Get a player's fantasy performance log, optionally filtered to a week range.

        Args:
            player_key: Player name or player_id.
            week_from: Starting week (inclusive). Omit for full season.
            week_to: Ending week (inclusive). Omit for full season.

        See queries.player.get_player_weekly_log for full return structure.
        """
        return get_player_weekly_log(
            self._conn(),
            self.league_id,
            player_key,
            week_from=week_from,
            week_to=week_to,
        )

    def get_roster_current(self, roster_key: Any) -> dict[str, Any]:
        """Get a team's current roster organized by position.

        When week_override is set, returns the roster as it was during the
        override week (via player_performances) instead of the current API
        snapshot, to avoid leaking future trades and roster moves.

        Args:
            roster_key: Team name, manager name, or roster_id.

        See queries.team.get_roster_current for full return structure.
        """
        conn = self._conn()
        if self.week_override is not None and self.effective_week is not None:
            return get_roster_snapshot(
                conn, self.league_id, roster_key, self.effective_week
            )
        return get_roster_current(conn, self.league_id, roster_key)

    def get_roster_snapshot(self, roster_key: Any, week: int) -> dict[str, Any]:
        """Get a team's roster as it was during a specific week.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: The week number to query.

        See queries.team.get_roster_snapshot for full return structure.
        """
        return get_roster_snapshot(
            self._conn(), self.league_id, roster_key, week
        )

    def run_sql(
        self,
        query: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Execute a custom SELECT query for advanced analysis.

        Args:
            query: A SELECT SQL query (write operations are blocked).
            params: Named parameters for the query.
            limit: Maximum rows to return (default 200).

        See queries.sql_tool.run_sql for full documentation and table list.
        """
        return run_sql(self._conn(), query, params, limit=limit)

    def get_playoff_bracket(self, bracket_type: str | None = None) -> dict[str, Any]:
        """Get the playoff bracket structure with team names and results.

        Args:
            bracket_type: "winners" or "losers". If None, returns both brackets.

        See queries.playoffs.get_playoff_bracket for full return structure.
        """
        return query_get_playoff_bracket(
            self._conn(), self.league_id, bracket_type
        )

    def get_team_playoff_path(self, roster_key: Any) -> dict[str, Any]:
        """Get a specific team's playoff bracket journey.

        Args:
            roster_key: Team name, manager name, or roster_id.

        See queries.playoffs.get_team_playoff_path for full return structure.
        """
        return query_get_team_playoff_path(
            self._conn(), self.league_id, roster_key
        )
