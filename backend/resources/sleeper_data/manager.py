"""Short-transaction persistence boundary for Sleeper ingestion."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast as typing_cast
from uuid import UUID, uuid4

from sqlalchemy import Text, cast, delete, func, literal, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Session

from backend.database.models.core.competitions import CompetitionSeason
from backend.database.models.core.franchises import Franchise, SeasonRoster
from backend.database.models.sleeper.normalized import (
    DraftPick,
    League,
    LeagueUser,
    Matchup,
    Player,
    PlayerPerformance,
    PlayoffMatchup,
    Roster,
    RosterManager,
    RosterPlayer,
    Transaction,
    TransactionMove,
    User,
)
from backend.database.models.sleeper.requests import (
    ApiPayload as ApiPayloadRow,
    ApiRequest as ApiRequestRow,
    NormalizedScope,
    RefreshRun as RefreshRunRow,
)
from backend.database.sessions import (
    SessionFactory,
    read_only_session,
    transaction_session,
)
from backend.json import JsonValue, canonical_json_text, parse_json_text
from backend.resources.context import ManagerContext
from backend.resources.errors import (
    InvalidResourceCommand,
    ResourceConflict,
    ResourceNotFound,
    ResourceReferenceUnavailable,
)
from backend.sleeper import (
    EndpointKind,
    ScopeKey,
    expected_scope_key,
    infer_and_validate_scope_key,
)

from .objects import (
    ApiRequest,
    ApiRequestCandidate,
    ApplyDisposition,
    ApplyResult,
    ApplyScopeRecords,
    BracketScopeRecords,
    ExpandRefreshPlan,
    LeagueScopeRecords,
    LeagueSeasonOverview,
    LeagueUsersScopeRecords,
    MatchupState,
    MatchupsScopeRecords,
    NormalizationRejection,
    NormalizationStatus,
    NflStateScopeRecords,
    Page,
    PayloadReceipt,
    PlayerCatalogScopeRecords,
    PlayerSearch,
    PlayerValue,
    RecordApiAttempt,
    RefreshFailure,
    RefreshRun,
    RefreshScopePlan,
    RefreshStatus,
    RequestStatus,
    RostersScopeRecords,
    SeasonIdentityMap,
    SeasonRosterIdentity,
    SeasonRosterState,
    SnapshotCandidateQuery,
    StartRefresh,
    TradedPicksScopeRecords,
    TransactionQuery,
    TransactionState,
    TransactionsScopeRecords,
    VerifiedPayload,
)

Clock = Callable[[], datetime]


class SleeperDataManager:
    """Own request audit, scope application, and current Sleeper reads."""

    def __init__(
        self,
        session_factory: SessionFactory,
        context: ManagerContext,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._context = context
        self._clock = clock or _utc_now

    def get_season_identity_map(self, competition_season_id: UUID) -> SeasonIdentityMap:
        with read_only_session(self._session_factory) as session:
            season = self._season_in_scope(session, competition_season_id)
            roster_rows = session.execute(
                select(SeasonRoster)
                .where(SeasonRoster.competition_season_id == competition_season_id)
                .order_by(SeasonRoster.sleeper_roster_id)
            ).scalars()
            return SeasonIdentityMap(
                competition_id=season.competition_id,
                competition_season_id=season.id,
                sleeper_league_id=season.sleeper_league_id,
                season_year=season.season_year,
                roster_by_sleeper_id={
                    row.sleeper_roster_id: SeasonRosterIdentity(
                        season_roster_id=row.id,
                        franchise_id=row.franchise_id,
                    )
                    for row in roster_rows
                },
            )

    def start_refresh(self, command: StartRefresh) -> RefreshRun:
        if (
            command.requested_through_week is not None
            and not 1 <= command.requested_through_week <= 18
        ):
            raise InvalidResourceCommand(
                "requested through week must be between 1 and 18"
            )
        _validate_plan(
            command.endpoint_plan,
            competition_season_id=command.competition_season_id,
        )
        with transaction_session(self._session_factory) as session:
            season = self._season_in_scope(session, command.competition_season_id)
            row = RefreshRunRow(
                competition_id=season.competition_id,
                competition_season_id=season.id,
                requested_through_week=command.requested_through_week,
                endpoint_scope=_jsonb(
                    _plan_document(
                        command.endpoint_plan,
                        effective_through_week=command.requested_through_week,
                    )
                ),
                trigger_source=command.trigger_source,
                status=RefreshStatus.RUNNING.value,
                code_version=command.code_version,
                normalizer_version=command.normalizer_version,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return _refresh_object(row)

    def expand_refresh_plan(
        self,
        refresh_id: UUID,
        command: ExpandRefreshPlan,
    ) -> RefreshRun:
        if not 1 <= command.effective_through_week <= 18:
            raise InvalidResourceCommand("effective through week must be between 1 and 18")
        with transaction_session(self._session_factory) as session:
            row = self._refresh_in_scope(session, refresh_id, for_update=True)
            if row.status != RefreshStatus.RUNNING.value:
                raise ResourceConflict("only a running refresh plan can be expanded")
            if _effective_through_week(row.endpoint_scope) is not None:
                raise ResourceConflict("refresh plan has already resolved its through week")
            existing = _decode_plan(row.endpoint_scope)
            combined = (*existing, *command.remaining_scopes)
            if row.competition_season_id is None:
                raise ResourceConflict("refresh plan has no competition season")
            _validate_plan(
                combined,
                competition_season_id=row.competition_season_id,
            )
            row.endpoint_scope = _jsonb(
                _plan_document(
                    combined,
                    effective_through_week=command.effective_through_week,
                )
            )
            session.flush()
            return _refresh_object(row)

    def record_attempt(self, command: RecordApiAttempt) -> ApiRequest:
        _validate_attempt_scope(command)
        with transaction_session(self._session_factory) as session:
            refresh = self._refresh_in_scope(session, command.refresh_run_id, for_update=True)
            if refresh.status != RefreshStatus.RUNNING.value:
                raise ResourceConflict("API attempts can only be recorded on a running refresh")
            if refresh.competition_season_id != command.competition_season_id:
                raise InvalidResourceCommand("API attempt season does not match its refresh")
            planned = {item.scope_key: item for item in _decode_plan(refresh.endpoint_scope)}
            plan_item = planned.get(command.scope_key)
            if plan_item is None or plan_item.endpoint_kind != command.endpoint_kind:
                raise InvalidResourceCommand("API attempt is not present in the refresh plan")

            payload_id: UUID | None = None
            response_sha256: str | None = None
            if command.payload is not None:
                payload = command.payload
                _verify_inline_receipt(payload)
                payload_row = self._upsert_payload(session, payload)
                payload_id = payload_row.id
                response_sha256 = payload_row.sha256_hash

            row = ApiRequestRow(
                refresh_run_id=refresh.id,
                competition_season_id=refresh.competition_season_id,
                endpoint_kind=command.endpoint_kind,
                scope_key=command.scope_key,
                request_path=command.request_path,
                request_parameters=_jsonb(dict(command.request_parameters)),
                week=command.week,
                bracket_kind=command.bracket_kind,
                requested_at=command.requested_at,
                completed_at=command.completed_at,
                latency_ms=command.latency_ms,
                status=command.status.value,
                http_status=command.http_status,
                error=_jsonb(dict(command.error)) if command.error is not None else None,
                is_complete=command.completeness.is_complete,
                completeness_reason=(
                    f"{command.completeness.code}: {command.completeness.summary}"
                ),
                payload_id=payload_id,
                response_sha256=response_sha256,
                normalization_status=(
                    NormalizationStatus.PENDING.value
                    if command.status is RequestStatus.SUCCEEDED
                    and command.completeness.is_complete
                    else NormalizationStatus.NOT_APPLICABLE.value
                ),
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return _request_object(row)

    def reject_normalization(
        self,
        request_id: UUID,
        rejection: NormalizationRejection,
    ) -> ApiRequest:
        with transaction_session(self._session_factory) as session:
            row = self._request_in_scope(session, request_id, for_update=True)
            if row.normalization_status == NormalizationStatus.REJECTED.value:
                return _request_object(row)
            if row.status != RequestStatus.SUCCEEDED.value or not row.is_complete:
                raise InvalidResourceCommand(
                    "only a successful complete request can reject normalization"
                )
            refresh = self._refresh_in_scope(session, row.refresh_run_id)
            row.normalization_status = NormalizationStatus.REJECTED.value
            row.normalizer_version = refresh.normalizer_version
            row.normalized_at = self._clock()
            row.error = _jsonb(
                {
                    "code": rejection.code,
                    "summary": rejection.summary,
                    "stage": "normalization",
                }
            )
            session.flush()
            return _request_object(row)

    def apply_scope(
        self,
        request_id: UUID,
        records: ApplyScopeRecords,
    ) -> ApplyResult:
        with transaction_session(self._session_factory) as session:
            request = self._request_in_scope(session, request_id, for_update=True)
            self._assert_apply_eligible(session, request, records)
            _lock_key(session, f"scope:{request.scope_key}")
            head = session.get(NormalizedScope, request.scope_key, with_for_update=True)
            if head is not None and head.source_api_request_id == request.id:
                return ApplyResult(
                    disposition=ApplyDisposition.ALREADY_APPLIED,
                    request_id=request.id,
                    scope_key=request.scope_key,
                    normalized_row_count=head.normalized_row_count,
                )

            if head is not None:
                prior_request = session.get(ApiRequestRow, head.source_api_request_id)
                if prior_request is None:
                    raise ResourceConflict("normalized scope references a missing request")
                if _request_order(request) < _request_order(prior_request):
                    self._mark_normalized(session, request)
                    return ApplyResult(
                        disposition=ApplyDisposition.STALE_IGNORED,
                        request_id=request.id,
                        scope_key=request.scope_key,
                        normalized_row_count=head.normalized_row_count,
                    )
                if head.response_sha256 == request.response_sha256:
                    head.source_api_request_id = request.id
                    head.applied_at = self._clock()
                    self._mark_normalized(session, request)
                    return ApplyResult(
                        disposition=ApplyDisposition.IDENTICAL_HEAD_ADVANCED,
                        request_id=request.id,
                        scope_key=request.scope_key,
                        normalized_row_count=head.normalized_row_count,
                    )

            row_count = self._replace_scope(session, request, records)
            if head is None:
                head = NormalizedScope(
                    scope_key=request.scope_key,
                    source_api_request_id=request.id,
                    response_sha256=typing_cast(str, request.response_sha256),
                    normalized_row_count=row_count,
                    applied_at=self._clock(),
                )
                session.add(head)
            else:
                head.source_api_request_id = request.id
                head.response_sha256 = typing_cast(str, request.response_sha256)
                head.normalized_row_count = row_count
                head.applied_at = self._clock()
            self._mark_normalized(session, request)
            session.flush()
            return ApplyResult(
                disposition=ApplyDisposition.APPLIED,
                request_id=request.id,
                scope_key=request.scope_key,
                normalized_row_count=row_count,
            )

    def finish_refresh(
        self,
        refresh_id: UUID,
        *,
        cancelled: bool = False,
        failure: RefreshFailure | None = None,
    ) -> RefreshRun:
        if cancelled and failure is not None:
            raise InvalidResourceCommand(
                "refresh cannot be cancelled and failed at the same time"
            )
        with transaction_session(self._session_factory) as session:
            refresh = self._refresh_in_scope(session, refresh_id, for_update=True)
            if refresh.status != RefreshStatus.RUNNING.value:
                return _refresh_object(refresh)
            plan = _decode_plan(refresh.endpoint_scope)
            attempts = tuple(session.execute(
                select(ApiRequestRow).where(ApiRequestRow.refresh_run_id == refresh.id)
            ).scalars())
            summary = _derive_refresh_summary(plan, attempts, cancelled=cancelled)
            status = summary.status
            if failure is not None:
                status = (
                    RefreshStatus.PARTIAL
                    if summary.succeeded_scope_count
                    else RefreshStatus.FAILED
                )
            refresh.status = status.value
            refresh.completed_at = self._clock()
            refresh.request_count = len(attempts)
            refresh.succeeded_request_count = summary.succeeded_scope_count
            refresh.failed_request_count = summary.failed_scope_count
            error_summary: dict[str, JsonValue] = {}
            if summary.failed_scope_keys:
                error_summary["failed_scope_keys"] = list(summary.failed_scope_keys)
            if failure is not None:
                error_summary["refresh_failure"] = {
                    "code": failure.code,
                    "summary": failure.summary,
                }
            refresh.error_summary = _jsonb(error_summary) if error_summary else None
            session.flush()
            return _refresh_object(refresh)

    def get_refresh(self, refresh_id: UUID) -> RefreshRun:
        with read_only_session(self._session_factory) as session:
            return _refresh_object(self._refresh_in_scope(session, refresh_id))

    def list_refresh_requests(
        self,
        refresh_id: UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> Page[ApiRequest]:
        _validate_page(limit, offset)
        with read_only_session(self._session_factory) as session:
            refresh = self._refresh_in_scope(session, refresh_id)
            total = session.scalar(
                select(func.count()).select_from(ApiRequestRow).where(
                    ApiRequestRow.refresh_run_id == refresh.id
                )
            ) or 0
            rows = session.execute(
                select(ApiRequestRow)
                .where(ApiRequestRow.refresh_run_id == refresh.id)
                .order_by(ApiRequestRow.requested_at, ApiRequestRow.id)
                .limit(limit)
                .offset(offset)
            ).scalars()
            return Page(
                items=tuple(_request_object(row) for row in rows),
                limit=limit,
                offset=offset,
                total=total,
            )

    def list_snapshot_candidates(
        self,
        query: SnapshotCandidateQuery,
    ) -> tuple[ApiRequestCandidate, ...]:
        with read_only_session(self._session_factory) as session:
            self._season_in_scope(session, query.competition_season_id)
            rows = session.execute(
                select(ApiRequestRow)
                .where(
                    ApiRequestRow.competition_season_id == query.competition_season_id,
                    ApiRequestRow.status == RequestStatus.SUCCEEDED.value,
                    ApiRequestRow.is_complete.is_(True),
                    ApiRequestRow.payload_id.is_not(None),
                    ApiRequestRow.response_sha256.is_not(None),
                    ApiRequestRow.completed_at <= query.observed_through,
                )
                .order_by(
                    ApiRequestRow.scope_key,
                    ApiRequestRow.requested_at.desc(),
                    ApiRequestRow.id.desc(),
                )
            ).scalars()
            return tuple(_candidate_object(row) for row in rows)

    def resolve_verified_payloads(
        self,
        request_ids: Collection[UUID],
    ) -> tuple[VerifiedPayload, ...]:
        ordered_ids = tuple(dict.fromkeys(request_ids))
        if not ordered_ids:
            return ()
        with read_only_session(self._session_factory) as session:
            inline_text = cast(ApiPayloadRow.inline_payload, Text).label("inline_json_text")
            rows = session.execute(
                select(ApiRequestRow, ApiPayloadRow, inline_text)
                .join(ApiPayloadRow, ApiPayloadRow.id == ApiRequestRow.payload_id)
                .join(
                    CompetitionSeason,
                    CompetitionSeason.id == ApiRequestRow.competition_season_id,
                )
                .where(ApiRequestRow.id.in_(ordered_ids), self._competition_clause(CompetitionSeason.competition_id))
            ).all()
            by_id = {row.ApiRequest.id: row for row in rows}
            if missing := tuple(request_id for request_id in ordered_ids if request_id not in by_id):
                raise ResourceNotFound(f"payload requests not found in scope: {missing}")
            resolved: list[VerifiedPayload] = []
            for request_id in ordered_ids:
                result = by_id[request_id]
                request = result.ApiRequest
                payload = result.ApiPayload
                stored_jsonb_text = result.inline_json_text
                inline_json_text = None
                if stored_jsonb_text is not None:
                    inline_json_text = _verified_canonical_jsonb_text(
                        stored_jsonb_text,
                        expected_sha256=payload.sha256_hash,
                        expected_byte_length=payload.byte_length,
                    )
                resolved.append(
                    VerifiedPayload(
                        request_id=request.id,
                        endpoint_kind=request.endpoint_kind,
                        scope_key=request.scope_key,
                        response_sha256=payload.sha256_hash,
                        byte_length=payload.byte_length,
                        media_type=payload.media_type,
                        inline_json_text=inline_json_text,
                        local_storage_key=payload.object_storage_key,
                    )
                )
            return tuple(resolved)

    def get_season_overview(self, season_id: UUID) -> LeagueSeasonOverview:
        with read_only_session(self._session_factory) as session:
            season = self._season_in_scope(session, season_id)
            row = session.get(League, season_id)
            if row is None:
                raise ResourceNotFound("league season has no normalized Sleeper overview")
            return LeagueSeasonOverview(
                competition_id=season.competition_id,
                competition_season_id=season.id,
                name=row.name,
                season=row.season,
                status=row.status,
                playoff_start_week=row.playoff_start_week,
                playoff_team_count=row.playoff_team_count,
            )

    def get_roster(self, season_roster_id: UUID) -> SeasonRosterState:
        with read_only_session(self._session_factory) as session:
            row = session.execute(
                select(Roster)
                .join(CompetitionSeason, CompetitionSeason.id == Roster.competition_season_id)
                .where(Roster.season_roster_id == season_roster_id, self._competition_clause(CompetitionSeason.competition_id))
            ).scalar_one_or_none()
            if row is None:
                raise ResourceNotFound("season roster not found in manager scope")
            managers = tuple(
                session.scalars(
                    select(RosterManager.sleeper_user_id)
                    .where(RosterManager.season_roster_id == row.season_roster_id)
                    .order_by(RosterManager.source_order, RosterManager.sleeper_user_id)
                )
            )
            players = tuple(
                session.scalars(
                    select(RosterPlayer.sleeper_player_id)
                    .where(RosterPlayer.season_roster_id == row.season_roster_id)
                    .order_by(RosterPlayer.sleeper_player_id)
                )
            )
            return SeasonRosterState(
                season_roster_id=row.season_roster_id,
                competition_season_id=row.competition_season_id,
                record_string=row.record_string,
                wins=row.wins,
                losses=row.losses,
                ties=row.ties,
                points_for=row.points_for,
                points_against=row.points_against,
                manager_user_ids=managers,
                player_ids=players,
            )

    def list_matchups(self, season_id: UUID, week: int) -> tuple[MatchupState, ...]:
        with read_only_session(self._session_factory) as session:
            self._season_in_scope(session, season_id)
            rows = session.execute(
                select(Matchup)
                .where(Matchup.competition_season_id == season_id, Matchup.week == week)
                .order_by(Matchup.sleeper_matchup_id, Matchup.season_roster_id)
            ).scalars()
            return tuple(
                MatchupState(
                    competition_season_id=row.competition_season_id,
                    week=row.week,
                    season_roster_id=row.season_roster_id,
                    sleeper_matchup_id=row.sleeper_matchup_id,
                    points=row.points,
                )
                for row in rows
            )

    def list_transactions(self, query: TransactionQuery) -> tuple[TransactionState, ...]:
        for value in (query.week_from, query.week_to):
            if value is not None and not 1 <= value <= 18:
                raise InvalidResourceCommand(
                    "transaction query weeks must be between 1 and 18"
                )
        if (
            query.week_from is not None
            and query.week_to is not None
            and query.week_from > query.week_to
        ):
            raise InvalidResourceCommand(
                "transaction query week_from must not exceed week_to"
            )
        with read_only_session(self._session_factory) as session:
            self._season_in_scope(session, query.competition_season_id)
            conditions = [Transaction.competition_season_id == query.competition_season_id]
            if query.week_from is not None:
                conditions.append(Transaction.week >= query.week_from)
            if query.week_to is not None:
                conditions.append(Transaction.week <= query.week_to)
            rows = session.execute(
                select(Transaction)
                .where(*conditions)
                .order_by(Transaction.week, Transaction.provider_created_at_ms, Transaction.id)
            ).scalars()
            return tuple(
                TransactionState(
                    id=row.id,
                    competition_season_id=row.competition_season_id,
                    sleeper_transaction_id=row.sleeper_transaction_id,
                    week=row.week,
                    transaction_type=row.transaction_type,
                    status=row.status,
                )
                for row in rows
            )

    def search_players(self, query: PlayerSearch) -> Page[PlayerValue]:
        if not self._context.is_global:
            raise InvalidResourceCommand(
                "global player search requires an explicit global manager context"
            )
        _validate_page(query.limit, query.offset)
        needle = query.text.strip()
        if not needle:
            raise InvalidResourceCommand("player search text must not be empty")
        condition = Player.full_name.ilike(f"%{needle}%")
        with read_only_session(self._session_factory) as session:
            total = session.scalar(select(func.count()).select_from(Player).where(condition)) or 0
            rows = session.execute(
                select(Player)
                .where(condition)
                .order_by(Player.full_name, Player.sleeper_player_id)
                .limit(query.limit)
                .offset(query.offset)
            ).scalars()
            return Page(
                items=tuple(_player_object(row) for row in rows),
                limit=query.limit,
                offset=query.offset,
                total=total,
            )

    def _upsert_payload(
        self,
        session: Session,
        payload: PayloadReceipt,
    ) -> ApiPayloadRow:
        payload_id = uuid4()
        statement = insert(ApiPayloadRow).values(
            id=payload_id,
            sha256_hash=payload.sha256,
            byte_length=payload.byte_length,
            media_type=payload.media_type,
            storage_kind="inline_json" if payload.inline_json_text is not None else "object",
            inline_payload=(
                cast(literal(payload.inline_json_text), JSONB)
                if payload.inline_json_text is not None
                else None
            ),
            object_storage_key=payload.local_storage_key,
        ).on_conflict_do_nothing(index_elements=[ApiPayloadRow.sha256_hash])
        session.execute(statement)
        row = session.scalar(
            select(ApiPayloadRow)
            .where(ApiPayloadRow.sha256_hash == payload.sha256)
            .with_for_update()
        )
        if row is None:
            raise ResourceConflict("content-addressed payload could not be resolved")
        if row.byte_length != payload.byte_length:
            raise ResourceConflict("payload hash exists with a different byte length")
        return row

    def _assert_apply_eligible(
        self,
        session: Session,
        request: ApiRequestRow,
        records: ApplyScopeRecords,
    ) -> None:
        if (
            request.status != RequestStatus.SUCCEEDED.value
            or not request.is_complete
            or request.payload_id is None
            or request.response_sha256 is None
        ):
            raise InvalidResourceCommand("request is not eligible for normalization")
        if request.normalization_status == NormalizationStatus.REJECTED.value:
            raise ResourceConflict("a rejected request cannot be applied")
        expected_kind = _records_endpoint_kind(records)
        if request.endpoint_kind != expected_kind.value:
            raise InvalidResourceCommand("endpoint records do not match the source request")
        if isinstance(records, (MatchupsScopeRecords, TransactionsScopeRecords)):
            if records.week != request.week:
                raise InvalidResourceCommand("endpoint record week does not match request scope")
        if isinstance(records, BracketScopeRecords) and records.bracket_kind != request.bracket_kind:
            raise InvalidResourceCommand("bracket records do not match request scope")
        payload = session.get(ApiPayloadRow, request.payload_id)
        if payload is None or payload.sha256_hash != request.response_sha256:
            raise ResourceConflict("request payload receipt is not verified")

    def _replace_scope(
        self,
        session: Session,
        request: ApiRequestRow,
        records: ApplyScopeRecords,
    ) -> int:
        if isinstance(records, LeagueScopeRecords):
            return self._apply_league(session, request, records)
        if isinstance(records, LeagueUsersScopeRecords):
            return self._apply_users(session, request, records)
        if isinstance(records, PlayerCatalogScopeRecords):
            return self._apply_players(session, request, records)
        if isinstance(records, NflStateScopeRecords):
            return 0
        if isinstance(records, RostersScopeRecords):
            return self._apply_rosters(session, request, records)
        if isinstance(records, MatchupsScopeRecords):
            return self._apply_matchups(session, request, records)
        if isinstance(records, TransactionsScopeRecords):
            return self._apply_transactions(session, request, records)
        if isinstance(records, TradedPicksScopeRecords):
            return self._apply_traded_picks(session, request, records)
        return self._apply_bracket(session, request, records)

    def _apply_league(self, session: Session, request: ApiRequestRow, records: LeagueScopeRecords) -> int:
        season = self._season_in_scope(session, typing_cast(UUID, request.competition_season_id))
        value = records.league
        if value.sleeper_league_id != season.sleeper_league_id:
            raise InvalidResourceCommand("league payload does not match mapped Sleeper league")
        statement = insert(League).values(
            competition_season_id=season.id,
            source_api_request_id=request.id,
            name=value.name,
            status=value.status,
            season=value.season,
            previous_sleeper_league_id=value.previous_sleeper_league_id,
            sleeper_draft_id=value.sleeper_draft_id,
            sport=value.sport,
            scoring_settings=_jsonb(dict(value.scoring_settings)),
            roster_positions=_jsonb(list(value.roster_positions)),
            provider_settings=_jsonb(dict(value.provider_settings)),
            playoff_start_week=value.playoff_start_week,
            playoff_team_count=value.playoff_team_count,
            league_average_match=value.league_average_match,
        ).on_conflict_do_update(
            index_elements=[League.competition_season_id],
            set_={
                "source_api_request_id": request.id,
                "name": value.name,
                "status": value.status,
                "season": value.season,
                "previous_sleeper_league_id": value.previous_sleeper_league_id,
                "sleeper_draft_id": value.sleeper_draft_id,
                "sport": value.sport,
                "scoring_settings": _jsonb(dict(value.scoring_settings)),
                "roster_positions": _jsonb(list(value.roster_positions)),
                "provider_settings": _jsonb(dict(value.provider_settings)),
                "playoff_start_week": value.playoff_start_week,
                "playoff_team_count": value.playoff_team_count,
                "league_average_match": value.league_average_match,
                "updated_at": self._clock(),
            },
        )
        session.execute(statement)
        return 1

    def _apply_users(self, session: Session, request: ApiRequestRow, records: LeagueUsersScopeRecords) -> int:
        season_id = typing_cast(UUID, request.competition_season_id)
        self._season_in_scope(session, season_id)
        supplied_user_ids = {user.sleeper_user_id for user in records.users}
        if any(
            league_user.sleeper_user_id not in supplied_user_ids
            for league_user in records.league_users
        ):
            raise InvalidResourceCommand(
                "league-user rows must have a profile in the same complete response"
            )
        user_ids = tuple(sorted(user.sleeper_user_id for user in records.users))
        for user_id in user_ids:
            _lock_key(session, f"user:{user_id}")
        existing = {
            user.sleeper_user_id: user
            for user in session.execute(select(User).where(User.sleeper_user_id.in_(user_ids))).scalars()
        }
        for value in records.users:
            current = existing.get(value.sleeper_user_id)
            if current is not None:
                current_request = session.get(ApiRequestRow, current.source_api_request_id)
                if current_request is not None and _request_order(request) < _request_order(current_request):
                    continue
            statement = insert(User).values(
                sleeper_user_id=value.sleeper_user_id,
                display_name=value.display_name,
                username=value.username,
                avatar=value.avatar,
                metadata_json=_jsonb(dict(value.metadata)),
                source_api_request_id=request.id,
            ).on_conflict_do_update(
                index_elements=[User.sleeper_user_id],
                set_={
                    "display_name": value.display_name,
                    "username": value.username,
                    "avatar": value.avatar,
                    "metadata": _jsonb(dict(value.metadata)),
                    "source_api_request_id": request.id,
                    "updated_at": self._clock(),
                },
            )
            session.execute(statement)
        session.execute(delete(LeagueUser).where(LeagueUser.competition_season_id == season_id))
        session.add_all(
            LeagueUser(
                competition_season_id=season_id,
                sleeper_user_id=value.sleeper_user_id,
                team_name=value.team_name,
                nickname=value.nickname,
                is_commissioner=value.is_commissioner,
                metadata_json=_jsonb(dict(value.metadata)),
                source_api_request_id=request.id,
            )
            for value in records.league_users
        )
        return len(records.users) + len(records.league_users)

    def _apply_players(self, session: Session, request: ApiRequestRow, records: PlayerCatalogScopeRecords) -> int:
        for value in records.players:
            statement = insert(Player).values(
                sleeper_player_id=value.sleeper_player_id,
                full_name=value.full_name,
                position=value.position,
                nfl_team=value.nfl_team,
                active=value.active,
                status=value.status,
                injury_status=value.injury_status,
                age=value.age,
                years_experience=value.years_experience,
                metadata_json=_jsonb(dict(value.metadata)),
                source_api_request_id=request.id,
            ).on_conflict_do_update(
                index_elements=[Player.sleeper_player_id],
                set_={
                    "full_name": value.full_name,
                    "position": value.position,
                    "nfl_team": value.nfl_team,
                    "active": value.active,
                    "status": value.status,
                    "injury_status": value.injury_status,
                    "age": value.age,
                    "years_experience": value.years_experience,
                    "metadata": _jsonb(dict(value.metadata)),
                    "source_api_request_id": request.id,
                    "updated_at": self._clock(),
                },
            )
            session.execute(statement)
        return len(records.players)

    def _apply_rosters(self, session: Session, request: ApiRequestRow, records: RostersScopeRecords) -> int:
        season_id = typing_cast(UUID, request.competition_season_id)
        season = self._season_in_scope(session, season_id)
        roster_ids = {value.season_roster_id for value in records.rosters}
        child_roster_ids = {
            *(value.season_roster_id for value in records.managers),
            *(value.season_roster_id for value in records.players),
        }
        if not child_roster_ids.issubset(roster_ids):
            raise InvalidResourceCommand(
                "roster children must reference a roster in the same response"
            )
        _require_season_rosters(session, roster_ids, season_id=season_id)
        _require_users(
            session,
            {value.sleeper_user_id for value in records.managers},
        )
        _require_players(
            session,
            {value.sleeper_player_id for value in records.players},
        )
        _require_franchises(
            session,
            {
                franchise_id
                for value in records.draft_pick_seeds
                for franchise_id in (
                    value.original_franchise_id,
                    value.current_franchise_id,
                )
            },
            competition_id=season.competition_id,
        )
        _lock_key(session, f"draft-picks:{season.competition_id}")
        session.execute(delete(RosterManager).where(RosterManager.competition_season_id == season_id))
        session.execute(delete(RosterPlayer).where(RosterPlayer.competition_season_id == season_id))
        session.execute(delete(Roster).where(Roster.competition_season_id == season_id))
        for value in records.rosters:
            statement = insert(Roster).values(
                season_roster_id=value.season_roster_id,
                competition_season_id=season_id,
                source_api_request_id=request.id,
                settings_json=_jsonb(dict(value.settings)),
                metadata_json=_jsonb(dict(value.metadata)),
                record_string=value.record_string,
                wins=value.wins,
                losses=value.losses,
                ties=value.ties,
                points_for=value.points_for,
                points_against=value.points_against,
            ).on_conflict_do_update(
                index_elements=[Roster.season_roster_id],
                set_={
                    "source_api_request_id": request.id,
                    "settings": _jsonb(dict(value.settings)),
                    "metadata": _jsonb(dict(value.metadata)),
                    "record_string": value.record_string,
                    "wins": value.wins,
                    "losses": value.losses,
                    "ties": value.ties,
                    "points_for": value.points_for,
                    "points_against": value.points_against,
                    "updated_at": self._clock(),
                },
            )
            session.execute(statement)
        session.add_all(
            RosterManager(
                season_roster_id=value.season_roster_id,
                competition_season_id=season_id,
                sleeper_user_id=value.sleeper_user_id,
                role=value.role,
                source_order=value.source_order,
                source_api_request_id=request.id,
            )
            for value in records.managers
        )
        session.add_all(
            RosterPlayer(
                season_roster_id=value.season_roster_id,
                competition_season_id=season_id,
                sleeper_player_id=value.sleeper_player_id,
                role=value.role,
                source_api_request_id=request.id,
            )
            for value in records.players
        )
        for value in records.draft_pick_seeds:
            session.execute(
                insert(DraftPick).values(
                    competition_id=season.competition_id,
                    draft_season_year=value.draft_season_year,
                    round=value.round,
                    original_franchise_id=value.original_franchise_id,
                    current_franchise_id=value.current_franchise_id,
                    sleeper_pick_id=None,
                    source="seed",
                    source_api_request_id=request.id,
                    source_api_request_competition_season_id=season_id,
                ).on_conflict_do_nothing(
                    index_elements=[
                        DraftPick.competition_id,
                        DraftPick.draft_season_year,
                        DraftPick.round,
                        DraftPick.original_franchise_id,
                    ]
                )
            )
        return (
            len(records.rosters)
            + len(records.managers)
            + len(records.players)
            + len(records.draft_pick_seeds)
        )

    def _apply_matchups(self, session: Session, request: ApiRequestRow, records: MatchupsScopeRecords) -> int:
        season_id = typing_cast(UUID, request.competition_season_id)
        _require_season_rosters(
            session,
            {
                *(value.season_roster_id for value in records.matchups),
                *(
                    value.season_roster_id
                    for value in records.player_performances
                ),
            },
            season_id=season_id,
        )
        _require_players(
            session,
            {
                value.sleeper_player_id
                for value in records.player_performances
            },
        )
        session.execute(delete(PlayerPerformance).where(PlayerPerformance.competition_season_id == season_id, PlayerPerformance.week == records.week))
        session.execute(delete(Matchup).where(Matchup.competition_season_id == season_id, Matchup.week == records.week))
        session.add_all(
            Matchup(
                competition_season_id=season_id,
                week=records.week,
                season_roster_id=value.season_roster_id,
                sleeper_matchup_id=value.sleeper_matchup_id,
                points=value.points,
                source_api_request_id=request.id,
            )
            for value in records.matchups
        )
        session.add_all(
            PlayerPerformance(
                competition_season_id=season_id,
                week=records.week,
                season_roster_id=value.season_roster_id,
                sleeper_matchup_id=value.sleeper_matchup_id,
                sleeper_player_id=value.sleeper_player_id,
                points=value.points,
                role=value.role,
                source_api_request_id=request.id,
            )
            for value in records.player_performances
        )
        return len(records.matchups) + len(records.player_performances)

    def _apply_transactions(self, session: Session, request: ApiRequestRow, records: TransactionsScopeRecords) -> int:
        season_id = typing_cast(UUID, request.competition_season_id)
        season = self._season_in_scope(session, season_id)
        moves = tuple(
            move
            for transaction in records.transactions
            for move in transaction.moves
        )
        _require_season_rosters(
            session,
            {
                roster_id
                for move in moves
                for roster_id in (
                    move.from_season_roster_id,
                    move.to_season_roster_id,
                )
                if roster_id is not None
            },
            season_id=season_id,
        )
        _require_players(
            session,
            {
                move.sleeper_player_id
                for move in moves
                if move.sleeper_player_id is not None
            },
        )
        _require_franchises(
            session,
            {
                move.original_franchise_id
                for move in moves
                if move.original_franchise_id is not None
            },
            competition_id=season.competition_id,
        )
        _lock_key(session, f"draft-picks:{season.competition_id}")
        old_ids = select(Transaction.id).where(Transaction.competition_season_id == season_id, Transaction.week == records.week)
        session.execute(delete(TransactionMove).where(TransactionMove.transaction_id.in_(old_ids)))
        session.execute(delete(Transaction).where(Transaction.competition_season_id == season_id, Transaction.week == records.week))
        move_count = 0
        for value in records.transactions:
            transaction_id = uuid4()
            session.add(
                Transaction(
                    id=transaction_id,
                    competition_season_id=season_id,
                    sleeper_transaction_id=value.sleeper_transaction_id,
                    week=records.week,
                    transaction_type=value.transaction_type,
                    status=value.status,
                    provider_created_at_ms=value.provider_created_at_ms,
                    settings_json=_jsonb(dict(value.settings)),
                    metadata_json=_jsonb(dict(value.metadata)),
                    source_api_request_id=request.id,
                )
            )
            for move in value.moves:
                draft_pick_id = None
                if move.move_kind == "pick":
                    if None in (move.draft_season_year, move.draft_round, move.original_franchise_id):
                        raise InvalidResourceCommand("pick move is missing its draft-pick coordinates")
                    draft_pick = session.execute(
                        select(DraftPick).where(
                            DraftPick.competition_id == season.competition_id,
                            DraftPick.draft_season_year == move.draft_season_year,
                            DraftPick.round == move.draft_round,
                            DraftPick.original_franchise_id == move.original_franchise_id,
                        ).with_for_update()
                    ).scalar_one_or_none()
                    # Transactions retain historical movement; traded-picks alone
                    # owns the mutable current-franchise projection.
                    if draft_pick is None:
                        draft_pick = DraftPick(
                            competition_id=season.competition_id,
                            draft_season_year=typing_cast(int, move.draft_season_year),
                            round=typing_cast(int, move.draft_round),
                            original_franchise_id=typing_cast(
                                UUID, move.original_franchise_id
                            ),
                            current_franchise_id=typing_cast(
                                UUID, move.original_franchise_id
                            ),
                            sleeper_pick_id=move.sleeper_pick_id,
                            source="transaction_identity",
                            source_api_request_id=request.id,
                            source_api_request_competition_season_id=season_id,
                        )
                        session.add(draft_pick)
                        session.flush()
                    draft_pick_id = draft_pick.id
                session.add(
                    TransactionMove(
                        transaction_id=transaction_id,
                        competition_season_id=season_id,
                        competition_id=season.competition_id,
                        move_index=move.move_index,
                        move_kind=move.move_kind,
                        from_season_roster_id=move.from_season_roster_id,
                        to_season_roster_id=move.to_season_roster_id,
                        sleeper_player_id=move.sleeper_player_id,
                        draft_pick_id=draft_pick_id,
                        budget_amount=move.budget_amount,
                    )
                )
                move_count += 1
        return len(records.transactions) + move_count

    def _apply_traded_picks(self, session: Session, request: ApiRequestRow, records: TradedPicksScopeRecords) -> int:
        season_id = typing_cast(UUID, request.competition_season_id)
        season = self._season_in_scope(session, season_id)
        _require_franchises(
            session,
            {
                franchise_id
                for value in records.picks
                for franchise_id in (
                    value.original_franchise_id,
                    value.current_franchise_id,
                )
            },
            competition_id=season.competition_id,
        )
        _lock_key(session, f"draft-picks:{season.competition_id}")
        incoming_by_coordinate = {
            (
                value.draft_season_year,
                value.round,
                value.original_franchise_id,
            ): value
            for value in records.picks
        }
        existing = tuple(
            session.execute(
                select(DraftPick)
                .where(DraftPick.competition_id == season.competition_id)
                .order_by(
                    DraftPick.draft_season_year,
                    DraftPick.round,
                    DraftPick.original_franchise_id,
                )
                .with_for_update()
            ).scalars()
        )
        existing_by_coordinate = {
            (
                row.draft_season_year,
                row.round,
                row.original_franchise_id,
            ): row
            for row in existing
        }
        for coordinate, row in existing_by_coordinate.items():
            if (
                coordinate not in incoming_by_coordinate
                and row.draft_season_year > season.season_year
                and row.current_franchise_id != row.original_franchise_id
                and _request_can_replace_draft_source(
                    session,
                    request=request,
                    current=row,
                    incoming_season_year=season.season_year,
                )
            ):
                row.current_franchise_id = row.original_franchise_id
                row.sleeper_pick_id = None
                row.source = "traded_picks_reset"
                row.source_api_request_id = request.id
                row.source_api_request_competition_season_id = season_id
        for value in records.picks:
            coordinate = (
                value.draft_season_year,
                value.round,
                value.original_franchise_id,
            )
            row = existing_by_coordinate.get(coordinate)
            if row is None:
                session.add(
                    DraftPick(
                    competition_id=season.competition_id,
                    draft_season_year=value.draft_season_year,
                    round=value.round,
                    original_franchise_id=value.original_franchise_id,
                    current_franchise_id=value.current_franchise_id,
                    sleeper_pick_id=value.sleeper_pick_id,
                    source="trade",
                    source_api_request_id=request.id,
                    source_api_request_competition_season_id=season_id,
                    )
                )
            elif _request_can_replace_draft_source(
                session,
                request=request,
                current=row,
                incoming_season_year=season.season_year,
            ):
                row.current_franchise_id = value.current_franchise_id
                row.sleeper_pick_id = value.sleeper_pick_id
                row.source = "trade"
                row.source_api_request_id = request.id
                row.source_api_request_competition_season_id = season_id
        return len(records.picks)

    def _apply_bracket(self, session: Session, request: ApiRequestRow, records: BracketScopeRecords) -> int:
        season_id = typing_cast(UUID, request.competition_season_id)
        _require_season_rosters(
            session,
            {
                roster_id
                for value in records.matchups
                for roster_id in (
                    value.t1_season_roster_id,
                    value.t2_season_roster_id,
                    value.winner_season_roster_id,
                    value.loser_season_roster_id,
                )
                if roster_id is not None
            },
            season_id=season_id,
        )
        session.execute(delete(PlayoffMatchup).where(PlayoffMatchup.competition_season_id == season_id, PlayoffMatchup.bracket_kind == records.bracket_kind))
        session.add_all(
            PlayoffMatchup(
                competition_season_id=season_id,
                bracket_kind=records.bracket_kind,
                node_key=value.node_key,
                round=value.round,
                t1_season_roster_id=value.t1_season_roster_id,
                t2_season_roster_id=value.t2_season_roster_id,
                t1_from_node_key=value.t1_from_node_key,
                t1_from_outcome=value.t1_from_outcome,
                t2_from_node_key=value.t2_from_node_key,
                t2_from_outcome=value.t2_from_outcome,
                winner_season_roster_id=value.winner_season_roster_id,
                loser_season_roster_id=value.loser_season_roster_id,
                placement=value.placement,
                source_api_request_id=request.id,
            )
            for value in records.matchups
        )
        return len(records.matchups)

    def _mark_normalized(self, session: Session, request: ApiRequestRow) -> None:
        refresh = session.get(RefreshRunRow, request.refresh_run_id)
        if refresh is None:
            raise ResourceConflict("request refresh is missing")
        request.normalization_status = NormalizationStatus.SUCCEEDED.value
        request.normalizer_version = refresh.normalizer_version
        request.normalized_at = self._clock()

    def _season_in_scope(self, session: Session, season_id: UUID) -> CompetitionSeason:
        self._require_competition_scope()
        row = session.execute(
            select(CompetitionSeason).where(
                CompetitionSeason.id == season_id,
                self._competition_clause(CompetitionSeason.competition_id),
            )
        ).scalar_one_or_none()
        if row is None:
            raise ResourceNotFound("competition season not found in manager scope")
        return row

    def _refresh_in_scope(self, session: Session, refresh_id: UUID, *, for_update: bool = False) -> RefreshRunRow:
        self._require_competition_scope()
        statement = (
            select(RefreshRunRow)
            .where(
                RefreshRunRow.id == refresh_id,
                self._competition_clause(RefreshRunRow.competition_id),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        row = session.execute(statement).scalar_one_or_none()
        if row is None:
            raise ResourceNotFound("refresh run not found in manager scope")
        return row

    def _request_in_scope(self, session: Session, request_id: UUID, *, for_update: bool = False) -> ApiRequestRow:
        self._require_competition_scope()
        statement = (
            select(ApiRequestRow)
            .join(RefreshRunRow, RefreshRunRow.id == ApiRequestRow.refresh_run_id)
            .where(
                ApiRequestRow.id == request_id,
                self._competition_clause(RefreshRunRow.competition_id),
            )
        )
        if for_update:
            statement = statement.with_for_update(of=ApiRequestRow)
        row = session.execute(statement).scalar_one_or_none()
        if row is None:
            raise ResourceNotFound("API request not found in manager scope")
        return row

    def _competition_clause(self, column: object) -> object:
        if self._context.competition_id is None:
            return literal(True)
        return column == self._context.competition_id

    def _require_competition_scope(self) -> None:
        if self._context.competition_id is None:
            raise InvalidResourceCommand(
                "this Sleeper operation requires competition-scoped manager context"
            )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _jsonb(value: JsonValue) -> object:
    return cast(literal(canonical_json_text(value)), JSONB)


def _plan_document(
    plan: Sequence[RefreshScopePlan],
    *,
    effective_through_week: int | None,
) -> JsonValue:
    return {
        "effective_through_week": effective_through_week,
        "scopes": [
            {
                "scope_key": item.scope_key,
                "endpoint_kind": item.endpoint_kind,
                "required": item.required,
                "dependency_scope_keys": list(item.dependency_scope_keys),
            }
            for item in plan
        ]
    }


def _effective_through_week(value: Mapping[str, object]) -> int | None:
    week = value.get("effective_through_week")
    if week is None:
        return None
    if isinstance(week, bool) or not isinstance(week, int) or not 1 <= week <= 18:
        raise ResourceConflict("refresh effective through week is malformed")
    return week


def _decode_plan(value: Mapping[str, object]) -> tuple[RefreshScopePlan, ...]:
    raw_scopes = value.get("scopes")
    if not isinstance(raw_scopes, list):
        raise ResourceConflict("refresh plan is malformed")
    result: list[RefreshScopePlan] = []
    for raw in raw_scopes:
        if not isinstance(raw, dict):
            raise ResourceConflict("refresh plan entry is malformed")
        dependencies = raw.get("dependency_scope_keys", [])
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            raise ResourceConflict("refresh plan dependencies are malformed")
        if not isinstance(raw.get("scope_key"), str) or not isinstance(raw.get("endpoint_kind"), str) or not isinstance(raw.get("required"), bool):
            raise ResourceConflict("refresh plan entry is malformed")
        result.append(
            RefreshScopePlan(
                scope_key=raw["scope_key"],
                endpoint_kind=raw["endpoint_kind"],
                required=raw["required"],
                dependency_scope_keys=tuple(dependencies),
            )
        )
    return tuple(result)


def _validate_plan(
    plan: Sequence[RefreshScopePlan],
    *,
    competition_season_id: UUID,
) -> None:
    scope_keys = [item.scope_key for item in plan]
    if len(scope_keys) != len(set(scope_keys)):
        raise InvalidResourceCommand("refresh plan contains duplicate scope keys")
    seen: set[str] = set()
    for item in plan:
        if not item.scope_key or not item.endpoint_kind:
            raise InvalidResourceCommand("refresh plan scope and endpoint must not be empty")
        try:
            infer_and_validate_scope_key(
                EndpointKind(item.endpoint_kind),
                ScopeKey.parse(item.scope_key),
                competition_season_id,
            )
        except ValueError as error:
            raise InvalidResourceCommand(
                "refresh plan endpoint kind and scope do not agree"
            ) from error
        if item.scope_key in item.dependency_scope_keys:
            raise InvalidResourceCommand("refresh scope cannot depend on itself")
        if any(dependency not in seen for dependency in item.dependency_scope_keys):
            raise InvalidResourceCommand(
                "refresh plan dependencies must precede their dependent scope"
            )
        seen.add(item.scope_key)


def _validate_attempt_scope(command: RecordApiAttempt) -> None:
    try:
        endpoint_kind = EndpointKind(command.endpoint_kind)
        scope_key = ScopeKey.parse(command.scope_key)
        expected = expected_scope_key(
            endpoint_kind,
            command.competition_season_id,
            week=command.week,
            bracket_kind=command.bracket_kind,
        )
    except ValueError as error:
        raise InvalidResourceCommand("API attempt endpoint metadata is invalid") from error
    if scope_key != expected:
        raise InvalidResourceCommand(
            "API attempt endpoint kind and scope key do not agree"
        )


def _verify_inline_receipt(payload: PayloadReceipt) -> None:
    if payload.inline_json_text is None:
        return
    parsed = parse_json_text(payload.inline_json_text)
    canonical = canonical_json_text(parsed)
    if canonical != payload.inline_json_text:
        raise InvalidResourceCommand("inline payload text is not canonical JSON")
    _verify_payload_text(
        canonical,
        expected_sha256=payload.sha256,
        expected_byte_length=payload.byte_length,
    )


def _verify_payload_text(content: str, *, expected_sha256: str, expected_byte_length: int) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) != expected_byte_length or sha256(encoded).hexdigest() != expected_sha256:
        raise ResourceConflict("payload content does not match its hash and size receipt")


def _verified_canonical_jsonb_text(
    stored_text: str,
    *,
    expected_sha256: str,
    expected_byte_length: int,
) -> str:
    """Recover canonical bytes from PostgreSQL's non-canonical JSONB text."""

    canonical = canonical_json_text(parse_json_text(stored_text))
    _verify_payload_text(
        canonical,
        expected_sha256=expected_sha256,
        expected_byte_length=expected_byte_length,
    )
    return canonical


def _lock_key(session: Session, value: str) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": value},
    )


def _request_order(request: ApiRequestRow) -> tuple[datetime, int]:
    return request.requested_at, request.id.int


def _require_season_rosters(
    session: Session,
    season_roster_ids: set[UUID],
    *,
    season_id: UUID,
) -> None:
    if not season_roster_ids:
        return
    found = set(
        session.scalars(
            select(SeasonRoster.id).where(
                SeasonRoster.id.in_(season_roster_ids),
                SeasonRoster.competition_season_id == season_id,
            )
        )
    )
    if found != season_roster_ids:
        raise ResourceReferenceUnavailable(
            "endpoint records reference an unmapped season roster"
        )


def _require_users(session: Session, sleeper_user_ids: set[str]) -> None:
    if not sleeper_user_ids:
        return
    found = set(
        session.scalars(
            select(User.sleeper_user_id).where(
                User.sleeper_user_id.in_(sleeper_user_ids)
            )
        )
    )
    if found != sleeper_user_ids:
        raise ResourceReferenceUnavailable(
            "endpoint records reference an unavailable Sleeper user"
        )


def _require_players(session: Session, sleeper_player_ids: set[str]) -> None:
    if not sleeper_player_ids:
        return
    found = set(
        session.scalars(
            select(Player.sleeper_player_id).where(
                Player.sleeper_player_id.in_(sleeper_player_ids)
            )
        )
    )
    if found != sleeper_player_ids:
        raise ResourceReferenceUnavailable(
            "endpoint records reference an unavailable Sleeper player"
        )


def _require_franchises(
    session: Session,
    franchise_ids: set[UUID],
    *,
    competition_id: UUID,
) -> None:
    if not franchise_ids:
        return
    found = set(
        session.scalars(
            select(Franchise.id).where(
                Franchise.id.in_(franchise_ids),
                Franchise.competition_id == competition_id,
            )
        )
    )
    if found != franchise_ids:
        raise ResourceReferenceUnavailable(
            "endpoint records reference a franchise outside the competition"
        )


def _request_can_replace_draft_source(
    session: Session,
    *,
    request: ApiRequestRow,
    current: DraftPick,
    incoming_season_year: int,
) -> bool:
    if (
        current.source_api_request_id is None
        or current.source_api_request_competition_season_id is None
    ):
        return True
    current_request = session.get(ApiRequestRow, current.source_api_request_id)
    current_season = session.get(
        CompetitionSeason,
        current.source_api_request_competition_season_id,
    )
    if current_request is None or current_season is None:
        raise ResourceConflict("draft pick references missing source authority")
    incoming_authority = (
        incoming_season_year,
        request.requested_at,
        request.id.int,
    )
    current_authority = (
        current_season.season_year,
        current_request.requested_at,
        current_request.id.int,
    )
    return incoming_authority >= current_authority


def _records_endpoint_kind(records: ApplyScopeRecords) -> EndpointKind:
    if isinstance(records, LeagueScopeRecords):
        return EndpointKind.LEAGUE
    if isinstance(records, LeagueUsersScopeRecords):
        return EndpointKind.LEAGUE_USERS
    if isinstance(records, PlayerCatalogScopeRecords):
        return EndpointKind.PLAYER_CATALOG
    if isinstance(records, NflStateScopeRecords):
        return EndpointKind.NFL_STATE
    if isinstance(records, RostersScopeRecords):
        return EndpointKind.LEAGUE_ROSTERS
    if isinstance(records, MatchupsScopeRecords):
        return EndpointKind.MATCHUPS
    if isinstance(records, TransactionsScopeRecords):
        return EndpointKind.TRANSACTIONS
    if isinstance(records, TradedPicksScopeRecords):
        return EndpointKind.TRADED_PICKS
    if records.bracket_kind == "winners":
        return EndpointKind.WINNERS_BRACKET
    return EndpointKind.LOSERS_BRACKET


@dataclass(frozen=True, slots=True)
class _RefreshSummary:
    status: RefreshStatus
    succeeded_scope_count: int
    failed_scope_count: int
    failed_scope_keys: tuple[str, ...]


def _derive_refresh_summary(
    plan: Sequence[RefreshScopePlan],
    attempts: Sequence[ApiRequestRow],
    *,
    cancelled: bool,
) -> _RefreshSummary:
    latest: dict[str, ApiRequestRow] = {}
    for attempt in attempts:
        current = latest.get(attempt.scope_key)
        if current is None or _request_order(attempt) > _request_order(current):
            latest[attempt.scope_key] = attempt

    succeeded = 0
    failed: list[str] = []
    failed_required: list[str] = []
    for item in plan:
        attempt = latest.get(item.scope_key)
        scope_succeeded = (
            attempt is not None
            and attempt.status == RequestStatus.SUCCEEDED.value
            and attempt.is_complete
            and attempt.normalization_status
            in {
                NormalizationStatus.SUCCEEDED.value,
                NormalizationStatus.NOT_APPLICABLE.value,
            }
        )
        if scope_succeeded:
            succeeded += 1
        elif not cancelled or attempt is not None:
            failed.append(item.scope_key)
            if item.required:
                failed_required.append(item.scope_key)

    if cancelled:
        status = RefreshStatus.CANCELLED
    elif not failed_required:
        status = RefreshStatus.SUCCEEDED
    elif succeeded:
        status = RefreshStatus.PARTIAL
    else:
        status = RefreshStatus.FAILED
    return _RefreshSummary(
        status=status,
        succeeded_scope_count=succeeded,
        failed_scope_count=len(failed),
        failed_scope_keys=tuple(failed),
    )


def _refresh_object(row: RefreshRunRow) -> RefreshRun:
    if row.competition_id is None or row.competition_season_id is None:
        raise ResourceConflict("refresh row has no competition season scope")
    return RefreshRun(
        id=row.id,
        competition_id=row.competition_id,
        competition_season_id=row.competition_season_id,
        requested_through_week=row.requested_through_week,
        effective_through_week=_effective_through_week(row.endpoint_scope),
        endpoint_plan=_decode_plan(row.endpoint_scope),
        trigger_source=row.trigger_source,
        status=RefreshStatus(row.status),
        code_version=row.code_version,
        normalizer_version=row.normalizer_version,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_summary=row.error_summary,
        attempt_count=row.request_count,
        succeeded_scope_count=row.succeeded_request_count,
        failed_scope_count=row.failed_request_count,
    )


def _request_object(row: ApiRequestRow) -> ApiRequest:
    if row.competition_season_id is None:
        raise ResourceConflict("API request has no competition season scope")
    return ApiRequest(
        id=row.id,
        refresh_run_id=row.refresh_run_id,
        competition_season_id=row.competition_season_id,
        endpoint_kind=row.endpoint_kind,
        scope_key=row.scope_key,
        request_path=row.request_path,
        request_parameters=row.request_parameters,
        week=row.week,
        bracket_kind=row.bracket_kind,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
        latency_ms=row.latency_ms,
        status=RequestStatus(row.status),
        http_status=row.http_status,
        error=row.error,
        is_complete=row.is_complete,
        completeness_reason=row.completeness_reason,
        response_sha256=row.response_sha256,
        normalization_status=NormalizationStatus(row.normalization_status),
        normalizer_version=row.normalizer_version,
        normalized_at=row.normalized_at,
    )


def _candidate_object(row: ApiRequestRow) -> ApiRequestCandidate:
    if row.competition_season_id is None or row.response_sha256 is None:
        raise ResourceConflict("snapshot candidate is missing its verified scope")
    return ApiRequestCandidate(
        request_id=row.id,
        competition_season_id=row.competition_season_id,
        endpoint_kind=row.endpoint_kind,
        scope_key=row.scope_key,
        week=row.week,
        bracket_kind=row.bracket_kind,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
        response_sha256=row.response_sha256,
    )


def _player_object(row: Player) -> PlayerValue:
    return PlayerValue(
        sleeper_player_id=row.sleeper_player_id,
        full_name=row.full_name,
        position=row.position,
        nfl_team=row.nfl_team,
        active=row.active,
        status=row.status,
        injury_status=row.injury_status,
        age=row.age,
        years_experience=row.years_experience,
        metadata=row.metadata_json,
    )


def _validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 500:
        raise InvalidResourceCommand("page limit must be between 1 and 500")
    if offset < 0:
        raise InvalidResourceCommand("page offset must be non-negative")
