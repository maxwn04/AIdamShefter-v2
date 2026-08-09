from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.services.datalayer.contracts import RefreshRequest, RefreshTrigger, SnapshotRequest
from backend.sleeper import EndpointKind, ScopeKey


def test_scope_key_round_trips_canonical_parts() -> None:
    season_id = uuid4()

    key = ScopeKey.from_parts(EndpointKind.MATCHUPS, season_id, 8)

    assert str(key) == f"matchups:{season_id}:8"
    assert ScopeKey.parse(str(key)) == key


@pytest.mark.parametrize("value", ["matchups", ":week", "matchups:../secret"])
def test_scope_key_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        ScopeKey.parse(value)


def test_refresh_request_validates_week_at_the_boundary() -> None:
    request = RefreshRequest(
        competition_season_id=uuid4(),
        through_week=8,
        trigger=RefreshTrigger.MANUAL,
    )

    assert request.through_week == 8

    with pytest.raises(ValidationError):
        RefreshRequest(
            competition_season_id=uuid4(),
            through_week=0,
            trigger=RefreshTrigger.MANUAL,
        )


def test_snapshot_request_requires_timezone_aware_observation_boundary() -> None:
    request = SnapshotRequest(
        competition_season_id=uuid4(),
        through_week=8,
        observed_through=datetime(2025, 10, 28, tzinfo=timezone.utc),
    )

    assert request.observed_through.tzinfo is timezone.utc

    with pytest.raises(ValidationError):
        SnapshotRequest(
            competition_season_id=uuid4(),
            through_week=8,
            observed_through=datetime(2025, 10, 28),
        )
