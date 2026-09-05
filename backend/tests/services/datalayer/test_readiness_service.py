from datetime import UTC, date, datetime
from uuid import UUID

from backend.resources.sleeper_data.league_seasons import SnapshotSeasonIdentity
from backend.resources.sleeper_data.refreshes import RefreshNeedReason
from backend.resources.sleeper_data.snapshots import SnapshotSeasonRole
from backend.services.datalayer.contracts import SnapshotRequest, SnapshotSelectionRole
from backend.services.datalayer.readiness_service import (
    DatalayerSnapshotReadinessService,
    ReadySnapshotReadiness,
    RefreshRequiredSnapshotReadiness,
    RosterMappingRequiredSnapshotReadiness,
)
from backend.services.datalayer.snapshot_inputs import (
    MapSeasonRosters,
    PrepareSnapshotRequest,
    RefreshSeason,
    ResolvedSnapshotInputs,
    ResolvedSnapshotSeason,
    ResolutionState,
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


COMPETITION_ID = UUID("20000000-0000-0000-0000-000000000001")
HISTORY_ID = UUID("10000000-0000-0000-0000-000000000001")
PRIMARY_ID = UUID("10000000-0000-0000-0000-000000000002")
HASH = "a" * 64


def _identity(season_id: UUID, year: int, sequence: int) -> SnapshotSeasonIdentity:
    return SnapshotSeasonIdentity(
        competition_id=COMPETITION_ID,
        competition_season_id=season_id,
        sleeper_league_id=f"league-{year}",
        season_year=year,
        sequence_number=sequence,
    )


def _request() -> PrepareSnapshotRequest:
    return PrepareSnapshotRequest(
        snapshot=SnapshotRequest(
            competition_season_id=PRIMARY_ID,
            through_week=8,
            as_of_date=date(2026, 8, 29),
        ),
        mode=SnapshotPreparationMode.READINESS_ONLY,
        requested_at=datetime(2026, 8, 29, 22, tzinfo=UTC),
    )


def _resolved() -> ResolvedSnapshotInputs:
    identities = (
        _identity(HISTORY_ID, 2025, 1),
        _identity(PRIMARY_ID, 2026, 2),
    )
    endpoints = tuple(
        build_league_request(identity.competition_season_id, identity.sleeper_league_id)
        for identity in identities
    )
    requirements = tuple(
        SnapshotRequirement(
            request=endpoint,
            selection_role=SnapshotSelectionRole.LEAGUE,
        )
        for endpoint in endpoints
    )
    return ResolvedSnapshotInputs(
        primary=_request().snapshot,
        seasons=tuple(
            ResolvedSnapshotSeason(
                identity=identity,
                role=(
                    SnapshotSeasonRole.PRIMARY
                    if identity.competition_season_id == PRIMARY_ID
                    else SnapshotSeasonRole.HISTORY
                ),
                through_week=(8 if identity.competition_season_id == PRIMARY_ID else 18),
                settings=SnapshotSeasonSettings(
                    playoff_start_week=15,
                    playoff_team_count=6,
                    draft_rounds=0,
                    league_average_match=0,
                ),
                requirement_scopes=(endpoint.scope_key,),
            )
            for identity, endpoint in zip(identities, endpoints, strict=True)
        ),
        requirements=SnapshotRequirements(entries=requirements),
        manifest=SelectedRequestManifest(
            entries=tuple(
                SelectedRequestManifestEntry(
                    request_id=UUID(f"30000000-0000-0000-0000-00000000000{index}"),
                    endpoint_kind=endpoint.endpoint_kind,
                    scope_key=endpoint.scope_key,
                    selection_role=SnapshotSelectionRole.LEAGUE,
                    response_sha256=HASH,
                )
                for index, endpoint in enumerate(endpoints, start=1)
            )
        ),
        roster_mappings=(),
        input_revision=HASH,
    )


class _Resolver:
    def __init__(self, state: ResolutionState) -> None:
        self.state = state
        self.requests: list[PrepareSnapshotRequest] = []

    def resolve(self, request: PrepareSnapshotRequest) -> ResolutionState:
        self.requests.append(request)
        return self.state


def test_ready_state_exposes_only_revision_and_ordered_coverage() -> None:
    resolver = _Resolver(_resolved())
    request = _request()

    result = DatalayerSnapshotReadinessService(resolver).inspect(request)

    assert isinstance(result, ReadySnapshotReadiness)
    assert result.input_revision == HASH
    assert [season.season_year for season in result.included_seasons] == [2025, 2026]
    assert [season.role.value for season in result.included_seasons] == [
        "history",
        "primary",
    ]
    assert [season.through_week for season in result.included_seasons] == [18, 8]
    assert resolver.requests == [request]


def test_refresh_state_retains_exact_historical_action() -> None:
    identity = _identity(HISTORY_ID, 2025, 1)
    result = DatalayerSnapshotReadinessService(
        _Resolver(
            RefreshSeason(
                season=identity,
                through_week=18,
                reason=RefreshNeedReason.MISSING,
                missing_scopes=(build_league_request(HISTORY_ID, "league-2025").scope_key,),
                coverage_fingerprint=HASH,
            )
        )
    ).inspect(_request())

    assert isinstance(result, RefreshRequiredSnapshotReadiness)
    assert result.season.role is SnapshotSeasonRole.HISTORY
    assert result.season.through_week == 18
    assert result.reason is RefreshNeedReason.MISSING
    assert len(result.missing_scopes) == 1


def test_mapping_state_uses_primary_cutoff_when_primary_is_blocked() -> None:
    result = DatalayerSnapshotReadinessService(
        _Resolver(
            MapSeasonRosters(
                season=_identity(PRIMARY_ID, 2026, 2),
                roster_ids=("1", "2"),
            )
        )
    ).inspect(_request())

    assert isinstance(result, RosterMappingRequiredSnapshotReadiness)
    assert result.season.role is SnapshotSeasonRole.PRIMARY
    assert result.season.through_week == 8
    assert result.sleeper_roster_ids == ("1", "2")
