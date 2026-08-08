"""Schema models and SQLAlchemy table definitions.

One module per table: each file owns the insert DTO and the Core Table.
Import row types and `metadata` from this package.
"""

from ._base import RowMixin, metadata
from .draft_picks import DraftPick, draft_picks
from .games import Game, games
from .leagues import League, leagues
from .matchups import MatchupRow, matchups
from .player_performances import PlayerPerformance, player_performances
from .players import Player, players
from .playoff_matchups import PlayoffMatchup, playoff_matchups
from .roster_players import RosterPlayer, roster_players
from .rosters import Roster, rosters
from .season_context import SeasonContext, season_context
from .standings import StandingsWeek, standings
from .team_profiles import TeamProfile, team_profiles
from .transaction_moves import TransactionMove, transaction_moves
from .transactions import Transaction, transactions
from .users import User, users

__all__ = [
    "RowMixin",
    "metadata",
    "DraftPick",
    "Game",
    "League",
    "MatchupRow",
    "Player",
    "PlayerPerformance",
    "PlayoffMatchup",
    "Roster",
    "RosterPlayer",
    "SeasonContext",
    "StandingsWeek",
    "TeamProfile",
    "Transaction",
    "TransactionMove",
    "User",
    "draft_picks",
    "games",
    "leagues",
    "matchups",
    "player_performances",
    "players",
    "playoff_matchups",
    "roster_players",
    "rosters",
    "season_context",
    "standings",
    "team_profiles",
    "transaction_moves",
    "transactions",
    "users",
]
