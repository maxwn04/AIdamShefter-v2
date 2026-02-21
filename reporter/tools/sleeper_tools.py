"""Adapters for Sleeper datalayer tools with automatic research logging."""

from __future__ import annotations

from typing import Any, Callable, Optional

from datalayer.sleeper_data import SleeperLeagueData

from reporter.agent.research_log import ResearchLog


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
            "league_snapshot": self.data.get_league_snapshot,
            "week_games": self.data.get_week_games_with_players,
            "week_player_leaderboard": self.data.get_week_player_leaderboard,
            "season_leaders": self.data.get_season_leaders,
            "transactions": self.data.get_transactions,
            "team_dossier": self.data.get_team_dossier,
            "team_game": self.data.get_team_game_with_players,
            "team_schedule": self.data.get_team_schedule,
            "roster_current": self.data.get_roster_current,
            "roster_snapshot": self.data.get_roster_snapshot,
            "team_transactions": self.data.get_team_transactions,
            "bench_analysis": self.data.get_bench_analysis,
            "standings": self.data.get_standings,
            "player_summary": self.data.get_player_summary,
            "player_weekly_log": self.data.get_player_weekly_log,
            "playoff_bracket": self.data.get_playoff_bracket,
            "team_playoff_path": self.data.get_team_playoff_path,
            "run_sql": self.data.run_sql,
        }

    @property
    def available_tools(self) -> list[str]:
        """List of available tool names."""
        return list(self._handlers.keys())

    def call(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a data retrieval tool.

        Tool start/end logging is handled by the stream event loop in
        ResearchAgent.research(), not here.
        """
        if tool_name not in self._handlers:
            return {
                "found": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": self.available_tools,
            }

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

- **league_snapshot(week?)**: Standings, games, and transactions for a week.
  Returns comprehensive league state including standings, all matchups, and transaction activity.
  This is your best starting point to understand the week.

- **week_games(week?)**: Matchups with player-by-player breakdown.
  Detailed view showing game results and which players scored what for each team.

- **week_player_leaderboard(week?, limit?)**: Top scorers ranked by points.
  Get the highest-scoring players across all teams.

- **season_leaders(week_from?, week_to?, position?, roster_key?, role?, sort_by?, limit?)**:
  Season-long player rankings by total or average points. Filter by position, team,
  week range, or starter role. Use for MVP candidates and season stat leaders.

- **standings(week?)**: League standings with records, points, ranks, streaks.
  Includes league_average_match flag. More focused than league_snapshot when
  you only need standings.

- **bench_analysis(roster_key?, week?)**: Starter vs bench scoring breakdown.
  League-wide mode shows every team's starter/bench totals. Team-specific mode
  adds individual bench player details.

- **transactions(week_from, week_to)**: Trades, waivers, and FA pickups in a week range.
  All roster moves for the specified weeks. For a single week, pass the same value
  for both week_from and week_to.

### Team-Specific

- **team_dossier(roster_key, week?)**: Profile, standings, and recent games.
  Comprehensive team overview including record, streak, and recent matchups.

- **team_game(roster_key, week?)**: Team matchup with player-by-player details.
  Game result plus player-by-player scoring breakdown.

- **team_schedule(roster_key)**: Full season schedule with W/L/T.
  Complete game-by-game results for the season.

- **roster_current(roster_key)**: Current roster by position.
  Active roster organized by starter/bench slots.

- **roster_snapshot(roster_key, week)**: Historical roster for specific week.
  What the roster looked like during a past week.

- **team_transactions(roster_key, week_from, week_to)**: Team's transactions in a week range.
  What moves did this team make? Pass the same week for both params for a single week.

### Player-Specific

- **player_summary(player_key)**: Metadata (position, team, status, injury).
  Basic player information.

- **player_weekly_log(player_key, week_from?, week_to?)**: Fantasy performance log.
  Week-by-week fantasy points. Omit week params for full season, or pass a range
  to focus on a stretch (e.g., after a trade, during playoffs).

### Playoff Bracket

- **playoff_bracket(bracket_type?)**: Full bracket structure with matchups and results.
  Shows winners and/or losers bracket organized by round. Includes champion and placements.

- **team_playoff_path(roster_key)**: A team's playoff journey.
  Each matchup with opponent, result (win/loss/pending), and final placement.

### Escape Hatch

- **run_sql(query, limit?)**: Custom SELECT query (writes blocked).
  For complex queries not covered by other tools.

## Parameter Notes

- **roster_key**: Accepts team name, manager name, or roster_id
- **player_key**: Accepts player name or player_id
- **week**: Defaults to current week if not specified
"""
