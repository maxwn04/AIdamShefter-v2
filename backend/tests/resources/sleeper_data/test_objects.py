from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest

from backend.database.models.core.competitions import CompetitionSeason
from backend.database.models.sleeper.normalized import DraftPick
from backend.database.models.sleeper.requests import ApiRequest as ApiRequestRow
from backend.resources.context import ActorKind, ManagerContext
from backend.resources.errors import InvalidResourceCommand
from backend.resources.sleeper_data.manager import (
    _derive_refresh_summary,
    _effective_through_week,
    _plan_document,
    _request_can_replace_draft_source,
    _validate_plan,
    _verified_canonical_jsonb_text,
)
from backend.resources.sleeper_data.objects import (
    ApplyDisposition,
    ApplyResult,
    NormalizationStatus,
    PayloadReceipt,
    RefreshScopePlan,
    RefreshStatus,
    RequestStatus,
)


def test_manager_context_requires_one_explicit_scope() -> None:
    competition_id = uuid4()
    context = ManagerContext.competition(
        actor_kind=ActorKind.API,
        actor_id="local-api",
        competition_id=competition_id,
        correlation_id="request-1",
    )

    assert context.competition_id == competition_id
    assert not context.is_global

    global_context = ManagerContext.global_scope(
        actor_kind=ActorKind.WORKER,
        actor_id="catalog-worker",
        reason="refresh global player catalog",
    )
    assert global_context.is_global

    with pytest.raises(ValueError, match="exactly one"):
        ManagerContext(
            actor_kind=ActorKind.SYSTEM,
            actor_id="system",
            competition_id=competition_id,
            global_reason="also global",
        )


def test_payload_receipt_represents_inline_json_null_exactly() -> None:
    content = "null"
    receipt = PayloadReceipt(
        sha256=sha256(content.encode()).hexdigest(),
        byte_length=len(content),
        media_type="application/json",
        inline_json_text=content,
    )

    assert receipt.inline_json_text == "null"
    assert receipt.local_storage_key is None


def test_payload_receipt_requires_content_addressed_local_key() -> None:
    digest = sha256(b"[]").hexdigest()
    with pytest.raises(ValueError, match="content receipt"):
        PayloadReceipt(
            sha256=digest,
            byte_length=2,
            media_type="application/json",
            local_storage_key="payloads/arbitrary.json",
        )


def test_jsonb_text_is_recanonicalized_before_payload_receipt_verification() -> None:
    canonical = '{"a":1.25,"b":[2,3]}'

    recovered = _verified_canonical_jsonb_text(
        '{"b": [2, 3], "a": 1.2500}',
        expected_sha256=sha256(canonical.encode()).hexdigest(),
        expected_byte_length=len(canonical.encode()),
    )

    assert recovered == canonical


def test_apply_result_derives_current_view_change() -> None:
    applied = ApplyResult(
        disposition=ApplyDisposition.APPLIED,
        request_id=uuid4(),
        scope_key="league:season",
        normalized_row_count=1,
    )
    identical = ApplyResult(
        disposition=ApplyDisposition.IDENTICAL_HEAD_ADVANCED,
        request_id=uuid4(),
        scope_key="league:season",
        normalized_row_count=1,
    )

    assert applied.changed_current_view
    assert not identical.changed_current_view


def test_refresh_plan_rejects_duplicate_and_unknown_dependencies() -> None:
    season_id = uuid4()
    scope = RefreshScopePlan(
        scope_key=f"league:{season_id}",
        endpoint_kind="league",
        required=True,
    )
    with pytest.raises(InvalidResourceCommand, match="duplicate"):
        _validate_plan(
            (scope, scope),
            competition_season_id=season_id,
        )

    with pytest.raises(InvalidResourceCommand, match="dependenc"):
        _validate_plan(
            (
                RefreshScopePlan(
                    scope_key=f"rosters:{season_id}",
                    endpoint_kind="league_rosters",
                    required=True,
                    dependency_scope_keys=(f"users:{season_id}",),
                ),
            ),
            competition_season_id=season_id,
        )

    users = RefreshScopePlan(
        scope_key=f"users:{season_id}",
        endpoint_kind="league_users",
        required=True,
    )
    rosters = RefreshScopePlan(
        scope_key=f"rosters:{season_id}",
        endpoint_kind="league_rosters",
        required=True,
        dependency_scope_keys=(users.scope_key,),
    )
    with pytest.raises(InvalidResourceCommand, match="precede"):
        _validate_plan(
            (rosters, users),
            competition_season_id=season_id,
        )

    _validate_plan(
        (users, rosters),
        competition_season_id=season_id,
    )

    with pytest.raises(InvalidResourceCommand, match="do not agree"):
        _validate_plan(
            (
                RefreshScopePlan(
                    scope_key="players:nfl",
                    endpoint_kind="league",
                    required=True,
                ),
            ),
            competition_season_id=season_id,
        )


def test_refresh_plan_document_keeps_effective_week_separate() -> None:
    plan = (RefreshScopePlan("league:season", "league", True),)

    document = _plan_document(plan, effective_through_week=8)

    assert _effective_through_week(document) == 8


def test_refresh_summary_uses_latest_retry_and_requiredness() -> None:
    requested_at = datetime(2025, 9, 1, tzinfo=UTC)
    failed_retry = _attempt(
        scope_key="league:season",
        requested_at=requested_at,
        status=RequestStatus.HTTP_ERROR,
        normalization_status=NormalizationStatus.PENDING,
        complete=False,
    )
    successful_retry = _attempt(
        scope_key="league:season",
        requested_at=requested_at.replace(microsecond=1),
        status=RequestStatus.SUCCEEDED,
        normalization_status=NormalizationStatus.SUCCEEDED,
        complete=True,
    )
    optional_failure = _attempt(
        scope_key="bracket:season:winners",
        requested_at=requested_at,
        status=RequestStatus.HTTP_ERROR,
        normalization_status=NormalizationStatus.PENDING,
        complete=False,
    )
    plan = (
        RefreshScopePlan("league:season", "league", True),
        RefreshScopePlan("bracket:season:winners", "winners_bracket", False),
    )

    summary = _derive_refresh_summary(
        plan,
        (failed_retry, successful_retry, optional_failure),
        cancelled=False,
    )

    assert summary.status is RefreshStatus.SUCCEEDED
    assert summary.succeeded_scope_count == 1
    assert summary.failed_scope_count == 1
    assert summary.failed_scope_keys == ("bracket:season:winners",)


def test_refresh_summary_preserves_cancelled_state_without_marking_unattempted_failed() -> None:
    plan = (
        RefreshScopePlan("league:season", "league", True),
        RefreshScopePlan("users:season", "league_users", True),
    )
    attempt = _attempt(
        scope_key="league:season",
        requested_at=datetime(2025, 9, 1, tzinfo=UTC),
        status=RequestStatus.SUCCEEDED,
        normalization_status=NormalizationStatus.SUCCEEDED,
        complete=True,
    )

    summary = _derive_refresh_summary(plan, (attempt,), cancelled=True)

    assert summary.status is RefreshStatus.CANCELLED
    assert summary.succeeded_scope_count == 1
    assert summary.failed_scope_count == 0


def test_newer_competition_season_outranks_later_archived_request() -> None:
    old_season_id = uuid4()
    new_season_id = uuid4()
    current_request_id = uuid4()
    incoming_request = _attempt(
        scope_key="picks:old-season",
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
        status=RequestStatus.SUCCEEDED,
        normalization_status=NormalizationStatus.PENDING,
        complete=True,
    )
    incoming_request.competition_season_id = old_season_id
    current_request = _attempt(
        scope_key="picks:new-season",
        requested_at=datetime(2025, 9, 1, tzinfo=UTC),
        status=RequestStatus.SUCCEEDED,
        normalization_status=NormalizationStatus.SUCCEEDED,
        complete=True,
    )
    current_request.id = current_request_id
    current_request.competition_season_id = new_season_id
    current = DraftPick(
        competition_id=uuid4(),
        draft_season_year=2027,
        round=1,
        original_franchise_id=uuid4(),
        current_franchise_id=uuid4(),
        source="trade",
        source_api_request_id=current_request_id,
        source_api_request_competition_season_id=new_season_id,
    )
    session = _LookupSession(
        {
            (ApiRequestRow, current_request_id): current_request,
            (CompetitionSeason, new_season_id): CompetitionSeason(
                id=new_season_id,
                competition_id=current.competition_id,
                season_year=2025,
                sequence_number=2,
                sleeper_league_id="new-season",
            ),
        }
    )

    assert not _request_can_replace_draft_source(
        session,
        request=incoming_request,
        current=current,
        incoming_season_year=2024,
    )


class _LookupSession:
    def __init__(self, values: dict[tuple[type[object], object], object]) -> None:
        self._values = values

    def get(self, model: type[object], identity: object) -> object | None:
        return self._values.get((model, identity))


def _attempt(
    *,
    scope_key: str,
    requested_at: datetime,
    status: RequestStatus,
    normalization_status: NormalizationStatus,
    complete: bool,
) -> ApiRequestRow:
    return ApiRequestRow(
        id=uuid4(),
        refresh_run_id=uuid4(),
        competition_season_id=uuid4(),
        endpoint_kind="league",
        scope_key=scope_key,
        request_path="/league/example",
        request_parameters={},
        requested_at=requested_at,
        completed_at=requested_at,
        status=status.value,
        is_complete=complete,
        normalization_status=normalization_status.value,
    )
