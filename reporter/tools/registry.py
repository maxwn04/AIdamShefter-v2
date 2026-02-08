"""Tool registry for the reporter agent."""

from __future__ import annotations

from typing import Any, Callable

from agents import function_tool

from reporter.tools.sleeper_tools import ResearchToolAdapter


def create_tool_registry(adapter: ResearchToolAdapter) -> list[Callable]:
    """Create OpenAI Agents SDK tools from the ResearchToolAdapter.

    All tool calls are automatically logged via middleware.
    """

    # ==========================================================================
    # DATA RETRIEVAL TOOLS
    # ==========================================================================

    @function_tool
    def get_league_snapshot(week: int | None = None) -> dict[str, Any]:
        """Get league standings, games, and transactions for a week.

        This is typically your FIRST call—gives you broad context to identify
        what's interesting. Returns comprehensive league state including
        standings, all matchups, and transaction activity.

        Args:
            week: Week number (defaults to current week).
        """
        return adapter.call("get_league_snapshot", week=week)

    @function_tool
    def get_week_games(week: int | None = None) -> list[dict[str, Any]]:
        """Get all matchup games for a week with scores and winners.

        Use this to see all game results at a glance. Good for identifying
        upsets, blowouts, and close games.

        Args:
            week: Week number (defaults to current week).
        """
        return adapter.call("get_week_games", week=week)

    @function_tool
    def get_week_games_with_players(week: int | None = None) -> list[dict[str, Any]]:
        """Get all matchup games with player-by-player breakdowns.

        Detailed view showing which players scored what for each team.
        Use when you need to identify standout performers across all games.

        Args:
            week: Week number (defaults to current week).
        """
        return adapter.call("get_week_games_with_players", week=week)

    @function_tool
    def get_week_player_leaderboard(
        week: int | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get top-scoring players for a week, ranked by points.

        Great for finding the week's best performers for a "top performers"
        section or identifying breakout games.

        Args:
            week: Week number (defaults to current week).
            limit: Maximum players to return (default 10, max 25).
        """
        # Cap limit to prevent huge outputs
        capped_limit = min(limit, 25)
        return adapter.call("get_week_player_leaderboard", week=week, limit=capped_limit)

    @function_tool
    def get_week_transactions(week: int | None = None) -> list[dict[str, Any]]:
        """Get all trades, waivers, and FA pickups for a single week.

        Use to find transaction storylines—big trades, waiver wire finds,
        questionable moves.

        Args:
            week: Week number (defaults to current week).
        """
        return adapter.call("get_week_transactions", week=week)

    @function_tool
    def get_team_dossier(
        roster_key: str, week: int | None = None
    ) -> dict[str, Any]:
        """Get team profile, standings, and recent games.

        Comprehensive team overview—use when you want to understand a team's
        situation in depth. Includes record, streak, and recent matchups.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: Week for standings context (defaults to current).
        """
        return adapter.call("get_team_dossier", roster_key=roster_key, week=week)

    @function_tool
    def get_team_game(roster_key: str, week: int | None = None) -> dict[str, Any]:
        """Get a specific team's game result for a week.

        Use when you want to focus on one side of a matchup.

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

        Use when investigating WHY a team won or lost—see which players
        carried or tanked.

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

        Use for analyzing season arcs, streaks, and trends over time.

        Args:
            roster_key: Team name, manager name, or roster_id.
        """
        return adapter.call("get_team_schedule", roster_key=roster_key)

    @function_tool
    def get_roster_current(roster_key: str) -> dict[str, Any]:
        """Get a team's current roster organized by position.

        Use for roster composition analysis—who's starting, who's on bench.

        Args:
            roster_key: Team name, manager name, or roster_id.
        """
        return adapter.call("get_roster_current", roster_key=roster_key)

    @function_tool
    def get_roster_snapshot(roster_key: str, week: int) -> dict[str, Any]:
        """Get a team's roster as it was during a specific week.

        Use for historical roster analysis—what did the roster look like
        when they won/lost that key game?

        Args:
            roster_key: Team name, manager name, or roster_id.
            week: The week number to query.
        """
        return adapter.call("get_roster_snapshot", roster_key=roster_key, week=week)

    @function_tool
    def get_team_week_transactions(
        roster_key: str,
        week_from: int | None = None,
        week_to: int | None = None,
    ) -> dict[str, Any]:
        """Get a specific team's transactions for a week or week range.

        Use for team-focused transaction analysis—what moves did this
        team make? Defaults to current week if no range specified.

        Args:
            roster_key: Team name, manager name, or roster_id.
            week_from: Starting week (inclusive). Defaults to current week.
            week_to: Ending week (inclusive). Defaults to week_from.
        """
        return adapter.call(
            "get_team_week_transactions",
            roster_key=roster_key,
            week_from=week_from,
            week_to=week_to,
        )

    @function_tool
    def get_bench_analysis(
        roster_key: str | None = None, week: int | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Get starter vs bench scoring breakdown for a week.

        League-wide mode (no roster_key): every team's starter/bench totals
        sorted by bench points. Team-specific mode: adds individual bench
        player details.

        Args:
            roster_key: Optional team name, manager name, or roster_id.
            week: Week number (defaults to current week).
        """
        return adapter.call(
            "get_bench_analysis", roster_key=roster_key, week=week
        )

    @function_tool
    def get_standings(week: int | None = None) -> dict[str, Any]:
        """Get league standings for a specific week.

        Returns standings with records, points, ranks, streaks, and whether
        league_average_match is enabled. More focused than get_league_snapshot
        when you only need standings.

        Args:
            week: Week number (defaults to current week).
        """
        return adapter.call("get_standings", week=week)

    @function_tool
    def get_player_summary(player_key: str) -> dict[str, Any]:
        """Get basic metadata about an NFL player.

        Use for quick player info—position, NFL team, injury status.

        Args:
            player_key: Player name or player_id.
        """
        return adapter.call("get_player_summary", player_key=player_key)

    @function_tool
    def get_player_weekly_log(player_key: str) -> dict[str, Any]:
        """Get a player's full season fantasy performance log.

        Use for analyzing player consistency, trends, or finding their
        best/worst weeks.

        Args:
            player_key: Player name or player_id.
        """
        return adapter.call("get_player_weekly_log", player_key=player_key)

    @function_tool
    def get_player_weekly_log_range(
        player_key: str, week_from: int, week_to: int
    ) -> dict[str, Any]:
        """Get a player's fantasy performance for a specific week range.

        Use for focused player analysis over a particular stretch.

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
    def get_playoff_bracket(
        bracket_type: str | None = None,
    ) -> dict[str, Any]:
        """Get the playoff bracket structure with team names and results.

        Shows winners and/or losers bracket organized by round. Includes
        champion and placement information when available.

        Args:
            bracket_type: "winners" or "losers". Omit to get both brackets.
        """
        return adapter.call("get_playoff_bracket", bracket_type=bracket_type)

    @function_tool
    def get_team_playoff_path(roster_key: str) -> dict[str, Any]:
        """Get a specific team's playoff bracket journey.

        Shows each matchup with opponent, result (win/loss/pending), and
        final placement. Indicates if the team is eliminated or is champion.

        Args:
            roster_key: Team name, manager name, or roster_id.
        """
        return adapter.call("get_team_playoff_path", roster_key=roster_key)

    @function_tool
    def run_sql(query: str, limit: int = 200) -> dict[str, Any]:
        """Execute a custom SELECT query for advanced analysis.

        Use this escape hatch for complex queries not covered by other tools.
        Write operations (INSERT, UPDATE, DELETE) are blocked.

        Args:
            query: A SELECT SQL query.
            limit: Maximum rows to return (default 200).
        """
        return adapter.call("run_sql", query=query, limit=limit)

    # Return all data retrieval tools
    return [
        get_league_snapshot,
        get_standings,
        get_week_games,
        get_week_games_with_players,
        get_week_player_leaderboard,
        get_bench_analysis,
        get_week_transactions,
        get_team_dossier,
        get_team_game,
        get_team_game_with_players,
        get_team_schedule,
        get_roster_current,
        get_roster_snapshot,
        get_team_week_transactions,
        get_playoff_bracket,
        get_team_playoff_path,
        get_player_summary,
        get_player_weekly_log,
        get_player_weekly_log_range,
        run_sql,
    ]
