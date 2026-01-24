"""Canonical schema models for Sleeper data layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Optional


class RowMixin:
    """Small helper to prepare values for sqlite inserts."""

    table_name: ClassVar[str]

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class League(RowMixin):
    table_name: ClassVar[str] = "leagues"

    league_id: str
    season: str
    name: str
    sport: str
    scoring_settings_json: Optional[str] = None
    roster_positions_json: Optional[str] = None
    playoff_week_start: Optional[int] = None
    playoff_teams: Optional[int] = None


@dataclass
class SeasonContext(RowMixin):
    table_name: ClassVar[str] = "season_context"

    league_id: str
    computed_week: int
    override_week: Optional[int]
    effective_week: int
    generated_at: str


@dataclass
class User(RowMixin):
    table_name: ClassVar[str] = "users"

    user_id: str
    display_name: str
    avatar: Optional[str] = None
    metadata_json: Optional[str] = None


@dataclass
class Roster(RowMixin):
    table_name: ClassVar[str] = "rosters"

    league_id: str
    roster_id: int
    owner_user_id: Optional[str] = None
    settings_json: Optional[str] = None
    metadata_json: Optional[str] = None


@dataclass
class TeamProfile(RowMixin):
    table_name: ClassVar[str] = "team_profiles"

    league_id: str
    roster_id: int
    team_name: Optional[str] = None
    manager_name: Optional[str] = None
    avatar_url: Optional[str] = None


@dataclass
class MatchupRow(RowMixin):
    table_name: ClassVar[str] = "matchups"

    league_id: str
    season: str
    week: int
    matchup_id: int
    roster_id: int
    points: float
    starters_json: Optional[str] = None
    players_json: Optional[str] = None


@dataclass
class Game(RowMixin):
    table_name: ClassVar[str] = "games"

    league_id: str
    season: str
    week: int
    matchup_id: int
    roster_id_a: int
    roster_id_b: int
    points_a: float
    points_b: float
    winner_roster_id: Optional[int]
    is_playoffs: bool


@dataclass
class Player(RowMixin):
    table_name: ClassVar[str] = "players"

    player_id: str
    full_name: Optional[str] = None
    position: Optional[str] = None
    nfl_team: Optional[str] = None
    status: Optional[str] = None
    injury_status: Optional[str] = None
    metadata_json: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Transaction(RowMixin):
    table_name: ClassVar[str] = "transactions"

    league_id: str
    season: str
    week: int
    transaction_id: str
    type: str
    status: Optional[str] = None
    created_ts: Optional[int] = None
    settings_json: Optional[str] = None
    metadata_json: Optional[str] = None


@dataclass
class TransactionMove(RowMixin):
    table_name: ClassVar[str] = "transaction_moves"

    transaction_id: str
    roster_id: Optional[int]
    player_id: Optional[str]
    direction: str
    bid_amount: Optional[int] = None
    from_roster_id: Optional[int] = None
    to_roster_id: Optional[int] = None


@dataclass
class StandingsWeek(RowMixin):
    table_name: ClassVar[str] = "standings"

    league_id: str
    season: str
    week: int
    roster_id: int
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    rank: Optional[int] = None
    streak_type: Optional[str] = None
    streak_len: Optional[int] = None
