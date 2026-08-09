from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.api.schemas.data import DataRefreshCreateRequest, DataRefreshResponse
from backend.services.datalayer.contracts import (
    NormalizationStatus,
    RefreshOutcome,
    RefreshStatus,
    RequestStatus,
    ScopeRefreshResult,
)
from backend.sleeper import ScopeKey

REFRESH_ID = UUID("11111111-1111-1111-1111-111111111111")
API_REQUEST_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_create_request_accepts_only_the_optional_week() -> None:
    assert DataRefreshCreateRequest.model_validate({}).through_week is None
    assert DataRefreshCreateRequest.model_validate(
        {"through_week": 8}
    ).through_week == 8

    with pytest.raises(ValidationError):
        DataRefreshCreateRequest.model_validate({"trigger": "scheduled"})


@pytest.mark.parametrize("through_week", [0, 19])
def test_create_request_rejects_week_outside_the_season(
    through_week: int,
) -> None:
    with pytest.raises(ValidationError):
        DataRefreshCreateRequest(through_week=through_week)


def test_response_projects_scope_keys_without_internal_types() -> None:
    response = DataRefreshResponse.from_outcome(
        RefreshOutcome(
            refresh_run_id=REFRESH_ID,
            status=RefreshStatus.SUCCEEDED,
            requested_scope_count=1,
            succeeded_scope_count=1,
            failed_scope_count=0,
            scope_results=(
                ScopeRefreshResult(
                    scope_key=ScopeKey.parse("matchups:season-1:8"),
                    api_request_id=API_REQUEST_ID,
                    fetch_status=RequestStatus.SUCCEEDED,
                    normalization_status=NormalizationStatus.SUCCEEDED,
                    changed_current_view=True,
                    warning_codes=("lineup_missing",),
                ),
            ),
        )
    )

    assert response.model_dump(mode="json") == {
        "refresh_run_id": str(REFRESH_ID),
        "status": "succeeded",
        "requested_scope_count": 1,
        "succeeded_scope_count": 1,
        "failed_scope_count": 0,
        "scope_results": [
            {
                "scope_key": "matchups:season-1:8",
                "api_request_id": str(API_REQUEST_ID),
                "fetch_status": "succeeded",
                "normalization_status": "succeeded",
                "changed_current_view": True,
                "warning_codes": ["lineup_missing"],
            }
        ],
    }
