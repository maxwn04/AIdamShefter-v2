"""Auditable Sleeper refresh orchestration with dependency-aware scope apply."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from backend.json import JsonValue, canonical_json_bytes
from backend.resources.errors import ResourceReferenceUnavailable
from backend.resources.sleeper_data.manager import SleeperDataManager
from backend.resources.sleeper_data.objects import (
    ApiRequest,
    ApplyScopeRecords,
    BracketScopeRecords,
    BracketValue,
    CompletenessRecord,
    DraftPickSeedValue,
    ExpandRefreshPlan,
    LeagueScopeRecords,
    LeagueUserValue,
    LeagueUsersScopeRecords,
    LeagueValue,
    MatchupValue,
    MatchupsScopeRecords,
    NormalizationRejection,
    NflStateScopeRecords,
    PayloadReceipt,
    PlayerCatalogScopeRecords,
    PlayerPerformanceValue,
    PlayerValue,
    RecordApiAttempt,
    RefreshFailure,
    RefreshRun,
    RefreshScopePlan,
    RequestStatus as ResourceRequestStatus,
    RosterManagerValue,
    RosterPlayerValue,
    RostersScopeRecords,
    RosterValue,
    SeasonIdentityMap,
    SeasonRosterIdentity,
    StartRefresh,
    TradedPicksScopeRecords,
    TradedPickValue,
    TransactionMoveValue,
    TransactionsScopeRecords,
    TransactionValue,
    UserValue,
)
from backend.sleeper import EndpointKind, ScopeKey

from .contracts import (
    ApplyDisposition,
    NormalizationStatus,
    RefreshOutcome,
    RefreshRequest,
    RefreshStatus,
    RequestStatus,
    ScopeRefreshResult,
)
from .errors import EndpointPayloadRejected, InternalDatalayerFailure
from .local_files import LocalArtifactKind, LocalDatalayerFileStore
from .sleeper.client import SleeperSourceClient
from .sleeper.dispatch import EndpointRecords, normalize_endpoint, validate_completeness
from .sleeper.endpoints.brackets import (
    BracketMatchupRecord,
    build_losers_bracket_request,
    build_winners_bracket_request,
)
from .sleeper.endpoints.league import (
    LeagueRecord,
    LeagueUsersEndpointRecords,
    NflStateRecord,
    build_league_request,
    build_league_users_request,
    build_nfl_state_request,
)
from .sleeper.endpoints.players import PlayerRecord, build_player_catalog_request
from .sleeper.endpoints.rosters import (
    RosterEndpointRecords,
    TradedPickRecord,
    build_rosters_request,
    build_traded_picks_request,
)
from .sleeper.endpoints.weekly import (
    MatchupEndpointRecords,
    TransactionEndpointRecords,
    build_matchups_request,
    build_transactions_request,
)
from .sleeper.responses import (
    CompletenessFinding,
    EndpointRequest,
    FailedSourceAttempt,
    SuccessfulSourceAttempt,
)
from .versions import INGESTION_NORMALIZER_VERSION

@dataclass(frozen=True, slots=True)
class _PlannedEndpoint:
    request: EndpointRequest
    required: bool = True
    dependency_scope_keys: tuple[ScopeKey, ...] = ()

    def to_resource(self) -> RefreshScopePlan:
        return RefreshScopePlan(
            scope_key=str(self.request.scope_key),
            endpoint_kind=self.request.endpoint_kind.value,
            required=self.required,
            dependency_scope_keys=tuple(map(str, self.dependency_scope_keys)),
        )


@dataclass(frozen=True, slots=True)
class _ProcessedScope:
    result: ScopeRefreshResult
    records: EndpointRecords | None


class DatalayerRefreshService:
    """Own one refresh from exact planning through manager-derived finalization."""

    def __init__(
        self,
        *,
        source_client: SleeperSourceClient,
        data_manager: SleeperDataManager,
        file_store: LocalDatalayerFileStore,
        inline_payload_threshold_bytes: int,
        code_version: str,
        normalizer_version: str = INGESTION_NORMALIZER_VERSION,
    ) -> None:
        if inline_payload_threshold_bytes <= 0:
            raise ValueError("inline payload threshold must be positive")
        if not code_version.strip():
            raise ValueError("code_version must not be empty")
        if not normalizer_version.strip():
            raise ValueError("normalizer_version must not be empty")
        self._source_client = source_client
        self._data_manager = data_manager
        self._file_store = file_store
        self._inline_payload_threshold_bytes = inline_payload_threshold_bytes
        self._code_version = code_version
        self._normalizer_version = normalizer_version

    def refresh(self, request: RefreshRequest) -> RefreshOutcome:
        identity = self._data_manager.get_season_identity_map(
            request.competition_season_id
        )
        base_plan = _build_base_plan(identity)
        weekly_plan = (
            _build_weekly_plan(identity, through_week=request.through_week)
            if request.through_week is not None
            else ()
        )
        refresh = self._data_manager.start_refresh(
            StartRefresh(
                competition_season_id=identity.competition_season_id,
                requested_through_week=request.through_week,
                endpoint_plan=tuple(
                    item.to_resource() for item in (*base_plan, *weekly_plan)
                ),
                trigger_source=request.trigger.value,
                code_version=self._code_version,
                normalizer_version=self._normalizer_version,
            )
        )

        results: list[ScopeRefreshResult] = []
        successful_scopes: set[ScopeKey] = set()
        fresh_league: LeagueRecord | None = None
        fresh_state: NflStateRecord | None = None
        finalization_failure: RefreshFailure | None = None
        try:
            for item in base_plan:
                processed = self._process_scope(
                    refresh_id=refresh.id,
                    identity=identity,
                    planned=item,
                    successful_scopes=successful_scopes,
                    draft_rounds=(fresh_league.draft_rounds if fresh_league else None),
                )
                results.append(processed.result)
                if processed.result.normalization_status is NormalizationStatus.SUCCEEDED:
                    successful_scopes.add(item.request.scope_key)
                if isinstance(processed.records, LeagueRecord):
                    fresh_league = processed.records
                elif isinstance(processed.records, NflStateRecord):
                    fresh_state = processed.records

            effective_week = request.through_week
            if (
                effective_week is None
                and fresh_state is not None
                and fresh_state.season == str(identity.season_year)
            ):
                effective_week = max(1, fresh_state.week)

            if request.through_week is None and effective_week is not None:
                weekly_plan = _build_weekly_plan(
                    identity,
                    through_week=effective_week,
                )
                refresh = self._data_manager.expand_refresh_plan(
                    refresh.id,
                    ExpandRefreshPlan(
                        effective_through_week=effective_week,
                        remaining_scopes=tuple(
                            item.to_resource() for item in weekly_plan
                        ),
                    ),
                )

            if effective_week is not None:
                draft_rounds = fresh_league.draft_rounds if fresh_league else None
                for item in weekly_plan:
                    processed = self._process_scope(
                        refresh_id=refresh.id,
                        identity=identity,
                        planned=item,
                        successful_scopes=successful_scopes,
                        draft_rounds=draft_rounds,
                    )
                    results.append(processed.result)
                    if (
                        processed.result.normalization_status
                        is NormalizationStatus.SUCCEEDED
                    ):
                        successful_scopes.add(item.request.scope_key)
            else:
                state_scope = ScopeKey.from_parts("state", "nfl")
                if fresh_state is not None:
                    _append_scope_warning(
                        results,
                        state_scope,
                        "nfl_state_season_mismatch",
                    )
                _append_scope_warning(
                    results,
                    state_scope,
                    "weekly_plan_omitted_nfl_state_unavailable",
                )
                finalization_failure = RefreshFailure(
                    code="effective_week_unavailable",
                    summary="Weekly scopes could not be planned from current NFL state",
                )
        except asyncio.CancelledError:
            self._data_manager.finish_refresh(refresh.id, cancelled=True)
            raise
        except Exception as error:
            self._data_manager.finish_refresh(
                refresh.id,
                failure=RefreshFailure(
                    code="refresh_orchestration_failed",
                    summary="Datalayer refresh orchestration failed",
                ),
            )
            raise InternalDatalayerFailure(correlation_id=str(refresh.id)) from error

        finalized = self._data_manager.finish_refresh(
            refresh.id,
            failure=finalization_failure,
        )
        return _outcome(finalized, results)

    def _process_scope(
        self,
        *,
        refresh_id: UUID,
        identity: SeasonIdentityMap,
        planned: _PlannedEndpoint,
        successful_scopes: set[ScopeKey],
        draft_rounds: int | None,
    ) -> _ProcessedScope:
        attempt = self._source_client.execute(planned.request)
        finding = _completeness(attempt, sleeper_league_id=identity.sleeper_league_id)
        recorded = self._data_manager.record_attempt(
            _record_attempt(
                refresh_id=refresh_id,
                competition_season_id=identity.competition_season_id,
                attempt=attempt,
                finding=finding,
                file_store=self._file_store,
                inline_payload_threshold_bytes=self._inline_payload_threshold_bytes,
            )
        )

        if isinstance(attempt, FailedSourceAttempt) or not finding.is_complete:
            return _ProcessedScope(result=_scope_result(recorded), records=None)

        unavailable = tuple(
            dependency
            for dependency in planned.dependency_scope_keys
            if dependency not in successful_scopes
        )
        if unavailable:
            rejected = self._data_manager.reject_normalization(
                recorded.id,
                NormalizationRejection(
                    code="dependency_scope_unavailable",
                    summary="A required refresh dependency was unavailable",
                ),
            )
            return _ProcessedScope(
                result=_scope_result(
                    rejected,
                    warning_codes=("dependency_scope_unavailable",),
                ),
                records=None,
            )

        try:
            normalized = normalize_endpoint(
                planned.request,
                attempt.payload,
                sleeper_league_id=identity.sleeper_league_id,
            )
            scope_records = _to_scope_records(
                normalized,
                endpoint=planned.request,
                identity=identity,
                draft_rounds=draft_rounds,
            )
        except EndpointPayloadRejected as rejection:
            rejected = self._data_manager.reject_normalization(
                recorded.id,
                NormalizationRejection(code=rejection.code, summary=rejection.summary),
            )
            return _ProcessedScope(
                result=_scope_result(rejected, warning_codes=(rejection.code,)),
                records=None,
            )
        try:
            applied = self._data_manager.apply_scope(recorded.id, scope_records)
        except ResourceReferenceUnavailable:
            code = "reference_data_unavailable"
            rejected = self._data_manager.reject_normalization(
                recorded.id,
                NormalizationRejection(
                    code=code,
                    summary="Endpoint records reference unavailable platform data",
                ),
            )
            return _ProcessedScope(
                result=_scope_result(rejected, warning_codes=(code,)),
                records=None,
            )
        return _ProcessedScope(
            result=ScopeRefreshResult(
                scope_key=ScopeKey.parse(applied.scope_key),
                api_request_id=applied.request_id,
                fetch_status=RequestStatus.SUCCEEDED,
                normalization_status=NormalizationStatus.SUCCEEDED,
                changed_current_view=applied.changed_current_view,
                warning_codes=(
                    (ApplyDisposition.STALE_IGNORED.value,)
                    if applied.disposition == ApplyDisposition.STALE_IGNORED.value
                    else ()
                ),
            ),
            records=(
                None
                if applied.disposition == ApplyDisposition.STALE_IGNORED.value
                else normalized
            ),
        )


def _build_base_plan(identity: SeasonIdentityMap) -> tuple[_PlannedEndpoint, ...]:
    league = build_league_request(
        sleeper_league_id=identity.sleeper_league_id,
        competition_season_id=identity.competition_season_id,
    )
    users = build_league_users_request(
        sleeper_league_id=identity.sleeper_league_id,
        competition_season_id=identity.competition_season_id,
    )
    players = build_player_catalog_request()
    rosters = build_rosters_request(
        identity.competition_season_id,
        identity.sleeper_league_id,
    )
    return (
        _PlannedEndpoint(league),
        _PlannedEndpoint(build_nfl_state_request()),
        _PlannedEndpoint(users),
        _PlannedEndpoint(players),
        _PlannedEndpoint(
            rosters,
            dependency_scope_keys=(users.scope_key, players.scope_key),
        ),
        _PlannedEndpoint(
            build_traded_picks_request(
                identity.competition_season_id,
                identity.sleeper_league_id,
            )
        ),
        _PlannedEndpoint(
            build_winners_bracket_request(
                identity.competition_season_id,
                identity.sleeper_league_id,
            )
        ),
        _PlannedEndpoint(
            build_losers_bracket_request(
                identity.competition_season_id,
                identity.sleeper_league_id,
            )
        ),
    )


def _build_weekly_plan(
    identity: SeasonIdentityMap,
    *,
    through_week: int,
) -> tuple[_PlannedEndpoint, ...]:
    player_scope = ScopeKey.from_parts("players", "nfl")
    result: list[_PlannedEndpoint] = []
    for week in range(1, through_week + 1):
        result.extend(
            (
                _PlannedEndpoint(
                    build_matchups_request(
                        identity.competition_season_id,
                        identity.sleeper_league_id,
                        week,
                    ),
                    dependency_scope_keys=(player_scope,),
                ),
                _PlannedEndpoint(
                    build_transactions_request(
                        identity.competition_season_id,
                        identity.sleeper_league_id,
                        week,
                    ),
                    dependency_scope_keys=(player_scope,),
                ),
            )
        )
    return tuple(result)


def _completeness(
    attempt: SuccessfulSourceAttempt | FailedSourceAttempt,
    *,
    sleeper_league_id: str,
) -> CompletenessFinding:
    if isinstance(attempt, FailedSourceAttempt):
        return CompletenessFinding(
            is_complete=False,
            code="source_attempt_failed",
            summary="Sleeper request did not return a usable payload",
        )
    try:
        return validate_completeness(
            attempt.endpoint,
            attempt.payload,
            sleeper_league_id=sleeper_league_id,
        )
    except Exception:
        return CompletenessFinding(
            is_complete=False,
            code="completeness_validation_failed",
            summary="Sleeper response completeness could not be established",
        )


def _record_attempt(
    *,
    refresh_id: UUID,
    competition_season_id: UUID,
    attempt: SuccessfulSourceAttempt | FailedSourceAttempt,
    finding: CompletenessFinding,
    file_store: LocalDatalayerFileStore,
    inline_payload_threshold_bytes: int,
) -> RecordApiAttempt:
    payload: PayloadReceipt | None = None
    error: Mapping[str, JsonValue] | None = None
    if isinstance(attempt, SuccessfulSourceAttempt):
        canonical = canonical_json_bytes(attempt.payload)
        if len(canonical) != attempt.byte_length:
            raise ValueError("source payload byte length changed after parsing")
        canonical_sha256 = hashlib.sha256(canonical).hexdigest()
        if canonical_sha256 != attempt.response_sha256:
            raise ValueError("source payload hash changed after parsing")
        if len(canonical) > inline_payload_threshold_bytes:
            stored = file_store.store_bytes(LocalArtifactKind.PAYLOAD, canonical)
            payload = PayloadReceipt(
                sha256=stored.sha256,
                byte_length=stored.byte_length,
                media_type=attempt.media_type,
                local_storage_key=stored.storage_key,
            )
        else:
            payload = PayloadReceipt(
                sha256=attempt.response_sha256,
                byte_length=attempt.byte_length,
                media_type=attempt.media_type,
                inline_json_text=canonical.decode("utf-8"),
            )
        status = ResourceRequestStatus.SUCCEEDED
    else:
        status = ResourceRequestStatus(attempt.status.value)
        error = {
            "code": attempt.error.code,
            "summary": attempt.error.summary,
        }

    return RecordApiAttempt(
        refresh_run_id=refresh_id,
        competition_season_id=competition_season_id,
        endpoint_kind=attempt.endpoint.endpoint_kind.value,
        scope_key=str(attempt.endpoint.scope_key),
        request_path=attempt.endpoint.path,
        request_parameters=dict(attempt.endpoint.parameters),
        week=attempt.endpoint.week,
        bracket_kind=attempt.endpoint.bracket_kind,
        requested_at=attempt.requested_at,
        completed_at=attempt.completed_at,
        latency_ms=attempt.latency_ms,
        status=status,
        http_status=attempt.http_status,
        error=error,
        completeness=CompletenessRecord(
            is_complete=finding.is_complete,
            code=finding.code,
            summary=finding.summary,
        ),
        payload=payload,
    )


def _to_scope_records(
    records: EndpointRecords,
    *,
    endpoint: EndpointRequest,
    identity: SeasonIdentityMap,
    draft_rounds: int | None,
) -> ApplyScopeRecords:
    kind = endpoint.endpoint_kind
    if kind is EndpointKind.LEAGUE:
        assert isinstance(records, LeagueRecord)
        if records.season != str(identity.season_year):
            _reject_mapping(
                EndpointKind.LEAGUE,
                "league_season_mismatch",
                "Sleeper league season does not match the platform season",
            )
        return LeagueScopeRecords(
            league=LeagueValue(
                sleeper_league_id=records.sleeper_league_id,
                season=records.season,
                name=records.name,
                sport=records.sport,
                status=records.status,
                previous_sleeper_league_id=records.previous_sleeper_league_id,
                sleeper_draft_id=records.sleeper_draft_id,
                scoring_settings=records.scoring_settings,
                roster_positions=records.roster_positions,
                provider_settings=records.provider_settings,
                playoff_start_week=records.playoff_start_week,
                playoff_team_count=records.playoff_team_count,
                league_average_match=records.league_average_match,
            )
        )
    if kind is EndpointKind.NFL_STATE:
        assert isinstance(records, NflStateRecord)
        return NflStateScopeRecords()
    if kind is EndpointKind.LEAGUE_USERS:
        assert isinstance(records, LeagueUsersEndpointRecords)
        return LeagueUsersScopeRecords(
            users=tuple(
                UserValue(
                    sleeper_user_id=row.sleeper_user_id,
                    display_name=row.display_name,
                    username=row.username,
                    avatar=row.avatar,
                    metadata=row.metadata,
                )
                for row in records.users
            ),
            league_users=tuple(
                LeagueUserValue(
                    sleeper_user_id=row.sleeper_user_id,
                    team_name=row.team_name,
                    nickname=row.nickname,
                    is_commissioner=row.is_commissioner,
                    metadata=row.metadata,
                )
                for row in records.league_users
            ),
        )
    if kind is EndpointKind.PLAYER_CATALOG:
        assert isinstance(records, tuple)
        assert all(isinstance(row, PlayerRecord) for row in records)
        return PlayerCatalogScopeRecords(
            players=tuple(
                PlayerValue(
                    sleeper_player_id=row.sleeper_player_id,
                    full_name=row.full_name,
                    position=row.position,
                    nfl_team=row.nfl_team,
                    active=row.active,
                    status=row.status,
                    injury_status=row.injury_status,
                    age=row.age,
                    years_experience=row.years_experience,
                    metadata=row.metadata,
                )
                for row in records
            )
        )
    if kind is EndpointKind.LEAGUE_ROSTERS:
        assert isinstance(records, RosterEndpointRecords)
        roster_ids = identity.roster_by_sleeper_id
        return RostersScopeRecords(
            rosters=tuple(
                RosterValue(
                    season_roster_id=_season_roster_id(
                        roster_ids, row.sleeper_roster_id, EndpointKind.LEAGUE_ROSTERS
                    ),
                    settings=row.settings,
                    metadata=row.metadata,
                    record_string=row.record_string,
                    wins=row.wins,
                    losses=row.losses,
                    ties=row.ties,
                    points_for=row.points_for,
                    points_against=row.points_against,
                )
                for row in records.rosters
            ),
            managers=tuple(
                RosterManagerValue(
                    season_roster_id=_season_roster_id(
                        roster_ids, row.sleeper_roster_id, EndpointKind.LEAGUE_ROSTERS
                    ),
                    sleeper_user_id=row.sleeper_user_id,
                    role=row.role,
                    source_order=row.source_order,
                )
                for row in records.managers
            ),
            players=tuple(
                RosterPlayerValue(
                    season_roster_id=_season_roster_id(
                        roster_ids, row.sleeper_roster_id, EndpointKind.LEAGUE_ROSTERS
                    ),
                    sleeper_player_id=row.sleeper_player_id,
                    role=row.role,
                )
                for row in records.players
            ),
            draft_pick_seeds=_draft_pick_seeds(identity, draft_rounds),
        )
    if kind is EndpointKind.MATCHUPS:
        assert isinstance(records, MatchupEndpointRecords)
        assert endpoint.week is not None
        roster_ids = identity.roster_by_sleeper_id
        if any(row.week != endpoint.week for row in records.matchups) or any(
            row.week != endpoint.week for row in records.player_performances
        ):
            raise ValueError("matchup records do not match the requested week")
        return MatchupsScopeRecords(
            week=endpoint.week,
            matchups=tuple(
                MatchupValue(
                    season_roster_id=_season_roster_id(
                        roster_ids, row.sleeper_roster_id, EndpointKind.MATCHUPS
                    ),
                    sleeper_matchup_id=row.sleeper_matchup_id,
                    points=row.points,
                )
                for row in records.matchups
            ),
            player_performances=tuple(
                PlayerPerformanceValue(
                    season_roster_id=_season_roster_id(
                        roster_ids, row.sleeper_roster_id, EndpointKind.MATCHUPS
                    ),
                    sleeper_matchup_id=row.sleeper_matchup_id,
                    sleeper_player_id=row.sleeper_player_id,
                    points=row.points,
                    role=row.role,
                )
                for row in records.player_performances
            ),
        )
    if kind is EndpointKind.TRANSACTIONS:
        assert isinstance(records, TransactionEndpointRecords)
        assert endpoint.week is not None
        roster_ids = identity.roster_by_sleeper_id
        moves_by_transaction = {
            row.sleeper_transaction_id: [] for row in records.transactions
        }
        for row in records.moves:
            moves_by_transaction[row.sleeper_transaction_id].append(
                TransactionMoveValue(
                    move_index=row.move_index,
                    move_kind=row.move_kind,
                    from_season_roster_id=_optional_season_roster_id(
                        roster_ids,
                        row.from_sleeper_roster_id,
                        EndpointKind.TRANSACTIONS,
                    ),
                    to_season_roster_id=_optional_season_roster_id(
                        roster_ids,
                        row.to_sleeper_roster_id,
                        EndpointKind.TRANSACTIONS,
                    ),
                    sleeper_player_id=row.sleeper_player_id,
                    draft_season_year=row.draft_season_year,
                    draft_round=row.draft_round,
                    original_franchise_id=_optional_franchise_id(
                        roster_ids,
                        row.original_sleeper_roster_id,
                        EndpointKind.TRANSACTIONS,
                    ),
                    sleeper_pick_id=row.sleeper_pick_id,
                    budget_amount=row.budget_amount,
                )
            )
        if any(row.week != endpoint.week for row in records.transactions):
            raise ValueError("transaction records do not match the requested week")
        return TransactionsScopeRecords(
            week=endpoint.week,
            transactions=tuple(
                TransactionValue(
                    sleeper_transaction_id=row.sleeper_transaction_id,
                    transaction_type=row.transaction_type,
                    status=row.status,
                    provider_created_at_ms=row.provider_created_at_ms,
                    settings=row.settings,
                    metadata=row.metadata,
                    moves=tuple(moves_by_transaction[row.sleeper_transaction_id]),
                )
                for row in records.transactions
            ),
        )
    if kind is EndpointKind.TRADED_PICKS:
        assert isinstance(records, tuple)
        assert all(isinstance(row, TradedPickRecord) for row in records)
        return TradedPicksScopeRecords(
            picks=tuple(
                TradedPickValue(
                    draft_season_year=row.draft_season_year,
                    round=row.draft_round,
                    original_franchise_id=_franchise_id(
                        identity.roster_by_sleeper_id,
                        row.original_sleeper_roster_id,
                        EndpointKind.TRADED_PICKS,
                    ),
                    current_franchise_id=_franchise_id(
                        identity.roster_by_sleeper_id,
                        row.current_owner_sleeper_roster_id,
                        EndpointKind.TRADED_PICKS,
                    ),
                    sleeper_pick_id=row.sleeper_pick_id,
                )
                for row in records
            )
        )
    if kind in (EndpointKind.WINNERS_BRACKET, EndpointKind.LOSERS_BRACKET):
        assert isinstance(records, tuple)
        assert all(isinstance(row, BracketMatchupRecord) for row in records)
        if endpoint.bracket_kind is None:
            raise ValueError("bracket request does not identify its bracket kind")
        bracket_kind = endpoint.bracket_kind
        if any(row.bracket_kind != bracket_kind for row in records):
            raise ValueError("bracket records do not match the requested bracket kind")
        return BracketScopeRecords(
            bracket_kind=bracket_kind,
            matchups=tuple(
                BracketValue(
                    node_key=str(row.matchup_id),
                    round=row.round,
                    t1_season_roster_id=_optional_season_roster_id(
                        identity.roster_by_sleeper_id,
                        _optional_text_id(row.t1_roster_id),
                        _bracket_endpoint(bracket_kind),
                    ),
                    t2_season_roster_id=_optional_season_roster_id(
                        identity.roster_by_sleeper_id,
                        _optional_text_id(row.t2_roster_id),
                        _bracket_endpoint(bracket_kind),
                    ),
                    t1_from_node_key=_optional_text_id(row.t1_from_matchup_id),
                    t1_from_outcome=row.t1_from_outcome,
                    t2_from_node_key=_optional_text_id(row.t2_from_matchup_id),
                    t2_from_outcome=row.t2_from_outcome,
                    winner_season_roster_id=_optional_season_roster_id(
                        identity.roster_by_sleeper_id,
                        _optional_text_id(row.winner_roster_id),
                        _bracket_endpoint(bracket_kind),
                    ),
                    loser_season_roster_id=_optional_season_roster_id(
                        identity.roster_by_sleeper_id,
                        _optional_text_id(row.loser_roster_id),
                        _bracket_endpoint(bracket_kind),
                    ),
                    placement=row.placement,
                )
                for row in records
            ),
        )
    raise TypeError(f"unsupported endpoint kind: {kind.value}")


def _draft_pick_seeds(
    identity: SeasonIdentityMap,
    draft_rounds: int | None,
) -> tuple[DraftPickSeedValue, ...]:
    if draft_rounds is None or draft_rounds <= 0:
        return ()
    franchises = sorted(
        {row.franchise_id for row in identity.roster_by_sleeper_id.values()},
        key=str,
    )
    return tuple(
        DraftPickSeedValue(
            draft_season_year=season,
            round=round_number,
            original_franchise_id=franchise_id,
            current_franchise_id=franchise_id,
        )
        for season in range(identity.season_year + 1, identity.season_year + 4)
        for round_number in range(1, draft_rounds + 1)
        for franchise_id in franchises
    )


def _season_roster_id(
    identities: Mapping[str, SeasonRosterIdentity],
    sleeper_roster_id: str,
    endpoint_kind: EndpointKind,
) -> UUID:
    try:
        identity = identities[sleeper_roster_id]
    except KeyError:
        _reject_mapping(
            endpoint_kind,
            "season_roster_mapping_missing",
            "Sleeper roster has no platform season-roster mapping",
        )
    return identity.season_roster_id


def _franchise_id(
    identities: Mapping[str, SeasonRosterIdentity],
    sleeper_roster_id: str,
    endpoint_kind: EndpointKind,
) -> UUID:
    try:
        identity = identities[sleeper_roster_id]
    except KeyError:
        _reject_mapping(
            endpoint_kind,
            "season_roster_mapping_missing",
            "Sleeper roster has no platform franchise mapping",
        )
    return identity.franchise_id


def _optional_season_roster_id(
    identities: Mapping[str, SeasonRosterIdentity],
    sleeper_roster_id: str | None,
    endpoint_kind: EndpointKind,
) -> UUID | None:
    if sleeper_roster_id is None:
        return None
    return _season_roster_id(identities, sleeper_roster_id, endpoint_kind)


def _optional_franchise_id(
    identities: Mapping[str, SeasonRosterIdentity],
    sleeper_roster_id: str | None,
    endpoint_kind: EndpointKind,
) -> UUID | None:
    if sleeper_roster_id is None:
        return None
    return _franchise_id(identities, sleeper_roster_id, endpoint_kind)


def _optional_text_id(value: int | None) -> str | None:
    return None if value is None else str(value)


def _bracket_endpoint(bracket_kind: str) -> EndpointKind:
    return (
        EndpointKind.WINNERS_BRACKET
        if bracket_kind == "winners"
        else EndpointKind.LOSERS_BRACKET
    )


def _reject_mapping(
    endpoint_kind: EndpointKind,
    code: str,
    summary: str,
) -> NoReturn:
    raise EndpointPayloadRejected(
        endpoint_kind=endpoint_kind,
        code=code,
        summary=summary,
    )


def _scope_result(
    request: ApiRequest,
    *,
    warning_codes: tuple[str, ...] = (),
) -> ScopeRefreshResult:
    return ScopeRefreshResult(
        scope_key=ScopeKey.parse(request.scope_key),
        api_request_id=request.id,
        fetch_status=RequestStatus(request.status),
        normalization_status=NormalizationStatus(request.normalization_status),
        changed_current_view=False,
        warning_codes=warning_codes,
    )


def _append_scope_warning(
    results: list[ScopeRefreshResult],
    scope_key: ScopeKey,
    code: str,
) -> None:
    for index, result in enumerate(results):
        if result.scope_key == scope_key:
            results[index] = result.model_copy(
                update={"warning_codes": (*result.warning_codes, code)},
            )
            return


def _outcome(
    refresh: RefreshRun,
    results: list[ScopeRefreshResult],
) -> RefreshOutcome:
    return RefreshOutcome(
        refresh_run_id=refresh.id,
        status=RefreshStatus(refresh.status),
        requested_scope_count=len(refresh.endpoint_plan),
        succeeded_scope_count=refresh.succeeded_scope_count,
        failed_scope_count=refresh.failed_scope_count,
        scope_results=tuple(results),
    )
