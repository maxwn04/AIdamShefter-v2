from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from backend.resources.sleeper_data.league_seasons import SnapshotSeasonIdentity
from backend.resources.sleeper_data.refreshes import RefreshNeedReason
from backend.resources.sleeper_data.snapshots import SnapshotSeasonRole
from backend.services.datalayer.contracts import (
    ReadyDataSnapshot,
    RefreshStatus,
    SnapshotRequest,
    SnapshotSelectionRole,
)
from backend.services.datalayer.errors import (
    RosterIdentityMappingRequired,
    SnapshotInputsUnavailable,
)
from backend.services.datalayer.local_files import VerifiedLocalArtifact
from backend.services.datalayer.preparation_service import (
    DatalayerSnapshotPreparationService,
)
from backend.services.datalayer.refresh_coordination import (
    RefreshReceipt,
    RefreshReceiptDisposition,
)
from backend.services.datalayer.snapshot_inputs import (
    MapSeasonRosters,
    PrepareSnapshotRequest,
    RefreshSeason,
    ResolvedSnapshotInputs,
    ResolvedSnapshotSeason,
    SnapshotPreparationMode,
    SnapshotSeasonSettings,
)
from backend.services.datalayer.snapshot_selection import (
    SelectedRequestManifest,
    SelectedRequestManifestEntry,
    SnapshotRequirement,
    SnapshotRequirements,
)
from backend.services.datalayer.sleeper.endpoints import build_league_request


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
COMPETITION_ID = UUID("20000000-0000-0000-0000-000000000001")
REQUEST_ID = UUID("30000000-0000-0000-0000-000000000001")
HASH = "a" * 64


def _identity() -> SnapshotSeasonIdentity:
    return SnapshotSeasonIdentity(
        competition_id=COMPETITION_ID,
        competition_season_id=SEASON_ID,
        sleeper_league_id="league-1",
        season_year=2026,
        sequence_number=1,
    )


def _request() -> PrepareSnapshotRequest:
    return PrepareSnapshotRequest(
        snapshot=SnapshotRequest(
            competition_season_id=SEASON_ID,
            through_week=8,
            as_of_date=date(2026, 8, 25),
        ),
        mode=SnapshotPreparationMode.LIVE,
        requested_at=datetime(2026, 8, 25, 20, 0, tzinfo=timezone.utc),
    )


def _refresh_need() -> RefreshSeason:
    return RefreshSeason(
        season=_identity(),
        through_week=8,
        reason=RefreshNeedReason.MISSING,
        coverage_fingerprint=HASH,
    )


def _resolved() -> ResolvedSnapshotInputs:
    endpoint = build_league_request(SEASON_ID, "league-1")
    requirement = SnapshotRequirement(
        request=endpoint,
        selection_role=SnapshotSelectionRole.LEAGUE,
    )
    return ResolvedSnapshotInputs(
        primary=_request().snapshot,
        seasons=(
            ResolvedSnapshotSeason(
                identity=_identity(),
                role=SnapshotSeasonRole.PRIMARY,
                through_week=8,
                settings=SnapshotSeasonSettings(
                    playoff_start_week=15,
                    playoff_team_count=6,
                    draft_rounds=0,
                    league_average_match=0,
                ),
                requirement_scopes=(endpoint.scope_key,),
            ),
        ),
        requirements=SnapshotRequirements(entries=(requirement,)),
        manifest=SelectedRequestManifest(
            entries=(
                SelectedRequestManifestEntry(
                    request_id=REQUEST_ID,
                    endpoint_kind=endpoint.endpoint_kind,
                    scope_key=endpoint.scope_key,
                    selection_role=SnapshotSelectionRole.LEAGUE,
                    response_sha256=HASH,
                ),
            )
        ),
        roster_mappings=(),
        input_revision=HASH,
    )


def _ready() -> ReadyDataSnapshot:
    return ReadyDataSnapshot(
        id=UUID("40000000-0000-0000-0000-000000000001"),
        competition_id=COMPETITION_ID,
        primary_competition_season_id=SEASON_ID,
        through_week=8,
        as_of_date=date(2026, 8, 25),
        build_key=HASH,
        snapshot_projection_version="snapshot-v3",
        artifact=VerifiedLocalArtifact(
            path=Path.cwd().resolve() / "snapshot.sqlite",
            storage_key=f"snapshots/sha256/{HASH[:2]}/{HASH}.sqlite",
            sha256=HASH,
            byte_length=1,
        ),
        input_revision=HASH,
    )


def _receipt() -> RefreshReceipt:
    return RefreshReceipt(
        claim_id=UUID("50000000-0000-0000-0000-000000000001"),
        competition_season_id=SEASON_ID,
        through_week=8,
        refresh_run_id=UUID("60000000-0000-0000-0000-000000000001"),
        status=RefreshStatus.PARTIAL,
        disposition=RefreshReceiptDisposition.CLAIMED,
    )


class _Resolver:
    def __init__(self, states: list[object]):
        self.states = list(states)
        self.requests: list[PrepareSnapshotRequest] = []

    def resolve(self, request: PrepareSnapshotRequest) -> object:
        self.requests.append(request)
        return self.states.pop(0)


class _Refreshes:
    def __init__(self):
        self.needs: list[RefreshSeason] = []

    def ensure(self, need: RefreshSeason) -> RefreshReceipt:
        self.needs.append(need)
        return _receipt()


class _Builder:
    def __init__(self):
        self.inputs: list[ResolvedSnapshotInputs] = []

    def get_or_create(self, inputs: ResolvedSnapshotInputs) -> ReadyDataSnapshot:
        self.inputs.append(inputs)
        return _ready()


def test_partial_refresh_receipt_is_retained_before_exact_frozen_handoff() -> None:
    resolved = _resolved()
    resolver = _Resolver([_refresh_need(), resolved])
    refreshes = _Refreshes()
    builder = _Builder()

    prepared = DatalayerSnapshotPreparationService(
        resolver=resolver,
        refreshes=refreshes,
        builder=builder,
    ).get_or_create(_request())

    assert builder.inputs == [resolved]
    assert refreshes.needs == [_refresh_need()]
    assert prepared.snapshot == _ready()
    assert prepared.refresh_receipts == (_receipt(),)
    assert len(resolver.requests) == 2


def test_repeated_need_for_same_season_terminates_without_second_refresh() -> None:
    need = _refresh_need()
    refreshes = _Refreshes()

    with pytest.raises(SnapshotInputsUnavailable) as caught:
        DatalayerSnapshotPreparationService(
            resolver=_Resolver([need, need]),
            refreshes=refreshes,
            builder=_Builder(),
        ).get_or_create(_request())

    assert caught.value.competition_season_id == SEASON_ID
    assert refreshes.needs == [need]


def test_mapping_state_becomes_actionable_structured_boundary() -> None:
    state = MapSeasonRosters(season=_identity(), roster_ids=("1", "2"))

    with pytest.raises(RosterIdentityMappingRequired) as caught:
        DatalayerSnapshotPreparationService(
            resolver=_Resolver([state]),
            refreshes=_Refreshes(),
            builder=_Builder(),
        ).get_or_create(_request())

    assert caught.value.competition_season_id == SEASON_ID
    assert caught.value.sleeper_roster_ids == ("1", "2")
