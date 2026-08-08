"""Backward-compatible re-exports of SQLAlchemy tables.

Prefer: `from datalayer.sleeper_data.schema import metadata, leagues, ...`
"""

from . import (
    draft_picks,
    games,
    leagues,
    matchups,
    metadata,
    player_performances,
    players,
    playoff_matchups,
    roster_players,
    rosters,
    season_context,
    standings,
    team_profiles,
    transaction_moves,
    transactions,
    users,
)

__all__ = [
    "metadata",
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
]
