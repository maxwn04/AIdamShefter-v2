"""Caller-facing values for the Sleeper ingestion persistence aggregate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Generic, TypeAlias, TypeVar
from uuid import UUID

from backend.json import JsonValue


class RequestStatus(StrEnum):
    SUCCEEDED = "succeeded"
    HTTP_ERROR = "http_error"
    TRANSPORT_ERROR = "transport_error"
    INVALID_PAYLOAD = "invalid_payload"


class NormalizationStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"


class RefreshStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApplyDisposition(StrEnum):
    APPLIED = "applied"
    STALE_IGNORED = "stale_ignored"
    ALREADY_APPLIED = "already_applied"
    IDENTICAL_HEAD_ADVANCED = "identical_head_advanced"


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    limit: int
    offset: int
    total: int


@dataclass(frozen=True, slots=True)
class RefreshScopePlan:
    scope_key: str
    endpoint_kind: str
    required: bool
    dependency_scope_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StartRefresh:
    competition_season_id: UUID
    requested_through_week: int | None
    endpoint_plan: tuple[RefreshScopePlan, ...]
    trigger_source: str
    code_version: str
    normalizer_version: str


@dataclass(frozen=True, slots=True)
class ExpandRefreshPlan:
    effective_through_week: int
    remaining_scopes: tuple[RefreshScopePlan, ...]


@dataclass(frozen=True, slots=True)
class CompletenessRecord:
    is_complete: bool
    code: str
    summary: str


@dataclass(frozen=True, slots=True)
class PayloadReceipt:
    sha256: str
    byte_length: int
    media_type: str
    inline_json_text: str | None = None
    local_storage_key: str | None = None

    def __post_init__(self) -> None:
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise ValueError("payload sha256 must be 64 lowercase hexadecimal characters")
        if self.byte_length < 0:
            raise ValueError("payload byte_length must be non-negative")
        if not self.media_type.strip():
            raise ValueError("payload media_type must not be empty")
        if (self.inline_json_text is None) == (self.local_storage_key is None):
            raise ValueError("payload receipt requires exactly one storage location")
        if self.local_storage_key is not None:
            expected_key = (
                f"payloads/sha256/{self.sha256[:2]}/{self.sha256}.json"
            )
            if self.local_storage_key != expected_key:
                raise ValueError("local payload key does not match its content receipt")


@dataclass(frozen=True, slots=True)
class RecordApiAttempt:
    refresh_run_id: UUID
    competition_season_id: UUID
    endpoint_kind: str
    scope_key: str
    request_path: str
    request_parameters: Mapping[str, JsonValue]
    week: int | None
    bracket_kind: str | None
    requested_at: datetime
    completed_at: datetime
    latency_ms: int
    status: RequestStatus
    http_status: int | None
    error: Mapping[str, JsonValue] | None
    completeness: CompletenessRecord
    payload: PayloadReceipt | None

    def __post_init__(self) -> None:
        _require_aware(self.requested_at, "requested_at")
        _require_aware(self.completed_at, "completed_at")
        if self.completed_at < self.requested_at:
            raise ValueError("API attempt cannot complete before it starts")
        if self.latency_ms < 0:
            raise ValueError("API attempt latency_ms must be non-negative")
        if (self.status is RequestStatus.SUCCEEDED) != (self.payload is not None):
            raise ValueError("only successful API attempts may carry a payload")
        if self.status is not RequestStatus.SUCCEEDED and self.completeness.is_complete:
            raise ValueError("failed API attempts cannot be complete")


@dataclass(frozen=True, slots=True)
class NormalizationRejection:
    code: str
    summary: str


@dataclass(frozen=True, slots=True)
class RefreshFailure:
    code: str
    summary: str


@dataclass(frozen=True, slots=True)
class RefreshRun:
    id: UUID
    competition_id: UUID
    competition_season_id: UUID
    requested_through_week: int | None
    effective_through_week: int | None
    endpoint_plan: tuple[RefreshScopePlan, ...]
    trigger_source: str
    status: RefreshStatus
    code_version: str
    normalizer_version: str
    started_at: datetime
    completed_at: datetime | None
    error_summary: Mapping[str, JsonValue] | None
    attempt_count: int
    succeeded_scope_count: int
    failed_scope_count: int

    @property
    def requested_scope_count(self) -> int:
        return len(self.endpoint_plan)


@dataclass(frozen=True, slots=True)
class ApiRequest:
    id: UUID
    refresh_run_id: UUID
    competition_season_id: UUID
    endpoint_kind: str
    scope_key: str
    request_path: str
    request_parameters: Mapping[str, JsonValue]
    week: int | None
    bracket_kind: str | None
    requested_at: datetime
    completed_at: datetime
    latency_ms: int | None
    status: RequestStatus
    http_status: int | None
    error: Mapping[str, JsonValue] | None
    is_complete: bool
    completeness_reason: str | None
    response_sha256: str | None
    normalization_status: NormalizationStatus
    normalizer_version: str | None
    normalized_at: datetime | None


@dataclass(frozen=True, slots=True)
class ApplyResult:
    disposition: ApplyDisposition
    request_id: UUID
    scope_key: str
    normalized_row_count: int

    @property
    def changed_current_view(self) -> bool:
        return self.disposition is ApplyDisposition.APPLIED


@dataclass(frozen=True, slots=True)
class SeasonRosterIdentity:
    season_roster_id: UUID
    franchise_id: UUID


@dataclass(frozen=True, slots=True)
class SeasonIdentityMap:
    competition_id: UUID
    competition_season_id: UUID
    sleeper_league_id: str
    season_year: int
    roster_by_sleeper_id: Mapping[str, SeasonRosterIdentity]


@dataclass(frozen=True, slots=True)
class LeagueValue:
    sleeper_league_id: str
    season: str
    name: str
    sport: str
    status: str | None
    previous_sleeper_league_id: str | None
    sleeper_draft_id: str | None
    scoring_settings: Mapping[str, JsonValue]
    roster_positions: tuple[str, ...]
    provider_settings: Mapping[str, JsonValue]
    playoff_start_week: int | None
    playoff_team_count: int | None
    league_average_match: int | None


@dataclass(frozen=True, slots=True)
class LeagueScopeRecords:
    league: LeagueValue


@dataclass(frozen=True, slots=True)
class UserValue:
    sleeper_user_id: str
    display_name: str
    username: str | None
    avatar: str | None
    metadata: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LeagueUserValue:
    sleeper_user_id: str
    team_name: str | None
    nickname: str | None
    is_commissioner: bool
    metadata: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LeagueUsersScopeRecords:
    users: tuple[UserValue, ...]
    league_users: tuple[LeagueUserValue, ...]


@dataclass(frozen=True, slots=True)
class PlayerValue:
    sleeper_player_id: str
    full_name: str | None
    position: str | None
    nfl_team: str | None
    active: bool | None
    status: str | None
    injury_status: str | None
    age: int | None
    years_experience: int | None
    metadata: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class PlayerCatalogScopeRecords:
    players: tuple[PlayerValue, ...]


@dataclass(frozen=True, slots=True)
class NflStateScopeRecords:
    """A complete NFL-state scope with no normalized current-view table."""


@dataclass(frozen=True, slots=True)
class RosterValue:
    season_roster_id: UUID
    settings: Mapping[str, JsonValue]
    metadata: Mapping[str, JsonValue]
    record_string: str | None
    wins: int
    losses: int
    ties: int
    points_for: Decimal
    points_against: Decimal


@dataclass(frozen=True, slots=True)
class RosterManagerValue:
    season_roster_id: UUID
    sleeper_user_id: str
    role: str
    source_order: int


@dataclass(frozen=True, slots=True)
class RosterPlayerValue:
    season_roster_id: UUID
    sleeper_player_id: str
    role: str


@dataclass(frozen=True, slots=True)
class DraftPickSeedValue:
    draft_season_year: int
    round: int
    original_franchise_id: UUID
    current_franchise_id: UUID


@dataclass(frozen=True, slots=True)
class RostersScopeRecords:
    rosters: tuple[RosterValue, ...]
    managers: tuple[RosterManagerValue, ...]
    players: tuple[RosterPlayerValue, ...]
    draft_pick_seeds: tuple[DraftPickSeedValue, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchupValue:
    season_roster_id: UUID
    sleeper_matchup_id: int | None
    points: Decimal


@dataclass(frozen=True, slots=True)
class PlayerPerformanceValue:
    season_roster_id: UUID
    sleeper_matchup_id: int | None
    sleeper_player_id: str
    points: Decimal
    role: str


@dataclass(frozen=True, slots=True)
class MatchupsScopeRecords:
    week: int
    matchups: tuple[MatchupValue, ...]
    player_performances: tuple[PlayerPerformanceValue, ...]


@dataclass(frozen=True, slots=True)
class TransactionMoveValue:
    move_index: int
    move_kind: str
    from_season_roster_id: UUID | None
    to_season_roster_id: UUID | None
    sleeper_player_id: str | None
    draft_season_year: int | None
    draft_round: int | None
    original_franchise_id: UUID | None
    sleeper_pick_id: str | None
    budget_amount: int | None


@dataclass(frozen=True, slots=True)
class TransactionValue:
    sleeper_transaction_id: str
    transaction_type: str
    status: str | None
    provider_created_at_ms: int | None
    settings: Mapping[str, JsonValue]
    metadata: Mapping[str, JsonValue]
    moves: tuple[TransactionMoveValue, ...]


@dataclass(frozen=True, slots=True)
class TransactionsScopeRecords:
    week: int
    transactions: tuple[TransactionValue, ...]


@dataclass(frozen=True, slots=True)
class TradedPickValue:
    draft_season_year: int
    round: int
    original_franchise_id: UUID
    current_franchise_id: UUID
    sleeper_pick_id: str | None


@dataclass(frozen=True, slots=True)
class TradedPicksScopeRecords:
    picks: tuple[TradedPickValue, ...]


@dataclass(frozen=True, slots=True)
class BracketValue:
    node_key: str
    round: int
    t1_season_roster_id: UUID | None
    t2_season_roster_id: UUID | None
    t1_from_node_key: str | None
    t1_from_outcome: str | None
    t2_from_node_key: str | None
    t2_from_outcome: str | None
    winner_season_roster_id: UUID | None
    loser_season_roster_id: UUID | None
    placement: int | None


@dataclass(frozen=True, slots=True)
class BracketScopeRecords:
    bracket_kind: str
    matchups: tuple[BracketValue, ...]


ApplyScopeRecords: TypeAlias = (
    LeagueScopeRecords
    | LeagueUsersScopeRecords
    | PlayerCatalogScopeRecords
    | NflStateScopeRecords
    | RostersScopeRecords
    | MatchupsScopeRecords
    | TransactionsScopeRecords
    | TradedPicksScopeRecords
    | BracketScopeRecords
)


@dataclass(frozen=True, slots=True)
class SnapshotCandidateQuery:
    competition_season_id: UUID
    observed_through: datetime

    def __post_init__(self) -> None:
        _require_aware(self.observed_through, "observed_through")


@dataclass(frozen=True, slots=True)
class ApiRequestCandidate:
    request_id: UUID
    competition_season_id: UUID
    endpoint_kind: str
    scope_key: str
    week: int | None
    bracket_kind: str | None
    requested_at: datetime
    completed_at: datetime
    response_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedPayload:
    request_id: UUID
    endpoint_kind: str
    scope_key: str
    response_sha256: str
    byte_length: int
    media_type: str
    inline_json_text: str | None
    local_storage_key: str | None


@dataclass(frozen=True, slots=True)
class LeagueSeasonOverview:
    competition_id: UUID
    competition_season_id: UUID
    name: str
    season: str
    status: str | None
    playoff_start_week: int | None
    playoff_team_count: int | None


@dataclass(frozen=True, slots=True)
class SeasonRosterState:
    season_roster_id: UUID
    competition_season_id: UUID
    record_string: str | None
    wins: int
    losses: int
    ties: int
    points_for: Decimal | None
    points_against: Decimal | None
    manager_user_ids: tuple[str, ...]
    player_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchupState:
    competition_season_id: UUID
    week: int
    season_roster_id: UUID
    sleeper_matchup_id: int | None
    points: Decimal


@dataclass(frozen=True, slots=True)
class TransactionQuery:
    competition_season_id: UUID
    week_from: int | None = None
    week_to: int | None = None


@dataclass(frozen=True, slots=True)
class TransactionState:
    id: UUID
    competition_season_id: UUID
    sleeper_transaction_id: str
    week: int
    transaction_type: str
    status: str | None


@dataclass(frozen=True, slots=True)
class PlayerSearch:
    text: str
    limit: int = 50
    offset: int = 0


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
