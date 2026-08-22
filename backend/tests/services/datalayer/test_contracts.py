from datetime import date
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.services.datalayer import (
    CompletenessWarning,
    EndpointKind,
    NormalizationStatus,
    RefreshOutcome,
    RefreshRequest,
    RefreshStatus,
    RefreshTrigger,
    RequestStatus,
    ScopeKey,
    ScopeRefreshResult,
    SnapshotRequest,
)


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
REQUEST_ID = UUID("20000000-0000-0000-0000-000000000002")
REFRESH_ID = UUID("30000000-0000-0000-0000-000000000003")


def test_scope_key_round_trips_canonical_parts() -> None:
    key = ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 8)

    assert str(key) == f"matchups:{SEASON_ID}:8"
    assert ScopeKey.parse(str(key)) == key


@pytest.mark.parametrize(
    "value",
    [
        "matchups",
        ":week",
        "matchups:../secret",
        "Matchups:season:8",
        "matchups:season:8?raw=true",
    ],
)
def test_scope_key_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError):
        ScopeKey.parse(value)


def test_scope_key_rejects_ambiguous_parts() -> None:
    with pytest.raises(ValueError, match="at least two"):
        ScopeKey.from_parts(EndpointKind.MATCHUPS)
    with pytest.raises(TypeError, match="boolean"):
        ScopeKey.from_parts(EndpointKind.MATCHUPS, True)


def test_workflow_requests_are_frozen_and_validate_week_boundaries() -> None:
    refresh = RefreshRequest(
        competition_season_id=SEASON_ID,
        through_week=8,
        trigger=RefreshTrigger.MANUAL,
    )
    snapshot = SnapshotRequest(
        competition_season_id=SEASON_ID,
        through_week=8,
        as_of_date=date(2025, 10, 28),
    )

    assert refresh.through_week == snapshot.through_week == 8
    assert snapshot.as_of_date == date(2025, 10, 28)
    with pytest.raises(ValidationError, match="frozen"):
        refresh.through_week = 9
    with pytest.raises(ValidationError):
        SnapshotRequest(
            competition_season_id=SEASON_ID,
            through_week=0,
            as_of_date=date(2025, 10, 28),
        )
    with pytest.raises(ValidationError, match="extra"):
        RefreshRequest(
            competition_season_id=SEASON_ID,
            through_week=8,
            trigger=RefreshTrigger.MANUAL,
            endpoint_kinds=(),
        )


def test_refresh_outcome_retains_immutable_scope_results() -> None:
    scope_result = ScopeRefreshResult(
        scope_key=ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 8),
        api_request_id=REQUEST_ID,
        fetch_status=RequestStatus.SUCCEEDED,
        normalization_status=NormalizationStatus.SUCCEEDED,
        changed_current_view=True,
        warning_codes=("late_reference_data",),
    )

    outcome = RefreshOutcome(
        refresh_run_id=REFRESH_ID,
        status=RefreshStatus.PARTIAL,
        requested_scope_count=2,
        succeeded_scope_count=1,
        failed_scope_count=1,
        scope_results=(scope_result,),
    )

    assert outcome.scope_results == (scope_result,)
    assert outcome.scope_results[0].warning_codes == ("late_reference_data",)


def test_completeness_warning_is_safe_structured_context() -> None:
    scope_key = ScopeKey.from_parts(EndpointKind.TRANSACTIONS, SEASON_ID, 8)

    warning = CompletenessWarning(
        code="late_reference_data",
        summary="Current names supplied display-only reference fields.",
        scope_key=scope_key,
    )

    assert warning.scope_key == scope_key
    assert warning.summary == "Current names supplied display-only reference fields."
    with pytest.raises(ValidationError):
        CompletenessWarning(code="Not Canonical", summary="unsafe code")
    with pytest.raises(ValidationError):
        CompletenessWarning(code="empty_summary", summary="   ")


def test_scope_result_rejects_unstructured_warning_codes() -> None:
    with pytest.raises(ValidationError):
        ScopeRefreshResult(
            scope_key=ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 8),
            api_request_id=REQUEST_ID,
            fetch_status=RequestStatus.SUCCEEDED,
            normalization_status=NormalizationStatus.SUCCEEDED,
            changed_current_view=True,
            warning_codes=("Not Canonical",),
        )
