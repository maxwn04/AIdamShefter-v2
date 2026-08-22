"""Immutable records produced by Sleeper endpoint-family normalizers."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    StringConstraints,
    model_validator,
)

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


CompletenessReason = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
ApplyStage = Literal[1, 2, 3]
ManagerRole = Literal["owner", "co_owner"]
RosterRole = Literal["starter", "bench", "taxi", "reserve", "ir"]
LineupRole = Literal["starter", "bench"]
MoveKind = Literal["player", "pick"]
BracketKind = Literal["winners", "losers"]
ProgressionOutcome = Literal["w", "l"]


class _EndpointValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class CompletenessFinding(_EndpointValue):
    """Whether a parsed payload is authoritative for its requested scope."""

    is_complete: StrictBool
    reason: CompletenessReason | None = None

    @model_validator(mode="after")
    def validate_reason(self) -> "CompletenessFinding":
        if self.is_complete and self.reason is not None:
            raise ValueError("a complete payload cannot have an incomplete reason")
        if not self.is_complete and self.reason is None:
            raise ValueError("an incomplete payload requires a reason")
        return self


class EndpointApplyMetadata(_EndpointValue):
    """Pure ordering and prerequisite metadata for one canonical request."""

    apply_stage: ApplyStage
    dependency_scope_keys: tuple[ScopeKey, ...] = ()


class LeagueRecord(_EndpointValue):
    sleeper_league_id: StrictStr
    name: StrictStr
    status: StrictStr | None = None
    season: StrictStr
    previous_sleeper_league_id: StrictStr | None = None
    sleeper_draft_id: StrictStr | None = None
    sport: StrictStr
    scoring_settings: dict[str, JsonValue]
    roster_positions: tuple[StrictStr, ...]
    provider_settings: dict[str, JsonValue]
    playoff_start_week: PositiveInt | None = None
    playoff_team_count: PositiveInt | None = None
    league_average_match: NonNegativeInt | None = None


class UserRecord(_EndpointValue):
    sleeper_user_id: StrictStr
    display_name: StrictStr
    username: StrictStr | None = None
    avatar: StrictStr | None = None
    metadata: dict[str, JsonValue]


class LeagueUserRecord(_EndpointValue):
    sleeper_user_id: StrictStr
    team_name: StrictStr | None = None
    nickname: StrictStr | None = None
    is_commissioner: StrictBool = False
    metadata: dict[str, JsonValue]


class NflStateRecord(_EndpointValue):
    sport: Literal["nfl"] = "nfl"
    week: NonNegativeInt
    leg: NonNegativeInt | None = None
    season_type: StrictStr | None = None
    season_start_date: StrictStr | None = None
    season: StrictStr
    previous_season: StrictStr | None = None
    league_season: StrictStr | None = None
    league_create_season: StrictStr | None = None
    display_week: NonNegativeInt | None = None
    provider_state: dict[str, JsonValue]


class PlayerRecord(_EndpointValue):
    sleeper_player_id: StrictStr
    full_name: StrictStr | None = None
    position: StrictStr | None = None
    nfl_team: StrictStr | None = None
    active: StrictBool | None = None
    status: StrictStr | None = None
    injury_status: StrictStr | None = None
    age: NonNegativeInt | None = None
    years_experience: NonNegativeInt | None = None
    metadata: dict[str, JsonValue]


class RosterRecord(_EndpointValue):
    sleeper_roster_id: StrictStr
    settings: dict[str, JsonValue]
    metadata: dict[str, JsonValue]
    record_string: StrictStr | None = None
    wins: NonNegativeInt
    losses: NonNegativeInt
    ties: NonNegativeInt
    points_for: Decimal
    points_against: Decimal


class RosterManagerRecord(_EndpointValue):
    sleeper_roster_id: StrictStr
    sleeper_user_id: StrictStr
    role: ManagerRole
    source_order: NonNegativeInt


class RosterPlayerRecord(_EndpointValue):
    sleeper_roster_id: StrictStr
    sleeper_player_id: StrictStr
    role: RosterRole


class TradedPickRecord(_EndpointValue):
    draft_season_year: PositiveInt
    draft_round: PositiveInt
    original_sleeper_roster_id: StrictStr
    current_owner_sleeper_roster_id: StrictStr
    sleeper_pick_id: StrictStr | None = None


class MatchupRecord(_EndpointValue):
    week: PositiveInt
    sleeper_roster_id: StrictStr
    sleeper_matchup_id: NonNegativeInt | None = None
    points: Decimal


class PlayerPerformanceRecord(_EndpointValue):
    week: PositiveInt
    sleeper_roster_id: StrictStr
    sleeper_matchup_id: NonNegativeInt | None = None
    sleeper_player_id: StrictStr
    points: Decimal
    role: LineupRole


class TransactionRecord(_EndpointValue):
    week: PositiveInt
    sleeper_transaction_id: StrictStr
    transaction_type: StrictStr
    status: StrictStr | None = None
    provider_created_at_ms: NonNegativeInt | None = None
    settings: dict[str, JsonValue]
    metadata: dict[str, JsonValue]


class TransactionMoveRecord(_EndpointValue):
    sleeper_transaction_id: StrictStr
    move_index: NonNegativeInt
    move_kind: MoveKind
    from_sleeper_roster_id: StrictStr | None = None
    to_sleeper_roster_id: StrictStr | None = None
    sleeper_player_id: StrictStr | None = None
    draft_season_year: PositiveInt | None = None
    draft_round: PositiveInt | None = None
    original_sleeper_roster_id: StrictStr | None = None
    sleeper_pick_id: StrictStr | None = None
    budget_amount: NonNegativeInt | None = None

    @model_validator(mode="after")
    def validate_asset_identity(self) -> "TransactionMoveRecord":
        pick_identity = (
            self.draft_season_year,
            self.draft_round,
            self.original_sleeper_roster_id,
        )
        if self.move_kind == "player":
            if self.sleeper_player_id is None or any(
                value is not None
                for value in (*pick_identity, self.sleeper_pick_id)
            ):
                raise ValueError("player moves require only a player identity")
        elif self.sleeper_player_id is not None or any(
            value is None for value in pick_identity
        ):
            raise ValueError("pick moves require one complete pick identity")
        return self


class BracketMatchupRecord(_EndpointValue):
    bracket_kind: BracketKind
    node_key: StrictStr
    round: PositiveInt
    t1_sleeper_roster_id: StrictStr | None = None
    t2_sleeper_roster_id: StrictStr | None = None
    t1_from_node_key: StrictStr | None = None
    t1_from_outcome: ProgressionOutcome | None = None
    t2_from_node_key: StrictStr | None = None
    t2_from_outcome: ProgressionOutcome | None = None
    winner_sleeper_roster_id: StrictStr | None = None
    loser_sleeper_roster_id: StrictStr | None = None
    placement: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_progression_pairs(self) -> "BracketMatchupRecord":
        if (self.t1_from_node_key is None) != (self.t1_from_outcome is None):
            raise ValueError("t1 progression key and outcome must appear together")
        if (self.t2_from_node_key is None) != (self.t2_from_outcome is None):
            raise ValueError("t2 progression key and outcome must appear together")
        return self


class LeagueEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.LEAGUE] = EndpointKind.LEAGUE
    league: LeagueRecord


class LeagueUsersEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.LEAGUE_USERS] = EndpointKind.LEAGUE_USERS
    users: tuple[UserRecord, ...]
    league_users: tuple[LeagueUserRecord, ...]


class NflStateEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.NFL_STATE] = EndpointKind.NFL_STATE
    state: NflStateRecord


class PlayerCatalogEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.PLAYER_CATALOG] = EndpointKind.PLAYER_CATALOG
    players: tuple[PlayerRecord, ...]


class LeagueRostersEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.LEAGUE_ROSTERS] = (
        EndpointKind.LEAGUE_ROSTERS
    )
    rosters: tuple[RosterRecord, ...]
    managers: tuple[RosterManagerRecord, ...]
    players: tuple[RosterPlayerRecord, ...]


class TradedPicksEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.TRADED_PICKS] = EndpointKind.TRADED_PICKS
    picks: tuple[TradedPickRecord, ...]


class MatchupsEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.MATCHUPS] = EndpointKind.MATCHUPS
    matchups: tuple[MatchupRecord, ...]
    player_performances: tuple[PlayerPerformanceRecord, ...]


class TransactionsEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.TRANSACTIONS] = EndpointKind.TRANSACTIONS
    transactions: tuple[TransactionRecord, ...]
    moves: tuple[TransactionMoveRecord, ...]


class WinnersBracketEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.WINNERS_BRACKET] = (
        EndpointKind.WINNERS_BRACKET
    )
    matchups: tuple[BracketMatchupRecord, ...]


class LosersBracketEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.LOSERS_BRACKET] = (
        EndpointKind.LOSERS_BRACKET
    )
    matchups: tuple[BracketMatchupRecord, ...]


EndpointRecords: TypeAlias = Annotated[
    LeagueEndpointRecords
    | LeagueUsersEndpointRecords
    | NflStateEndpointRecords
    | PlayerCatalogEndpointRecords
    | LeagueRostersEndpointRecords
    | TradedPicksEndpointRecords
    | MatchupsEndpointRecords
    | TransactionsEndpointRecords
    | WinnersBracketEndpointRecords
    | LosersBracketEndpointRecords,
    Field(discriminator="endpoint_kind"),
]
