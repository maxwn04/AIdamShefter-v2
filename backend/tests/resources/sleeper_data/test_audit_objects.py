from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

import backend.resources.sleeper_data as sleeper_data
from backend.resources.sleeper_data.normalized_scopes import NormalizedScopeManager
from backend.resources.sleeper_data.refreshes import (
    PlannedEndpointScope,
    RefreshRunManager,
    StartRefresh,
)
from backend.resources.sleeper_data.requests import (
    ApiRequestManager,
    RecordApiAttempt,
    SnapshotCandidateQuery,
)
from backend.services.datalayer.contracts import RefreshTrigger
from backend.services.datalayer.local_files import StoredLocalArtifact
from backend.services.datalayer.sleeper.endpoints import build_player_catalog_request
from backend.services.datalayer.sleeper.endpoints.contracts import CompletenessFinding
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey
from backend.tests.resources.sleeper_data.conftest import successful_attempt


def test_audit_resource_managers_are_exported_and_own_their_modules() -> None:
    exported_managers = {
        name: getattr(sleeper_data, name)
        for name in sleeper_data.__all__
        if name.endswith("Manager")
    }

    assert exported_managers["ApiRequestManager"] is ApiRequestManager
    assert exported_managers["NormalizedScopeManager"] is NormalizedScopeManager
    assert exported_managers["RefreshRunManager"] is RefreshRunManager
    assert RefreshRunManager.__module__.endswith(".refreshes.manager")
    assert ApiRequestManager.__module__.endswith(".requests.manager")
    assert NormalizedScopeManager.__module__.endswith(".normalized_scopes.manager")


def test_refresh_plan_requires_ordered_unique_dependencies() -> None:
    season_id = uuid4()
    league = PlannedEndpointScope(
        scope_key=ScopeKey.from_parts(EndpointKind.LEAGUE, season_id),
        endpoint_kind=EndpointKind.LEAGUE,
    )
    rosters = PlannedEndpointScope(
        scope_key=ScopeKey.from_parts(EndpointKind.LEAGUE_ROSTERS, season_id),
        endpoint_kind=EndpointKind.LEAGUE_ROSTERS,
        dependency_scope_keys=(league.scope_key,),
    )

    command = StartRefresh(
        competition_season_id=season_id,
        trigger=RefreshTrigger.MANUAL,
        endpoint_scope=(league, rosters),
        code_version="test",
        normalizer_version="test",
    )
    assert command.endpoint_scope == (league, rosters)

    with pytest.raises(ValidationError, match="precede"):
        StartRefresh(
            competition_season_id=season_id,
            trigger=RefreshTrigger.MANUAL,
            endpoint_scope=(rosters, league),
            code_version="test",
            normalizer_version="test",
        )
    with pytest.raises(ValidationError, match="unique"):
        StartRefresh(
            competition_season_id=season_id,
            trigger=RefreshTrigger.MANUAL,
            endpoint_scope=(league, league),
            code_version="test",
            normalizer_version="test",
        )


def test_object_payload_receipt_must_match_source_attempt() -> None:
    attempt = successful_attempt(
        build_player_catalog_request(),
        {"fraction": Decimal("1.125")},
        requested_at=datetime.now(UTC),
    )
    wrong_hash = "0" * 64

    with pytest.raises(ValidationError, match="does not match"):
        RecordApiAttempt(
            refresh_run_id=uuid4(),
            attempt=attempt,
            completeness=CompletenessFinding(is_complete=True),
            object_receipt=StoredLocalArtifact(
                storage_key=f"payloads/sha256/00/{wrong_hash}.json",
                sha256=wrong_hash,
                byte_length=attempt.byte_length,
            ),
        )


def test_snapshot_candidate_scopes_must_be_present_and_unique() -> None:
    scope = ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl")

    with pytest.raises(ValidationError, match="at least one"):
        SnapshotCandidateQuery(
            competition_season_id=uuid4(),
            scope_keys=(),
            through_week=1,
        )
    with pytest.raises(ValidationError, match="unique"):
        SnapshotCandidateQuery(
            competition_season_id=uuid4(),
            scope_keys=(scope, scope),
            through_week=1,
        )
