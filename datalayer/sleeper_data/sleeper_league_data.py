"""Facade for loading Sleeper league data into SQLite."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .config import SleeperConfig, load_config
from .normalize import (
    apply_traded_picks,
    derive_games,
    derive_team_profiles,
    normalize_bracket,
    normalize_league,
    normalize_matchups,
    normalize_players,
    normalize_roster_players,
    normalize_rosters,
    normalize_standings,
    normalize_transaction_moves,
    normalize_transactions,
    normalize_users,
    seed_draft_picks,
)
from .schema.models import SeasonContext, StandingsWeek
from .sleeper_api import (
    SleeperClient,
    get_league,
    get_league_rosters,
    get_league_users,
    get_losers_bracket,
    get_matchups,
    get_players,
    get_state,
    get_traded_picks,
    get_transactions as api_get_transactions,
    get_winners_bracket,
)
from .store.sqlite_store import bulk_insert, create_tables
from .queries import (
    get_bench_analysis,
    get_league_snapshot,
    get_player_summary,
    get_player_weekly_log,
    get_player_weekly_log_range,
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
        self.conn: Optional[sqlite3.Connection] = None
        self.effective_week: Optional[int] = None

    def load(self) -> None:
        # check_same_thread=False allows the connection to be used from
        # different threads (needed for async agent tool calls)
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        create_tables(self.conn)

        raw_league = get_league(self.league_id, client=self.client)
        raw_users = get_league_users(self.league_id, client=self.client)
        raw_rosters = get_league_rosters(self.league_id, client=self.client)
        raw_state = get_state("nfl", client=self.client)

        league = normalize_league(raw_league)
        users = normalize_users(raw_users)
        rosters = normalize_rosters(raw_rosters, league_id=self.league_id)
        roster_players = normalize_roster_players(raw_rosters, league_id=self.league_id)
        team_profiles = derive_team_profiles(
            raw_rosters, raw_users, league_id=self.league_id
        )

        bulk_insert(self.conn, league.table_name, [league])
        if users:
            bulk_insert(self.conn, users[0].table_name, users)
        if rosters:
            bulk_insert(self.conn, rosters[0].table_name, rosters)
        if team_profiles:
            bulk_insert(self.conn, team_profiles[0].table_name, team_profiles)

        draft_rounds = int((raw_league.get("settings") or {}).get("draft_rounds") or 0)
        draft_picks = seed_draft_picks(
            rosters, self.league_id, league.season, draft_rounds
        )
        if draft_picks:
            bulk_insert(self.conn, draft_picks[0].table_name, draft_picks)

        raw_traded_picks = get_traded_picks(self.league_id, client=self.client)
        apply_traded_picks(self.conn, raw_traded_picks, self.league_id)

        raw_players = get_players("nfl", client=self.client)
        players = normalize_players(raw_players)
        if players:
            bulk_insert(self.conn, players[0].table_name, players)
        if roster_players:
            bulk_insert(self.conn, roster_players[0].table_name, roster_players)

        computed_week = int(raw_state.get("week") or 0)
        effective_week = int(self.week_override or computed_week or 0)
        season = str(raw_league.get("season") or raw_state.get("season") or "")
        league_average_match = (
            int((raw_league.get("settings") or {}).get("league_average_match") or 0)
            if raw_league.get("settings") is not None
            else 0
        )
        chars_per_week = 2 if league_average_match == 1 else 1

        playoff_week_start = (
            int(league.playoff_week_start)
            if league.playoff_week_start is not None
            else None
        )

        def _record_string_to_weeks(
            record_string: str | None,
        ) -> list[tuple[int, int, int, int]]:
            if not record_string:
                return []
            trimmed = "".join(ch for ch in record_string.strip().upper() if ch.strip())
            if not trimmed:
                return []
            week_count = len(trimmed) // chars_per_week
            results: list[tuple[int, int, int, int]] = []
            wins = 0
            losses = 0
            ties = 0
            for week in range(1, week_count + 1):
                end_idx = week * chars_per_week
                slice_value = trimmed[end_idx - chars_per_week : end_idx]
                for outcome in slice_value:
                    if outcome == "W":
                        wins += 1
                    elif outcome == "L":
                        losses += 1
                    elif outcome == "T":
                        ties += 1
                results.append((week, wins, losses, ties))
            return results

        self.effective_week = effective_week
        if effective_week > 0:
            for week in range(1, effective_week + 1):
                raw_matchups = get_matchups(self.league_id, week, client=self.client)
                matchup_rows, player_performances = normalize_matchups(
                    raw_matchups, league_id=self.league_id, season=season, week=week
                )
                is_playoffs = playoff_week_start is not None and week >= int(
                    playoff_week_start
                )
                games = derive_games(matchup_rows, is_playoffs=is_playoffs)
                if matchup_rows:
                    bulk_insert(self.conn, matchup_rows[0].table_name, matchup_rows)
                if player_performances:
                    bulk_insert(
                        self.conn,
                        player_performances[0].table_name,
                        player_performances,
                    )
                if games:
                    bulk_insert(self.conn, games[0].table_name, games)

                raw_transactions = api_get_transactions(
                    self.league_id, week, client=self.client
                )
                transactions = normalize_transactions(
                    raw_transactions, league_id=self.league_id, season=season, week=week
                )
                moves = normalize_transaction_moves(raw_transactions)
                if transactions:
                    bulk_insert(self.conn, transactions[0].table_name, transactions)
                if moves:
                    bulk_insert(self.conn, moves[0].table_name, moves)

            record_standings: list[StandingsWeek] = []
            record_weeks: set[int] = set()

            for raw_roster in raw_rosters:
                roster_id = int(raw_roster["roster_id"])
                record_string = (raw_roster.get("metadata") or {}).get("record")
                if isinstance(record_string, list):
                    record_string = "".join(str(item) for item in record_string if item)
                if isinstance(record_string, str):
                    for week, wins, losses, ties in _record_string_to_weeks(
                        record_string
                    ):
                        if (
                            playoff_week_start is not None
                            and week >= playoff_week_start
                        ):
                            continue
                        record_standings.append(
                            StandingsWeek(
                                league_id=self.league_id,
                                season=season,
                                week=int(week),
                                roster_id=roster_id,
                                wins=wins,
                                losses=losses,
                                ties=ties,
                                points_for=0.0,
                                points_against=0.0,
                                rank=None,
                                streak_type=None,
                                streak_len=None,
                            )
                        )
                        record_weeks.add(int(week))

            if record_standings:
                bulk_insert(
                    self.conn,
                    record_standings[0].table_name,
                    record_standings,
                )

            should_insert_current = False
            if not record_weeks:
                should_insert_current = True
            elif effective_week > max(record_weeks):
                if playoff_week_start is None or effective_week < playoff_week_start:
                    should_insert_current = True

            if should_insert_current:
                standings = normalize_standings(
                    raw_rosters,
                    league_id=self.league_id,
                    season=season,
                    week=effective_week,
                )
                if standings:
                    bulk_insert(self.conn, standings[0].table_name, standings)

        raw_winners = get_winners_bracket(self.league_id, client=self.client)
        raw_losers = get_losers_bracket(self.league_id, client=self.client)
        winners = normalize_bracket(
            raw_winners, league_id=self.league_id, season=season, bracket_type="winners"
        )
        losers = normalize_bracket(
            raw_losers, league_id=self.league_id, season=season, bracket_type="losers"
        )
        if winners:
            bulk_insert(self.conn, winners[0].table_name, winners)
        if losers:
            bulk_insert(self.conn, losers[0].table_name, losers)

        season_context = SeasonContext(
            league_id=self.league_id,
            computed_week=computed_week,
            override_week=self.week_override,
            effective_week=effective_week,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        bulk_insert(self.conn, season_context.table_name, [season_context])

    def save_to_file(self, output_path: str) -> str:
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before saving.")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        file_conn = sqlite3.connect(output_path)
        try:
            self.conn.backup(file_conn)
            file_conn.commit()
        finally:
            file_conn.close()

        return output_path

    def get_league_snapshot(self, week: int | None = None) -> dict[str, Any]:
        """Get league standings, games, and transactions for a week.

        See queries.defaults.get_league_snapshot for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_league_snapshot(self.conn, week)

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
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            if roster_key is not None:
                return {"found": False, "roster_key": roster_key}
            return []
        return get_bench_analysis(
            self.conn, self.league_id, int(effective_week), roster_key
        )

    def get_standings(self, week: int | None = None) -> dict[str, Any]:
        """Get league standings for a specific week.

        Args:
            week: Week number (defaults to current week).

        See queries.league.get_standings for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_standings(self.conn, self.league_id, week)

    def get_team_dossier(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        """Get team profile, standings, and recent games.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week for standings (defaults to current week).

        See queries.defaults.get_team_dossier for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_team_dossier(self.conn, self.league_id, roster_key, week)

    def get_team_schedule(self, roster_key: Any) -> dict[str, Any]:
        """Get full season schedule with game-by-game results.

        Args:
            roster_key: Team name, manager name, or roster_id.

        See queries.defaults.get_team_schedule for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_team_schedule(self.conn, self.league_id, roster_key)

    def _get_effective_week(self, week: int | None = None) -> int | None:
        """Get effective week, defaulting to current week if not specified."""
        if week is not None:
            return week
        if not self.conn:
            return None
        context = self.conn.execute(
            "SELECT effective_week FROM season_context LIMIT 1"
        ).fetchone()
        return context[0] if context else None

    def get_week_games(self, week: int | None = None) -> list[dict[str, Any]]:
        """Get all matchup games for a week with scores and winners.

        Args:
            week: Week number (defaults to current week).

        See queries.league.get_week_games for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return []
        return get_week_games(self.conn, self.league_id, int(effective_week))

    def get_week_games_with_players(
        self, week: int | None = None
    ) -> list[dict[str, Any]]:
        """Get all matchup games for a week with player-by-player breakdowns.

        Args:
            week: Week number (defaults to current week).

        See queries.league.get_week_games_with_players for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return []
        return get_week_games_with_players(
            self.conn, self.league_id, int(effective_week)
        )

    def get_team_game(self, roster_key: Any, week: int | None = None) -> dict[str, Any]:
        """Get a specific team's game for a week.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week number (defaults to current week).

        See queries.league.get_team_game for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return {"found": False, "roster_key": roster_key}
        return get_team_game(self.conn, self.league_id, int(effective_week), roster_key)

    def get_team_game_with_players(
        self, roster_key: Any, week: int | None = None
    ) -> dict[str, Any]:
        """Get a specific team's game for a week with player breakdowns.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week number (defaults to current week).

        See queries.league.get_team_game_with_players for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return {"found": False, "roster_key": roster_key}
        return get_team_game_with_players(
            self.conn, self.league_id, int(effective_week), roster_key
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
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return []
        return get_week_player_leaderboard(
            self.conn, self.league_id, int(effective_week), limit=limit
        )

    def get_transactions(self, week_from: int, week_to: int) -> list[dict[str, Any]]:
        """Get all trades, waivers, and FA pickups in a week range.

        Args:
            week_from: Starting week (inclusive).
            week_to: Ending week (inclusive).

        See queries.transactions.get_transactions for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return query_get_transactions(self.conn, self.league_id, week_from, week_to)

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
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_team_transactions(
            self.conn, self.league_id, week_from, week_to, roster_key
        )

    def get_week_transactions(self, week: int | None = None) -> list[dict[str, Any]]:
        """Get all trades, waivers, and FA pickups for a single week.

        Args:
            week: Week number (defaults to current week).

        See queries.transactions.get_transactions for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        effective_week = self._get_effective_week(week)
        if effective_week is None:
            return []
        return query_get_transactions(
            self.conn, self.league_id, effective_week, effective_week
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
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
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
            self.conn, self.league_id, resolved_from, resolved_to, roster_key
        )

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        """Get basic metadata about an NFL player.

        Args:
            player_key: Player name or player_id.

        See queries.defaults.get_player_summary for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_player_summary(self.conn, player_key)

    def get_player_weekly_log(self, player_key: Any) -> dict[str, Any]:
        """Get a player's full season fantasy performance log.

        Args:
            player_key: Player name or player_id.

        See queries.player.get_player_weekly_log for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_player_weekly_log(self.conn, self.league_id, player_key)

    def get_player_weekly_log_range(
        self, player_key: Any, week_from: int, week_to: int
    ) -> dict[str, Any]:
        """Get a player's fantasy performance log for a specific week range.

        Args:
            player_key: Player name or player_id.
            week_from: Starting week (inclusive).
            week_to: Ending week (inclusive).

        See queries.player.get_player_weekly_log_range for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_player_weekly_log_range(
            self.conn, self.league_id, player_key, week_from, week_to
        )

    def get_roster_current(self, roster_key: Any) -> dict[str, Any]:
        """Get a team's current roster organized by position.

        Args:
            roster_key: Team name, manager name, or roster_id.

        See queries.defaults.get_roster_current for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_roster_current(self.conn, self.league_id, roster_key)

    def get_roster_snapshot(self, roster_key: Any, week: int) -> dict[str, Any]:
        """Get a team's roster as it was during a specific week.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: The week number to query.

        See queries.defaults.get_roster_snapshot for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return get_roster_snapshot(self.conn, self.league_id, roster_key, week)

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
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return run_sql(self.conn, query, params, limit=limit)

    def get_playoff_bracket(self, bracket_type: str | None = None) -> dict[str, Any]:
        """Get the playoff bracket structure with team names and results.

        Args:
            bracket_type: "winners" or "losers". If None, returns both brackets.

        See queries.playoffs.get_playoff_bracket for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return query_get_playoff_bracket(self.conn, self.league_id, bracket_type)

    def get_team_playoff_path(self, roster_key: Any) -> dict[str, Any]:
        """Get a specific team's playoff bracket journey.

        Args:
            roster_key: Team name, manager name, or roster_id.

        See queries.playoffs.get_team_playoff_path for full return structure.
        """
        if not self.conn:
            raise RuntimeError("Data not loaded. Call load() before querying.")
        return query_get_team_playoff_path(self.conn, self.league_id, roster_key)
