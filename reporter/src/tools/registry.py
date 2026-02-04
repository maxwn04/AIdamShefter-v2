"""Tool registry for the reporter agent."""

from __future__ import annotations

from typing import Any, Callable

from agents import function_tool

from tools.sleeper_tools import SleeperToolAdapter


def create_tool_registry(adapter: SleeperToolAdapter) -> list[Callable]:
    """Create OpenAI Agents SDK tools from the SleeperToolAdapter.

    Uses the @function_tool decorator pattern for proper schema generation.
    """

    @function_tool
    def get_league_snapshot(week: int | None = None) -> dict[str, Any]:
        """Get league standings, games, and transactions for a week.

        Args:
            week: Week number (defaults to current week).

        Returns comprehensive league state for the specified week.
        """
        return adapter.call("get_league_snapshot", week=week)

    @function_tool
    def get_week_games(week: int | None = None) -> list[dict[str, Any]]:
        """Get all matchup games for a week with scores and winners.

        Args:
            week: Week number (defaults to current week).
        """
        return adapter.call("get_week_games", week=week)

    @function_tool
    def get_week_games_with_players(week: int | None = None) -> list[dict[str, Any]]:
        """Get all matchup games with player-by-player breakdowns.

        Args:
            week: Week number (defaults to current week).
        """
        return adapter.call("get_week_games_with_players", week=week)

    @function_tool
    def get_week_player_leaderboard(
        week: int | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get top-scoring players for a week, ranked by points.

        Args:
            week: Week number (defaults to current week).
            limit: Maximum players to return (default 10).
        """
        return adapter.call("get_week_player_leaderboard", week=week, limit=limit)

    @function_tool
    def get_transactions(week_from: int, week_to: int) -> list[dict[str, Any]]:
        """Get all trades, waivers, and FA pickups in a week range.

        Args:
            week_from: Starting week (inclusive).
            week_to: Ending week (inclusive).
        """
        return adapter.call("get_transactions", week_from=week_from, week_to=week_to)

    @function_tool
    def get_team_dossier(
        roster_key: str, week: int | None = None
    ) -> dict[str, Any]:
        """Get team profile, standings, and recent games.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week for standings context (defaults to current).
        """
        return adapter.call("get_team_dossier", roster_key=roster_key, week=week)

    @function_tool
    def get_team_game(roster_key: str, week: int | None = None) -> dict[str, Any]:
        """Get a specific team's game result for a week.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week number (defaults to current week).
        """
        return adapter.call("get_team_game", roster_key=roster_key, week=week)

    @function_tool
    def get_team_game_with_players(
        roster_key: str, week: int | None = None
    ) -> dict[str, Any]:
        """Get a team's game with player-by-player breakdown.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week number (defaults to current week).
        """
        return adapter.call(
            "get_team_game_with_players", roster_key=roster_key, week=week
        )

    @function_tool
    def get_team_schedule(roster_key: str) -> dict[str, Any]:
        """Get a team's full season schedule with game-by-game results.

        Args:
            roster_key: Team name, manager name, or roster_id.
        """
        return adapter.call("get_team_schedule", roster_key=roster_key)

    @function_tool
    def get_roster_current(roster_key: str) -> dict[str, Any]:
        """Get a team's current roster organized by position.

        Args:
            roster_key: Team name, manager name, or roster_id.
        """
        return adapter.call("get_roster_current", roster_key=roster_key)

    @function_tool
    def get_roster_snapshot(roster_key: str, week: int) -> dict[str, Any]:
        """Get a team's roster as it was during a specific week.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: The week number to query.
        """
        return adapter.call("get_roster_snapshot", roster_key=roster_key, week=week)

    @function_tool
    def get_team_transactions(
        roster_key: str, week_from: int, week_to: int
    ) -> dict[str, Any]:
        """Get a specific team's transactions in a week range.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week_from: Starting week (inclusive).
            week_to: Ending week (inclusive).
        """
        return adapter.call(
            "get_team_transactions",
            roster_key=roster_key,
            week_from=week_from,
            week_to=week_to,
        )

    @function_tool
    def get_player_summary(player_key: str) -> dict[str, Any]:
        """Get basic metadata about an NFL player.

        Args:
            player_key: Player name or player_id.
        """
        return adapter.call("get_player_summary", player_key=player_key)

    @function_tool
    def get_player_weekly_log(player_key: str) -> dict[str, Any]:
        """Get a player's full season fantasy performance log.

        Args:
            player_key: Player name or player_id.
        """
        return adapter.call("get_player_weekly_log", player_key=player_key)

    @function_tool
    def get_player_weekly_log_range(
        player_key: str, week_from: int, week_to: int
    ) -> dict[str, Any]:
        """Get a player's fantasy performance for a specific week range.

        Args:
            player_key: Player name or player_id.
            week_from: Starting week (inclusive).
            week_to: Ending week (inclusive).
        """
        return adapter.call(
            "get_player_weekly_log_range",
            player_key=player_key,
            week_from=week_from,
            week_to=week_to,
        )

    @function_tool
    def run_sql(query: str, limit: int = 200) -> dict[str, Any]:
        """Execute a custom SELECT query for advanced analysis.

        Args:
            query: A SELECT SQL query (write operations are blocked).
            limit: Maximum rows to return (default 200).

        Use this for complex queries not covered by other tools.
        """
        return adapter.call("run_sql", query=query, limit=limit)

    # Return the decorated tools
    return [
        get_league_snapshot,
        get_week_games,
        get_week_games_with_players,
        get_week_player_leaderboard,
        get_transactions,
        get_team_dossier,
        get_team_game,
        get_team_game_with_players,
        get_team_schedule,
        get_roster_current,
        get_roster_snapshot,
        get_team_transactions,
        get_player_summary,
        get_player_weekly_log,
        get_player_weekly_log_range,
        run_sql,
    ]
