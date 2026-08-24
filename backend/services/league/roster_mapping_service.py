"""Resolve observed Sleeper rosters into durable competition identities."""

from __future__ import annotations

from typing import Protocol, assert_never
from uuid import UUID

from backend.resources.core import (
    ApplyRosterMappings,
    CreateFranchiseTarget,
    RosterIdentityCatalog,
    RosterMappingAssignment,
    RosterMappingConflict,
)
from backend.resources.sleeper_data import (
    ApiRequestCandidate,
    ApplyResult,
    InlineVerifiedPayload,
    ObjectVerifiedPayload,
    VerifiedPayload,
)
from backend.services.datalayer.canonical_json import JsonValue, parse_json_bytes
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.local_files import LocalDatalayerFileStore
from backend.services.datalayer.sleeper.endpoints import (
    LeagueRostersEndpointRecords,
    LeagueUsersEndpointRecords,
    normalize_league_rosters,
    normalize_league_users,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind
from backend.services.league.contracts import (
    ObservedRosterMapping,
    ReconcileRosterMappings,
    RosterManagerEvidence,
    RosterMappingResult,
    RosterMappingView,
)


class MappingStore(Protocol):
    def get_catalog(self, competition_season_id: UUID) -> RosterIdentityCatalog: ...

    def apply(self, command: ApplyRosterMappings) -> RosterIdentityCatalog: ...

    def bootstrap_first_season(
        self,
        competition_season_id: UUID,
        assignments: tuple[RosterMappingAssignment, ...],
    ) -> RosterIdentityCatalog: ...


class RequestPayloadReader(Protocol):
    def get_latest_complete_season_request(
        self,
        competition_season_id: UUID,
        endpoint_kind: EndpointKind,
    ) -> ApiRequestCandidate | None: ...

    def resolve_verified_payloads(
        self, request_ids: tuple[UUID, ...]
    ) -> tuple[VerifiedPayload, ...]: ...


class ScopeWriter(Protocol):
    def apply_scope(
        self,
        request_id: UUID,
        records: LeagueRostersEndpointRecords,
    ) -> ApplyResult: ...


class RosterMappingService:
    """Build mapping views, commit explicit choices, and replay roster scope."""

    def __init__(
        self,
        *,
        mappings: MappingStore,
        requests: RequestPayloadReader,
        scopes: ScopeWriter,
        files: LocalDatalayerFileStore,
    ) -> None:
        self._mappings = mappings
        self._requests = requests
        self._scopes = scopes
        self._files = files

    def get_mapping(self, competition_season_id: UUID) -> RosterMappingView:
        catalog = self._mappings.get_catalog(competition_season_id)
        source = self._requests.get_latest_complete_season_request(
            competition_season_id,
            EndpointKind.LEAGUE_ROSTERS,
        )
        if source is None:
            return RosterMappingView(
                status="awaiting_source",
                roster_count=0,
                mapped_count=len(catalog.mappings),
                rosters=(),
                franchise_options=_active_franchises(catalog),
            )
        rosters, users = self._load_source_records(competition_season_id, source)
        return _build_view(catalog, source, rosters, users)

    def reconcile(
        self,
        competition_season_id: UUID,
        command: ReconcileRosterMappings,
    ) -> RosterMappingResult:
        source = self._requests.get_latest_complete_season_request(
            competition_season_id,
            EndpointKind.LEAGUE_ROSTERS,
        )
        if source is None or source.request_id != command.source_api_request_id:
            raise RosterMappingConflict(
                "the observed roster source changed; reload team setup",
                stale_source=True,
            )
        rosters, _ = self._load_source_records(competition_season_id, source)
        observed_ids = {row.sleeper_roster_id for row in rosters.rosters}
        requested_ids = {row.sleeper_roster_id for row in command.assignments}
        if (
            len(requested_ids) != len(command.assignments)
            or requested_ids != observed_ids
        ):
            raise RosterMappingConflict(
                "assignments must cover every observed Sleeper roster exactly once"
            )
        self._mappings.apply(
            ApplyRosterMappings(
                competition_season_id=competition_season_id,
                assignments=command.assignments,
            )
        )
        try:
            self._scopes.apply_scope(source.request_id, rosters)
        except DatalayerScopeConflict:
            replay_status = "deferred"
        else:
            replay_status = "applied"
        return RosterMappingResult(
            mapping=self.get_mapping(competition_season_id),
            replay_status=replay_status,
        )

    def bootstrap_first_season(
        self,
        competition_season_id: UUID,
        rosters: LeagueRostersEndpointRecords,
        users: LeagueUsersEndpointRecords | None,
    ) -> None:
        catalog = self._mappings.get_catalog(competition_season_id)
        if catalog.sequence_number != 1 or catalog.mappings:
            return
        evidence = _manager_evidence(rosters, users)
        assignments = tuple(
            RosterMappingAssignment(
                sleeper_roster_id=roster.sleeper_roster_id,
                target=CreateFranchiseTarget(
                    display_name=_suggested_name(
                        roster.sleeper_roster_id,
                        evidence[roster.sleeper_roster_id],
                    )
                ),
            )
            for roster in rosters.rosters
        )
        if assignments:
            self._mappings.bootstrap_first_season(
                competition_season_id,
                assignments,
            )

    def _load_source_records(
        self,
        competition_season_id: UUID,
        roster_source: ApiRequestCandidate,
    ) -> tuple[LeagueRostersEndpointRecords, LeagueUsersEndpointRecords | None]:
        users_source = self._requests.get_latest_complete_season_request(
            competition_season_id,
            EndpointKind.LEAGUE_USERS,
        )
        candidates = (roster_source,) if users_source is None else (
            roster_source,
            users_source,
        )
        payloads = self._requests.resolve_verified_payloads(
            tuple(item.request_id for item in candidates)
        )
        values = {
            candidate.endpoint_kind: self._payload_value(payload)
            for candidate, payload in zip(candidates, payloads, strict=True)
        }
        roster_records = normalize_league_rosters(
            values[EndpointKind.LEAGUE_ROSTERS],
            _endpoint_request(roster_source),
        )
        if users_source is None:
            return roster_records, None
        return roster_records, normalize_league_users(
            values[EndpointKind.LEAGUE_USERS],
            _endpoint_request(users_source),
        )

    def _payload_value(self, payload: VerifiedPayload) -> JsonValue:
        if isinstance(payload, InlineVerifiedPayload):
            return payload.payload
        if isinstance(payload, ObjectVerifiedPayload):
            artifact = self._files.open_verified(
                payload.storage_key,
                expected_sha256=payload.sha256,
                expected_byte_length=payload.byte_length,
            )
            return parse_json_bytes(artifact.path.read_bytes())
        assert_never(payload)


def _endpoint_request(candidate: ApiRequestCandidate) -> EndpointRequest:
    suffix = (
        "/rosters"
        if candidate.endpoint_kind is EndpointKind.LEAGUE_ROSTERS
        else "/users"
    )
    return EndpointRequest(
        endpoint_kind=candidate.endpoint_kind,
        scope_key=candidate.scope_key,
        path=f"/league/source{suffix}",
    )


def _build_view(
    catalog: RosterIdentityCatalog,
    source: ApiRequestCandidate,
    rosters: LeagueRostersEndpointRecords,
    users: LeagueUsersEndpointRecords | None,
) -> RosterMappingView:
    mappings = {row.sleeper_roster_id: row for row in catalog.mappings}
    franchises = {row.id: row for row in catalog.franchises}
    evidence = _manager_evidence(rosters, users)
    rows: list[ObservedRosterMapping] = []
    for roster in rosters.rosters:
        mapping = mappings.get(roster.sleeper_roster_id)
        franchise = None if mapping is None else franchises.get(mapping.franchise_id)
        rows.append(
            ObservedRosterMapping(
                sleeper_roster_id=roster.sleeper_roster_id,
                suggested_display_name=_suggested_name(
                    roster.sleeper_roster_id,
                    evidence[roster.sleeper_roster_id],
                ),
                managers=evidence[roster.sleeper_roster_id],
                franchise_id=None if franchise is None else franchise.id,
                franchise_name=None if franchise is None else franchise.display_name,
            )
        )
    observed_ids = {row.sleeper_roster_id for row in rosters.rosters}
    mapped_ids = set(mappings).intersection(observed_ids)
    ready = observed_ids == set(mappings)
    return RosterMappingView(
        status="ready" if ready else "needs_mapping",
        source_api_request_id=source.request_id,
        source_observed_at=source.completed_at,
        roster_count=len(observed_ids),
        mapped_count=len(mapped_ids),
        rosters=tuple(rows),
        franchise_options=_active_franchises(catalog),
    )


def _active_franchises(
    catalog: RosterIdentityCatalog,
) -> tuple:
    return tuple(row for row in catalog.franchises if row.archived_at is None)


def _manager_evidence(
    rosters: LeagueRostersEndpointRecords,
    users: LeagueUsersEndpointRecords | None,
) -> dict[str, tuple[RosterManagerEvidence, ...]]:
    profiles = {} if users is None else {
        row.sleeper_user_id: row for row in users.users
    }
    memberships = {} if users is None else {
        row.sleeper_user_id: row for row in users.league_users
    }
    result: dict[str, list[RosterManagerEvidence]] = {
        row.sleeper_roster_id: [] for row in rosters.rosters
    }
    for manager in rosters.managers:
        profile = profiles.get(manager.sleeper_user_id)
        membership = memberships.get(manager.sleeper_user_id)
        result[manager.sleeper_roster_id].append(
            RosterManagerEvidence(
                sleeper_user_id=manager.sleeper_user_id,
                display_name=(
                    manager.sleeper_user_id
                    if profile is None
                    else profile.display_name
                ),
                team_name=None if membership is None else membership.team_name,
                role=manager.role,
            )
        )
    return {key: tuple(value) for key, value in result.items()}


def _suggested_name(
    sleeper_roster_id: str,
    managers: tuple[RosterManagerEvidence, ...],
) -> str:
    owner = next((row for row in managers if row.role == "owner"), None)
    if owner is not None and owner.team_name and owner.team_name.strip():
        return owner.team_name.strip()
    if owner is not None and owner.display_name.strip():
        return owner.display_name.strip()
    return f"Roster {sleeper_roster_id}"


__all__ = ["RosterMappingService"]
