from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from backend.resources.core import (
    ApplyRosterMappings,
    CreateFranchiseTarget,
    FranchiseIdentity,
    RosterIdentityCatalog,
    RosterMappingAssignment,
    RosterMappingConflict,
    SeasonRosterIdentity,
)
from backend.resources.sleeper_data import (
    ApiRequestCandidate,
    ApplyResult,
    InlineVerifiedPayload,
)
from backend.services.datalayer import ApplyDisposition, EndpointKind, ScopeKey
from backend.services.datalayer.local_files import LocalDatalayerFileStore
from backend.services.datalayer.sleeper.endpoints import (
    LeagueRostersEndpointRecords,
    LeagueUsersEndpointRecords,
)
from backend.services.league import ReconcileRosterMappings, RosterMappingService


COMPETITION_ID = UUID("10000000-0000-0000-0000-000000000001")
SEASON_ID = UUID("20000000-0000-0000-0000-000000000002")
REQUEST_ID = UUID("30000000-0000-0000-0000-000000000003")
NOW = datetime(2026, 8, 23, tzinfo=UTC)


class FakeMappings:
    def __init__(self, *, sequence_number: int = 2) -> None:
        self.catalog = RosterIdentityCatalog(
            competition_id=COMPETITION_ID,
            competition_season_id=SEASON_ID,
            sequence_number=sequence_number,
            competition_archived=False,
            franchises=(
                FranchiseIdentity(
                    id=UUID("40000000-0000-0000-0000-000000000004"),
                    competition_id=COMPETITION_ID,
                    display_name="Returning Team",
                    archived_at=None,
                ),
            ),
            mappings=(),
        )
        self.applied: ApplyRosterMappings | None = None
        self.bootstrapped: tuple[RosterMappingAssignment, ...] = ()

    def get_catalog(self, competition_season_id: UUID) -> RosterIdentityCatalog:
        assert competition_season_id == SEASON_ID
        return self.catalog

    def apply(self, command: ApplyRosterMappings) -> RosterIdentityCatalog:
        self.applied = command
        franchises = list(self.catalog.franchises)
        mappings: list[SeasonRosterIdentity] = []
        for assignment in command.assignments:
            if isinstance(assignment.target, CreateFranchiseTarget):
                franchise = FranchiseIdentity(
                    id=uuid4(),
                    competition_id=COMPETITION_ID,
                    display_name=assignment.target.display_name,
                    archived_at=None,
                )
                franchises.append(franchise)
            else:
                franchise = next(
                    item
                    for item in franchises
                    if item.id == assignment.target.franchise_id
                )
            mappings.append(
                SeasonRosterIdentity(
                    id=uuid4(),
                    competition_season_id=SEASON_ID,
                    franchise_id=franchise.id,
                    sleeper_roster_id=assignment.sleeper_roster_id,
                )
            )
        self.catalog = self.catalog.model_copy(
            update={"franchises": tuple(franchises), "mappings": tuple(mappings)}
        )
        return self.catalog

    def bootstrap_first_season(
        self,
        competition_season_id: UUID,
        assignments: tuple[RosterMappingAssignment, ...],
    ) -> RosterIdentityCatalog:
        self.bootstrapped = assignments
        return self.apply(
            ApplyRosterMappings(
                competition_season_id=competition_season_id,
                assignments=assignments,
            )
        )


class FakeRequests:
    def __init__(self, *, with_source: bool = True) -> None:
        self.roster_candidate = _candidate(EndpointKind.LEAGUE_ROSTERS, REQUEST_ID)
        self.users_candidate = _candidate(EndpointKind.LEAGUE_USERS, uuid4())
        self.with_source = with_source
        self.payloads = {
            self.roster_candidate.request_id: _payload(
                self.roster_candidate,
                [
                    {
                        "roster_id": 1,
                        "owner_id": "u1",
                        "settings": {},
                        "metadata": {},
                    },
                    {
                        "roster_id": 2,
                        "settings": {},
                        "metadata": {},
                    },
                ],
            ),
            self.users_candidate.request_id: _payload(
                self.users_candidate,
                [
                    {
                        "user_id": "u1",
                        "display_name": "Manager One",
                        "metadata": {"team_name": "Alpha Team"},
                    }
                ],
            ),
        }

    def get_latest_complete_season_request(
        self,
        competition_season_id: UUID,
        endpoint_kind: EndpointKind,
    ) -> ApiRequestCandidate | None:
        assert competition_season_id == SEASON_ID
        if not self.with_source:
            return None
        return (
            self.roster_candidate
            if endpoint_kind is EndpointKind.LEAGUE_ROSTERS
            else self.users_candidate
        )

    def resolve_verified_payloads(
        self, request_ids: tuple[UUID, ...]
    ) -> tuple[InlineVerifiedPayload, ...]:
        return tuple(self.payloads[item] for item in request_ids)


class FakeScopes:
    def __init__(self, *, conflict: bool = False) -> None:
        self.conflict = conflict
        self.applied: LeagueRostersEndpointRecords | None = None

    def apply_scope(
        self,
        request_id: UUID,
        records: LeagueRostersEndpointRecords,
    ) -> ApplyResult:
        from backend.services.datalayer.errors import DatalayerScopeConflict

        if self.conflict:
            raise DatalayerScopeConflict("dependency unavailable")
        self.applied = records
        return ApplyResult(
            request_id=request_id,
            scope_key=ScopeKey.from_parts(EndpointKind.LEAGUE_ROSTERS, SEASON_ID),
            disposition=ApplyDisposition.APPLIED,
            head_request_id=request_id,
            normalized_row_count=2,
            changed_current_view=True,
        )


def test_mapping_view_waits_for_a_complete_roster_source(tmp_path) -> None:
    service = _service(tmp_path, FakeMappings(), FakeRequests(with_source=False))

    view = service.get_mapping(SEASON_ID)

    assert view.status == "awaiting_source"
    assert view.rosters == ()
    assert view.franchise_options[0].display_name == "Returning Team"


def test_mapping_view_uses_team_owner_and_roster_name_fallbacks(tmp_path) -> None:
    service = _service(tmp_path, FakeMappings(), FakeRequests())

    view = service.get_mapping(SEASON_ID)

    assert view.status == "needs_mapping"
    assert [row.suggested_display_name for row in view.rosters] == [
        "Alpha Team",
        "Roster 2",
    ]
    assert view.rosters[0].managers[0].display_name == "Manager One"


def test_reconcile_requires_latest_source_and_exact_coverage(tmp_path) -> None:
    service = _service(tmp_path, FakeMappings(), FakeRequests())
    command = ReconcileRosterMappings(source_api_request_id=uuid4(), assignments=())

    try:
        service.reconcile(SEASON_ID, command)
    except RosterMappingConflict as error:
        assert error.stale_source
    else:
        raise AssertionError("stale source should conflict")


def test_reconcile_commits_mapping_and_reports_deferred_replay(tmp_path) -> None:
    mappings = FakeMappings()
    scopes = FakeScopes(conflict=True)
    service = _service(tmp_path, mappings, FakeRequests(), scopes=scopes)
    existing = mappings.catalog.franchises[0]

    result = service.reconcile(
        SEASON_ID,
        ReconcileRosterMappings(
            source_api_request_id=REQUEST_ID,
            assignments=(
                RosterMappingAssignment(
                    sleeper_roster_id="1",
                    target={"kind": "existing", "franchise_id": existing.id},
                ),
                RosterMappingAssignment(
                    sleeper_roster_id="2",
                    target={"kind": "new", "display_name": "Expansion"},
                ),
            ),
        ),
    )

    assert result.replay_status == "deferred"
    assert result.mapping.status == "ready"
    assert result.mapping.mapped_count == 2


def test_first_season_bootstrap_creates_only_new_franchises(tmp_path) -> None:
    mappings = FakeMappings(sequence_number=1)
    requests = FakeRequests()
    service = _service(tmp_path, mappings, requests)
    rosters, users = service._load_source_records(  # noqa: SLF001
        SEASON_ID, requests.roster_candidate
    )

    service.bootstrap_first_season(SEASON_ID, rosters, users)

    assert [item.sleeper_roster_id for item in mappings.bootstrapped] == ["1", "2"]
    assert all(item.target.kind == "new" for item in mappings.bootstrapped)


def _service(
    tmp_path,
    mappings: FakeMappings,
    requests: FakeRequests,
    *,
    scopes: FakeScopes | None = None,
) -> RosterMappingService:
    return RosterMappingService(
        mappings=mappings,
        requests=requests,
        scopes=scopes or FakeScopes(),
        files=LocalDatalayerFileStore(tmp_path),
    )


def _candidate(kind: EndpointKind, request_id: UUID) -> ApiRequestCandidate:
    return ApiRequestCandidate(
        request_id=request_id,
        competition_season_id=SEASON_ID,
        endpoint_kind=kind,
        scope_key=ScopeKey.from_parts(kind, SEASON_ID),
        week=None,
        bracket_kind=None,
        requested_at=NOW,
        completed_at=NOW,
        payload_id=uuid4(),
        response_sha256="a" * 64,
    )


def _payload(
    candidate: ApiRequestCandidate,
    payload,
) -> InlineVerifiedPayload:
    return InlineVerifiedPayload(
        request_id=candidate.request_id,
        scope_key=candidate.scope_key,
        sha256="a" * 64,
        byte_length=1,
        media_type="application/json",
        payload=payload,
    )
