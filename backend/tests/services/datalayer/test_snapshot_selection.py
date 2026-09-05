from datetime import date, datetime, timezone
from uuid import UUID

import pytest

from backend.resources.sleeper_data import (
    ApiRequestCandidate,
    SnapshotPlanningContext,
)
from backend.services.datalayer import (
    DatalayerScopeConflict,
    EndpointKind,
    SnapshotRequest,
    SnapshotSelectionRole,
    SnapshotUnavailable,
    canonical_snapshot_build_key,
    plan_snapshot_requirements,
    select_snapshot_requests,
)


SEASON_ID = UUID("11111111-1111-1111-1111-111111111111")
COMPETITION_ID = UUID("22222222-2222-2222-2222-222222222222")


def _snapshot(through_week: int = 2) -> SnapshotRequest:
    return SnapshotRequest(
        competition_season_id=SEASON_ID,
        through_week=through_week,
        as_of_date=date(2026, 10, 27),
    )


def _context(
    *, draft_rounds: int = 3, playoff_start_week: int | None = 2
) -> SnapshotPlanningContext:
    return SnapshotPlanningContext(
        competition_id=COMPETITION_ID,
        competition_season_id=SEASON_ID,
        sleeper_league_id="12345",
        season_year=2026,
        playoff_start_week=playoff_start_week,
        playoff_team_count=4,
        draft_rounds=draft_rounds,
        league_average_match=1,
    )


def _candidate(
    requirement,
    *,
    request_id: int,
    requested_hour: int = 1,
    completed_hour: int = 2,
    season_id: UUID | None | object = ...,
) -> ApiRequestCandidate:
    endpoint = requirement.request
    resolved_season = (
        None
        if endpoint.endpoint_kind
        in {EndpointKind.NFL_STATE, EndpointKind.PLAYER_CATALOG}
        else SEASON_ID
    )
    if season_id is not ...:
        resolved_season = season_id
    return ApiRequestCandidate(
        request_id=UUID(int=request_id),
        competition_season_id=resolved_season,
        endpoint_kind=endpoint.endpoint_kind,
        scope_key=endpoint.scope_key,
        week=endpoint.week,
        bracket_kind=endpoint.bracket_kind,
        requested_at=datetime(2026, 11, 1, requested_hour, tzinfo=timezone.utc),
        completed_at=datetime(2026, 11, 1, completed_hour, tzinfo=timezone.utc),
        payload_id=UUID(int=10_000 + request_id),
        response_sha256=f"{request_id:064x}",
    )


def test_build_key_has_a_stable_daily_golden_vector() -> None:
    assert canonical_snapshot_build_key(_snapshot(8), "1") == (
        "7640533409730a2572249fa3a517e01e00086f61f1ff1a81ef1144814be027f7"
    )
    assert canonical_snapshot_build_key(_snapshot(8), "2") != (
        canonical_snapshot_build_key(_snapshot(8), "1")
    )
    # Pre-completion-fix artifacts must not satisfy a new daily build lookup.
    assert canonical_snapshot_build_key(_snapshot(8), "1") != (
        "ba41c48a9ed2cb6d463dd13ced35326b65a31c4c0afc4dbbd19c6f5c905dd624"
    )


def test_daily_build_key_changes_with_derivation_version(monkeypatch: pytest.MonkeyPatch) -> None:
    original = canonical_snapshot_build_key(_snapshot(8), "2")
    monkeypatch.setattr(
        "backend.services.datalayer.snapshot_selection.SNAPSHOT_DERIVATION_VERSION", "next"
    )
    assert canonical_snapshot_build_key(_snapshot(8), "2") != original


def test_requirement_planning_is_explicit_and_stably_ordered() -> None:
    requirements = plan_snapshot_requirements(_snapshot(), _context())

    assert [entry.selection_role for entry in requirements.entries] == [
        SnapshotSelectionRole.LEAGUE,
        SnapshotSelectionRole.LEAGUE_USERS,
        SnapshotSelectionRole.NFL_STATE,
        SnapshotSelectionRole.PLAYER_CATALOG,
        SnapshotSelectionRole.LEAGUE_ROSTERS,
        SnapshotSelectionRole.TRADED_PICKS,
        SnapshotSelectionRole.WEEK_MATCHUPS,
        SnapshotSelectionRole.WEEK_TRANSACTIONS,
        SnapshotSelectionRole.WEEK_MATCHUPS,
        SnapshotSelectionRole.WEEK_TRANSACTIONS,
        SnapshotSelectionRole.WINNERS_BRACKET,
        SnapshotSelectionRole.LOSERS_BRACKET,
    ]
    assert [
        entry.request.week
        for entry in requirements.entries
        if entry.request.endpoint_kind
        in {EndpointKind.MATCHUPS, EndpointKind.TRANSACTIONS}
    ] == [1, 1, 2, 2]


def test_requirement_planning_omits_inapplicable_conditional_scopes() -> None:
    requirements = plan_snapshot_requirements(
        _snapshot(1),
        _context(draft_rounds=0, playoff_start_week=14),
    )

    assert EndpointKind.TRADED_PICKS not in {
        entry.request.endpoint_kind for entry in requirements.entries
    }
    assert EndpointKind.WINNERS_BRACKET not in {
        entry.request.endpoint_kind for entry in requirements.entries
    }


def test_selection_uses_request_start_time_and_ignores_daily_label() -> None:
    request = _snapshot(1)
    requirements = plan_snapshot_requirements(
        request,
        _context(draft_rounds=0, playoff_start_week=14),
    )
    candidates = []
    for index, requirement in enumerate(requirements.entries, start=1):
        candidates.append(_candidate(requirement, request_id=index))
    target = requirements.entries[-1]
    candidates.extend(
        (
            _candidate(
                target,
                request_id=100,
                requested_hour=3,
                completed_hour=5,
            ),
            _candidate(
                target,
                request_id=101,
                requested_hour=4,
                completed_hour=4,
            ),
        )
    )

    manifest = select_snapshot_requests(request, requirements, candidates)

    assert manifest.entries[-1].request_id == UUID(int=101)
    assert manifest.entries[-1].scope_key == target.request.scope_key


def test_selection_reports_ordered_missing_scopes() -> None:
    request = _snapshot(1)
    requirements = plan_snapshot_requirements(
        request,
        _context(draft_rounds=0, playoff_start_week=14),
    )
    candidates = [
        _candidate(requirement, request_id=index)
        for index, requirement in enumerate(requirements.entries[:-2], start=1)
    ]

    with pytest.raises(SnapshotUnavailable) as captured:
        select_snapshot_requests(request, requirements, candidates)

    assert captured.value.missing_scopes == requirements.scope_keys[-2:]


def test_selection_rejects_a_season_mismatch_for_an_exact_scope() -> None:
    request = _snapshot(1)
    requirements = plan_snapshot_requirements(
        request,
        _context(draft_rounds=0, playoff_start_week=14),
    )
    candidates = [
        _candidate(requirement, request_id=index)
        for index, requirement in enumerate(requirements.entries, start=1)
    ]
    candidates[0] = _candidate(
        requirements.entries[0],
        request_id=99,
        season_id=UUID("33333333-3333-3333-3333-333333333333"),
    )

    with pytest.raises(DatalayerScopeConflict):
        select_snapshot_requests(request, requirements, candidates)
