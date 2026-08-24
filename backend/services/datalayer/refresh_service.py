"""Synchronous orchestration for one complete Sleeper refresh workflow."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
from time import sleep
from typing import Protocol, assert_never, cast
from uuid import UUID

from backend.resources.sleeper_data.league_seasons import RefreshSeasonIdentity
from backend.resources.sleeper_data.normalized_scopes import ApplyResult
from backend.resources.sleeper_data.refreshes import (
    PlannedEndpointScope,
    RefreshRun,
    StartRefresh,
)
from backend.resources.sleeper_data.requests import (
    ApiRequest,
    NormalizationRejection,
    RecordApiAttempt,
)
from backend.services.datalayer.canonical_json import JsonValue, canonical_json_bytes
from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RefreshOutcome,
    RefreshRequest,
    RequestStatus,
    ScopeRefreshResult,
)
from backend.services.datalayer.errors import (
    DatalayerScopeConflict,
    EndpointPayloadRejected,
    RosterIdentityMappingRequired,
)
from backend.services.datalayer.local_files import (
    LocalArtifactKind,
    LocalArtifactVerificationError,
    StoredLocalArtifact,
)
from backend.services.datalayer.sleeper.endpoints import (
    CompletenessFinding,
    EndpointRecords,
    LeagueEndpointRecords,
    LeagueRostersEndpointRecords,
    LeagueUsersEndpointRecords,
    NflStateEndpointRecords,
    build_league_request,
    build_league_rosters_request,
    build_league_users_request,
    build_losers_bracket_request,
    build_matchups_request,
    build_nfl_state_request,
    build_player_catalog_request,
    build_traded_picks_request,
    build_transactions_request,
    build_winners_bracket_request,
    get_endpoint_apply_metadata,
    missing_dependency_scope_keys,
    normalize_league,
    normalize_league_rosters,
    normalize_league_users,
    normalize_losers_bracket,
    normalize_matchups,
    normalize_nfl_state,
    normalize_player_catalog,
    normalize_traded_picks,
    normalize_transactions,
    normalize_winners_bracket,
    validate_league_completeness,
    validate_league_rosters_completeness,
    validate_league_users_completeness,
    validate_losers_bracket_completeness,
    validate_matchups_completeness,
    validate_nfl_state_completeness,
    validate_player_catalog_completeness,
    validate_traded_picks_completeness,
    validate_transactions_completeness,
    validate_winners_bracket_completeness,
)
from backend.services.datalayer.sleeper.responses import (
    EndpointRequest,
    FailedSourceAttempt,
    SourceAttempt,
    SuccessfulSourceAttempt,
)
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey
from backend.services.datalayer.versions import INGESTION_NORMALIZER_VERSION


class SourceReader(Protocol):
    def execute(self, request: EndpointRequest) -> SourceAttempt: ...


class PayloadFileStore(Protocol):
    def store_bytes(
        self, kind: LocalArtifactKind, content: bytes
    ) -> StoredLocalArtifact: ...


class SeasonIdentityReader(Protocol):
    def get_refresh_identity(
        self, competition_season_id: UUID
    ) -> RefreshSeasonIdentity: ...


class RefreshWriter(Protocol):
    def start_refresh(self, command: StartRefresh) -> RefreshRun: ...

    def finish_refresh(self, refresh_id: UUID) -> RefreshRun: ...


class AttemptWriter(Protocol):
    def record_attempt(self, command: RecordApiAttempt) -> ApiRequest: ...

    def reject_normalization(
        self, request_id: UUID, rejection: NormalizationRejection
    ) -> ApiRequest: ...


class ScopeWriter(Protocol):
    def apply_scope(
        self, request_id: UUID, records: EndpointRecords
    ) -> ApplyResult: ...


class FirstSeasonRosterMapper(Protocol):
    def bootstrap_first_season(
        self,
        competition_season_id: UUID,
        rosters: LeagueRostersEndpointRecords,
        users: LeagueUsersEndpointRecords | None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class PlannedRefresh:
    requests: tuple[EndpointRequest, ...]
    endpoint_scope: tuple[PlannedEndpointScope, ...]
    through_week: int | None


@dataclass(slots=True)
class _AttemptState:
    source: SourceAttempt
    completeness: CompletenessFinding
    stored: ApiRequest | None = None
    warning_codes: tuple[str, ...] = ()
    changed_current_view: bool = False


class DatalayerRefreshService:
    """Fetch, audit, normalize, apply, and finalize one Sleeper refresh."""

    def __init__(
        self,
        *,
        source: SourceReader,
        identities: SeasonIdentityReader,
        refreshes: RefreshWriter,
        attempts: AttemptWriter,
        scopes: ScopeWriter,
        files: PayloadFileStore,
        code_version: str,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 1.0,
        inline_payload_max_bytes: int = 1024 * 1024,
        delay: Callable[[float], None] = sleep,
        roster_mappings: FirstSeasonRosterMapper | None = None,
    ) -> None:
        if not code_version.strip():
            raise ValueError("code_version must not be empty")
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts < 1
        ):
            raise ValueError("max_attempts must be positive")
        if (
            isinstance(retry_backoff_seconds, bool)
            or not isinstance(retry_backoff_seconds, (int, float))
            or not math.isfinite(retry_backoff_seconds)
            or retry_backoff_seconds <= 0
        ):
            raise ValueError("retry_backoff_seconds must be positive")
        if (
            isinstance(inline_payload_max_bytes, bool)
            or not isinstance(inline_payload_max_bytes, int)
            or inline_payload_max_bytes < 1
        ):
            raise ValueError("inline_payload_max_bytes must be positive")
        self._source = source
        self._identities = identities
        self._refreshes = refreshes
        self._attempts = attempts
        self._scopes = scopes
        self._files = files
        self._code_version = code_version.strip()
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._inline_payload_max_bytes = inline_payload_max_bytes
        self._delay = delay
        self._roster_mappings = roster_mappings

    def refresh(self, request: RefreshRequest) -> RefreshOutcome:
        identity = self._identities.get_refresh_identity(
            request.competition_season_id
        )
        preflight_requests = (
            build_league_request(
                identity.competition_season_id, identity.sleeper_league_id
            ),
            build_nfl_state_request(),
        )
        buffered = {
            endpoint.scope_key: self._execute_attempts(endpoint)
            for endpoint in preflight_requests
        }
        league_records = _complete_league_records(
            buffered[preflight_requests[0].scope_key]
        )
        nfl_records = _complete_nfl_records(buffered[preflight_requests[1].scope_key])
        effective_week = request.through_week
        if (
            effective_week is None
            and nfl_records is not None
            and nfl_records.state.week > 0
        ):
            effective_week = min(nfl_records.state.week, 18)
        plan = build_standard_refresh_plan(
            identity,
            through_week=effective_week,
            league_records=league_records,
        )
        refresh = self._refreshes.start_refresh(
            StartRefresh(
                competition_season_id=identity.competition_season_id,
                requested_through_week=request.through_week,
                trigger=request.trigger,
                endpoint_scope=plan.endpoint_scope,
                code_version=self._code_version,
                normalizer_version=INGESTION_NORMALIZER_VERSION,
            )
        )
        states: dict[ScopeKey, list[_AttemptState]] = {}
        try:
            for endpoint in preflight_requests:
                attempts = buffered[endpoint.scope_key]
                states[endpoint.scope_key] = attempts
                for state in attempts:
                    self._record_attempt(refresh.id, state)
            for endpoint in plan.requests:
                if endpoint.scope_key in states:
                    continue
                attempts = self._execute_and_record(refresh.id, endpoint)
                states[endpoint.scope_key] = attempts
            self._apply_latest(plan, states)
        except Exception:
            self._refreshes.finish_refresh(refresh.id)
            raise
        terminal = self._refreshes.finish_refresh(refresh.id)
        return _build_outcome(terminal, plan, states)

    def _execute_attempts(self, endpoint: EndpointRequest) -> list[_AttemptState]:
        results: list[_AttemptState] = []
        for attempt_number in range(1, self._max_attempts + 1):
            source = self._source.execute(endpoint)
            completeness = _completeness(source)
            results.append(_AttemptState(source=source, completeness=completeness))
            if (
                not _should_retry(source, completeness)
                or attempt_number == self._max_attempts
            ):
                break
            self._delay(
                self._retry_backoff_seconds * (2 ** (attempt_number - 1))
            )
        return results

    def _execute_and_record(
        self,
        refresh_id: UUID,
        endpoint: EndpointRequest,
    ) -> list[_AttemptState]:
        results: list[_AttemptState] = []
        for attempt_number in range(1, self._max_attempts + 1):
            source = self._source.execute(endpoint)
            completeness = _completeness(source)
            state = _AttemptState(source=source, completeness=completeness)
            self._record_attempt(refresh_id, state)
            results.append(state)
            if (
                not _should_retry(source, completeness)
                or attempt_number == self._max_attempts
            ):
                break
            self._delay(
                self._retry_backoff_seconds * (2 ** (attempt_number - 1))
            )
        return results

    def _record_attempt(self, refresh_id: UUID, state: _AttemptState) -> None:
        receipt: StoredLocalArtifact | None = None
        warnings = list(state.warning_codes)
        if isinstance(state.source, SuccessfulSourceAttempt):
            payload_bytes = canonical_json_bytes(state.source.payload)
        else:
            payload_bytes = None
        if (
            payload_bytes is not None
            and len(payload_bytes) > self._inline_payload_max_bytes
        ):
            try:
                receipt = self._files.store_bytes(
                    LocalArtifactKind.PAYLOAD,
                    payload_bytes,
                )
            except (OSError, LocalArtifactVerificationError):
                warnings.append("payload_storage_fallback")
        state.stored = self._attempts.record_attempt(
            RecordApiAttempt(
                refresh_run_id=refresh_id,
                attempt=state.source,
                completeness=state.completeness,
                object_receipt=receipt,
            )
        )
        state.warning_codes = tuple(warnings)

    def _apply_latest(
        self,
        plan: PlannedRefresh,
        states: dict[ScopeKey, list[_AttemptState]],
    ) -> None:
        available: set[ScopeKey] = set()
        normalized_by_kind: dict[EndpointKind, EndpointRecords] = {}
        for endpoint in plan.requests:
            state = states[endpoint.scope_key][-1]
            stored = cast(ApiRequest, state.stored)
            if not (
                isinstance(state.source, SuccessfulSourceAttempt)
                and state.completeness.is_complete
            ):
                continue
            metadata = get_endpoint_apply_metadata(endpoint)
            missing = missing_dependency_scope_keys(metadata, available)
            if missing:
                state.stored = self._attempts.reject_normalization(
                    stored.id,
                    NormalizationRejection(
                        code="normalization_dependency_unavailable",
                        summary="A required refresh dependency was unavailable",
                    ),
                )
                state.warning_codes += ("normalization_dependency_unavailable",)
                continue
            try:
                records = _normalize(state.source, endpoint)
                normalized_by_kind[endpoint.endpoint_kind] = records
                if (
                    isinstance(records, LeagueRostersEndpointRecords)
                    and self._roster_mappings is not None
                ):
                    users = normalized_by_kind.get(EndpointKind.LEAGUE_USERS)
                    self._roster_mappings.bootstrap_first_season(
                        cast(UUID, stored.competition_season_id),
                        records,
                        users if isinstance(users, LeagueUsersEndpointRecords) else None,
                    )
                applied = self._scopes.apply_scope(stored.id, records)
            except EndpointPayloadRejected as error:
                state.stored = self._attempts.reject_normalization(
                    stored.id,
                    NormalizationRejection(code=error.code, summary=error.summary),
                )
                state.warning_codes += (error.code,)
                continue
            except RosterIdentityMappingRequired:
                state.stored = self._attempts.reject_normalization(
                    stored.id,
                    NormalizationRejection(
                        code="roster_identity_mapping_required",
                        summary=(
                            "Sleeper rosters require durable franchise mappings"
                        ),
                    ),
                )
                state.warning_codes += ("roster_identity_mapping_required",)
                continue
            except DatalayerScopeConflict:
                state.stored = self._attempts.reject_normalization(
                    stored.id,
                    NormalizationRejection(
                        code="normalization_scope_conflict",
                        summary=(
                            "Normalized facts could not be mapped to the refresh scope"
                        ),
                    ),
                )
                state.warning_codes += ("normalization_scope_conflict",)
                continue
            state.stored = stored.model_copy(
                update={"normalization_status": NormalizationStatus.SUCCEEDED}
            )
            state.changed_current_view = applied.changed_current_view
            state.warning_codes += (
                ("stale_observation",)
                if applied.disposition.value == "stale_ignored"
                else ()
            )
            available.add(endpoint.scope_key)


def build_standard_refresh_plan(
    identity: RefreshSeasonIdentity,
    *,
    through_week: int | None,
    league_records: LeagueEndpointRecords | None,
) -> PlannedRefresh:
    """Build the one deterministic v1 product refresh plan."""

    if through_week is not None and (
        isinstance(through_week, bool)
        or not isinstance(through_week, int)
        or not 1 <= through_week <= 18
    ):
        raise ValueError("refresh plan through_week must be between 1 and 18")

    requests: list[EndpointRequest] = [
        build_league_request(
            identity.competition_season_id, identity.sleeper_league_id
        ),
        build_league_users_request(
            identity.competition_season_id, identity.sleeper_league_id
        ),
        build_nfl_state_request(),
        build_player_catalog_request(),
        build_league_rosters_request(
            identity.competition_season_id, identity.sleeper_league_id
        ),
    ]
    settings = (
        league_records.league.provider_settings
        if league_records is not None
        else {}
    )
    raw_rounds = settings.get("draft_rounds")
    if (
        isinstance(raw_rounds, int)
        and not isinstance(raw_rounds, bool)
        and raw_rounds > 0
    ):
        requests.append(
            build_traded_picks_request(
                identity.competition_season_id, identity.sleeper_league_id
            )
        )
    if through_week is not None:
        for week in range(1, through_week + 1):
            requests.extend(
                (
                    build_matchups_request(
                        identity.competition_season_id,
                        identity.sleeper_league_id,
                        week,
                    ),
                    build_transactions_request(
                        identity.competition_season_id,
                        identity.sleeper_league_id,
                        week,
                    ),
                )
            )
        playoff_start = (
            league_records.league.playoff_start_week
            if league_records is not None
            else None
        )
        if league_records is not None and (
            playoff_start is None or through_week >= playoff_start
        ):
            requests.extend(
                (
                    build_winners_bracket_request(
                        identity.competition_season_id,
                        identity.sleeper_league_id,
                    ),
                    build_losers_bracket_request(
                        identity.competition_season_id,
                        identity.sleeper_league_id,
                    ),
                )
            )
    endpoint_scope = tuple(
        PlannedEndpointScope(
            scope_key=endpoint.scope_key,
            endpoint_kind=endpoint.endpoint_kind,
            dependency_scope_keys=get_endpoint_apply_metadata(
                endpoint
            ).dependency_scope_keys,
        )
        for endpoint in requests
    )
    return PlannedRefresh(
        requests=tuple(requests),
        endpoint_scope=endpoint_scope,
        through_week=through_week,
    )


def _completeness(source: SourceAttempt) -> CompletenessFinding:
    if isinstance(source, FailedSourceAttempt):
        return CompletenessFinding(
            is_complete=False, reason="source_attempt_failed"
        )
    try:
        return _validate(source.payload, source.endpoint)
    except Exception:
        return CompletenessFinding(
            is_complete=False, reason="completeness_validation_failed"
        )


def _validate(payload: JsonValue, endpoint: EndpointRequest) -> CompletenessFinding:
    match endpoint.endpoint_kind:
        case EndpointKind.LEAGUE:
            return validate_league_completeness(payload, endpoint)
        case EndpointKind.LEAGUE_USERS:
            return validate_league_users_completeness(payload, endpoint)
        case EndpointKind.LEAGUE_ROSTERS:
            return validate_league_rosters_completeness(payload, endpoint)
        case EndpointKind.NFL_STATE:
            return validate_nfl_state_completeness(payload, endpoint)
        case EndpointKind.PLAYER_CATALOG:
            return validate_player_catalog_completeness(payload, endpoint)
        case EndpointKind.MATCHUPS:
            return validate_matchups_completeness(payload, endpoint)
        case EndpointKind.TRANSACTIONS:
            return validate_transactions_completeness(payload, endpoint)
        case EndpointKind.TRADED_PICKS:
            return validate_traded_picks_completeness(payload, endpoint)
        case EndpointKind.WINNERS_BRACKET:
            return validate_winners_bracket_completeness(payload, endpoint)
        case EndpointKind.LOSERS_BRACKET:
            return validate_losers_bracket_completeness(payload, endpoint)
    assert_never(endpoint.endpoint_kind)


def _normalize(
    source: SuccessfulSourceAttempt,
    endpoint: EndpointRequest,
) -> EndpointRecords:
    match endpoint.endpoint_kind:
        case EndpointKind.LEAGUE:
            return normalize_league(source.payload, endpoint)
        case EndpointKind.LEAGUE_USERS:
            return normalize_league_users(source.payload, endpoint)
        case EndpointKind.LEAGUE_ROSTERS:
            return normalize_league_rosters(source.payload, endpoint)
        case EndpointKind.NFL_STATE:
            return normalize_nfl_state(source.payload, endpoint)
        case EndpointKind.PLAYER_CATALOG:
            return normalize_player_catalog(source.payload, endpoint)
        case EndpointKind.MATCHUPS:
            return normalize_matchups(source.payload, endpoint)
        case EndpointKind.TRANSACTIONS:
            return normalize_transactions(source.payload, endpoint)
        case EndpointKind.TRADED_PICKS:
            return normalize_traded_picks(source.payload, endpoint)
        case EndpointKind.WINNERS_BRACKET:
            return normalize_winners_bracket(source.payload, endpoint)
        case EndpointKind.LOSERS_BRACKET:
            return normalize_losers_bracket(source.payload, endpoint)
    assert_never(endpoint.endpoint_kind)


def _should_retry(
    source: SourceAttempt,
    completeness: CompletenessFinding,
) -> bool:
    if isinstance(source, SuccessfulSourceAttempt):
        return not completeness.is_complete
    if source.status in {
        RequestStatus.TRANSPORT_ERROR,
        RequestStatus.INVALID_PAYLOAD,
    }:
        return True
    return source.status is RequestStatus.HTTP_ERROR and cast(
        int, source.http_status
    ) in {429, *range(500, 600)}


def _complete_league_records(
    states: Sequence[_AttemptState],
) -> LeagueEndpointRecords | None:
    state = states[-1]
    if (
        not isinstance(state.source, SuccessfulSourceAttempt)
        or not state.completeness.is_complete
    ):
        return None
    try:
        return normalize_league(state.source.payload, state.source.endpoint)
    except EndpointPayloadRejected:
        return None


def _complete_nfl_records(
    states: Sequence[_AttemptState],
) -> NflStateEndpointRecords | None:
    state = states[-1]
    if (
        not isinstance(state.source, SuccessfulSourceAttempt)
        or not state.completeness.is_complete
    ):
        return None
    try:
        return normalize_nfl_state(state.source.payload, state.source.endpoint)
    except EndpointPayloadRejected:
        return None


def _build_outcome(
    refresh: RefreshRun,
    plan: PlannedRefresh,
    states: dict[ScopeKey, list[_AttemptState]],
) -> RefreshOutcome:
    results: list[ScopeRefreshResult] = []
    for endpoint in plan.requests:
        state = states[endpoint.scope_key][-1]
        stored = cast(ApiRequest, state.stored)
        warning_codes = list(state.warning_codes)
        if isinstance(state.source, FailedSourceAttempt):
            warning_codes.append(state.source.error.code)
        elif not state.completeness.is_complete:
            warning_codes.append(cast(str, state.completeness.reason))
        results.append(
            ScopeRefreshResult(
                scope_key=endpoint.scope_key,
                api_request_id=stored.id,
                fetch_status=stored.status,
                normalization_status=stored.normalization_status,
                changed_current_view=state.changed_current_view,
                warning_codes=tuple(dict.fromkeys(warning_codes)),
            )
        )
    return RefreshOutcome(
        refresh_run_id=refresh.id,
        status=refresh.status,
        effective_through_week=plan.through_week,
        requested_scope_count=refresh.request_count,
        succeeded_scope_count=refresh.succeeded_request_count,
        failed_scope_count=refresh.failed_request_count,
        scope_results=tuple(results),
    )
