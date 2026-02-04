"""Adapters for Sleeper datalayer tools."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from datalayer.sleeper_data import SleeperLeagueData

from agent.schemas import ToolCall


class SleeperToolAdapter:
    """Adapts datalayer methods for the reporter agent with call logging."""

    def __init__(self, data: SleeperLeagueData):
        self.data = data
        self.call_log: list[ToolCall] = []
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
        """Execute a tool with logging for brief construction."""
        if tool_name not in self._handlers:
            return {
                "found": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": self.available_tools,
            }

        handler = self._handlers[tool_name]
        result = handler(**kwargs)

        # Log the call
        self.call_log.append(
            ToolCall(
                tool=tool_name,
                params=kwargs,
                timestamp=datetime.utcnow().isoformat(),
                result_summary=self._summarize_result(result),
            )
        )

        return result

    def _summarize_result(self, result: Any) -> str:
        """Create a brief summary of a tool result."""
        if isinstance(result, dict):
            if "found" in result and not result["found"]:
                return "not found"
            if "data" in result:
                data = result["data"]
                if isinstance(data, list):
                    return f"{len(data)} items"
                return "1 item"
            return "dict result"
        if isinstance(result, list):
            return f"{len(result)} items"
        return str(type(result).__name__)

    def get_data_refs(self) -> list[str]:
        """Return formatted refs for ReportBrief.facts.data_refs."""
        refs = []
        for call in self.call_log:
            params_str = ",".join(f"{k}={v}" for k, v in call.params.items())
            refs.append(f"{call.tool}:{params_str}" if params_str else call.tool)
        return refs

    def clear_log(self) -> None:
        """Clear the call log for a fresh research phase."""
        self.call_log = []


# Tool documentation for agent prompts
TOOL_DOCS = """
## Available Tools

### League-Wide Context

- **get_league_snapshot(week?)**: Standings, games, and transactions for a week.
  Returns comprehensive league state including standings, all matchups, and transaction activity.

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
