"""Adapters for Sleeper datalayer tools with automatic research logging."""

from __future__ import annotations

from typing import Any, Callable, Optional

from datalayer.sleeper_data import SleeperLeagueData

from agent.research_log import ResearchLog


class ResearchToolAdapter:
    """Adapts datalayer methods for the reporter agent with automatic logging.

    Tool calls are logged automatically via middleware hooks. This adapter
    focuses on executing data retrieval and logging the tool start with params.
    """

    def __init__(
        self,
        data: SleeperLeagueData,
        *,
        research_log: Optional[ResearchLog] = None,
    ):
        self.data = data
        # Use provided log or create a new one
        self.log = research_log or ResearchLog()
        self._handlers = self._build_handlers()

    def _build_handlers(self) -> dict[str, Callable[..., Any]]:
        """Map tool names to datalayer methods."""
        return {
            "get_league_snapshot": self.data.get_league_snapshot,
            "get_week_games": self.data.get_week_games,
            "get_week_games_with_players": self.data.get_week_games_with_players,
            "get_week_player_leaderboard": self.data.get_week_player_leaderboard,
            "get_transactions": self.data.get_transactions,
            "get_team_dossier": self.data.get_team_dossier,
            "get_team_game": self.data.get_team_game,
            "get_team_game_with_players": self.data.get_team_game_with_players,
            "get_team_schedule": self.data.get_team_schedule,
            "get_roster_current": self.data.get_roster_current,
            "get_roster_snapshot": self.data.get_roster_snapshot,
            "get_team_transactions": self.data.get_team_transactions,
            "get_player_summary": self.data.get_player_summary,
            "get_player_weekly_log": self.data.get_player_weekly_log,
            "get_player_weekly_log_range": self.data.get_player_weekly_log_range,
            "run_sql": self.data.run_sql,
        }

    @property
    def available_tools(self) -> list[str]:
        """List of available tool names."""
        return list(self._handlers.keys())

    def call(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a data retrieval tool.

        Logs the tool start with parameters. The tool end (with result and timing)
        is logged by the ResearchLoggingHooks middleware.
        """
        if tool_name not in self._handlers:
            return {
                "found": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": self.available_tools,
            }

        # Log tool start with params
        self.log.add_tool_start(tool_name=tool_name, tool_params=kwargs)

        # Execute the tool
        handler = self._handlers[tool_name]
        return handler(**kwargs)

    def get_research_log(self) -> ResearchLog:
        """Return the complete research log."""
        return self.log


# Keep the old name as an alias for backwards compatibility
SleeperToolAdapter = ResearchToolAdapter


# Tool documentation for agent prompts
TOOL_DOCS = """
## Available Data Tools

### League-Wide Context

- **get_league_snapshot(week?)**: Standings, games, and transactions for a week.
  Returns comprehensive league state including standings, all matchups, and transaction activity.
  This is your best starting point to understand the week.

- **get_week_games(week?)**: All matchups with scores and winners.
  Returns list of games with team names, scores, and win/loss indicators.

- **get_week_games_with_players(week?)**: Matchups with player-by-player breakdown.
  Detailed view showing which players scored what for each team.

- **get_week_player_leaderboard(week?, limit?)**: Top scorers ranked by points.
  Get the highest-scoring players across all teams.

- **get_transactions(week_from, week_to)**: Trades, waivers, and FA pickups.
  All roster moves in the specified week range.

### Team-Specific

- **get_team_dossier(roster_key, week?)**: Profile, standings, and recent games.
  Comprehensive team overview including record, streak, and recent matchups.

- **get_team_game(roster_key, week?)**: Specific team's matchup result.
  Single game details for one team.

- **get_team_game_with_players(roster_key, week?)**: Team matchup with player details.
  Game result plus player-by-player scoring breakdown.

- **get_team_schedule(roster_key)**: Full season schedule with W/L/T.
  Complete game-by-game results for the season.

- **get_roster_current(roster_key)**: Current roster by position.
  Active roster organized by starter/bench slots.

- **get_roster_snapshot(roster_key, week)**: Historical roster for specific week.
  What the roster looked like during a past week.

- **get_team_transactions(roster_key, week_from, week_to)**: Team's transaction history.
  All roster moves for a specific team.

### Player-Specific

- **get_player_summary(player_key)**: Metadata (position, team, status, injury).
  Basic player information.

- **get_player_weekly_log(player_key)**: Full season performance log.
  Week-by-week fantasy points for the entire season.

- **get_player_weekly_log_range(player_key, week_from, week_to)**: Performance for week range.
  Player stats for a specific week range.

### Escape Hatch

- **run_sql(query, limit?)**: Custom SELECT query (writes blocked).
  For complex queries not covered by other tools.

## Parameter Notes

- **roster_key**: Accepts team name, manager name, or roster_id
- **player_key**: Accepts player name or player_id
- **week**: Defaults to current week if not specified
"""
