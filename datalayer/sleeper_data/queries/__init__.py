"""Query helpers for the Sleeper data layer.

This package provides curated query functions for common fantasy football
research tasks. All functions return dictionaries with a consistent structure
including a 'found' boolean and 'as_of_week' context where applicable.

Modules:
    league: League-wide queries (snapshot, games, leaderboard)
    team: Team-specific queries (dossier, schedule, roster)
    player: Player queries (summary, weekly log)
    transactions: Transaction queries (trades, waivers, FA)
    sql_tool: Custom SQL execution
"""

from .league import (
    get_bench_analysis,
    get_league_snapshot,
    get_season_leaders,
    get_standings,
    get_team_game,
    get_team_game_with_players,
    get_week_games,
    get_week_games_with_players,
    get_week_player_leaderboard,
)
from .player import get_player_summary, get_player_weekly_log
from .playoffs import get_playoff_bracket, get_team_playoff_path
from .sql_tool import run_sql
from .team import get_roster_current, get_roster_snapshot, get_team_dossier, get_team_schedule
from .transactions import get_team_transactions, get_transactions

__all__ = [
    # League queries
    "get_bench_analysis",
    "get_league_snapshot",
    "get_season_leaders",
    "get_standings",
    "get_week_games",
    "get_week_games_with_players",
    "get_team_game",
    "get_team_game_with_players",
    "get_week_player_leaderboard",
    # Team queries
    "get_team_dossier",
    "get_team_schedule",
    "get_roster_current",
    "get_roster_snapshot",
    # Player queries
    "get_player_summary",
    "get_player_weekly_log",
    # Playoff queries
    "get_playoff_bracket",
    "get_team_playoff_path",
    # Transaction queries
    "get_transactions",
    "get_team_transactions",
    # SQL tool
    "run_sql",
]
