"""Resolve immutable multi-season snapshot inputs without network work."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Protocol, TypeAlias, cast
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from backend.resources._contracts import ContractModel
from backend.resources.core import SeasonRosterIdentity as CoreRosterIdentity
from backend.resources.sleeper_data.league_seasons import (
    SnapshotLineage,
    SnapshotSeasonIdentity,
)
from backend.resources.sleeper_data.refreshes import RefreshNeedReason
from backend.resources.sleeper_data.requests import (
    ApiRequestCandidate,
    InlineVerifiedPayload,
    LatestCompleteCandidatesQuery,
    ObjectVerifiedPayload,
    VerifiedPayload,
)
from backend.resources.sleeper_data.snapshots import SnapshotSeasonRole
from backend.services.datalayer.canonical_json import (
    JsonValue,
    canonical_json_sha256,
    parse_json_bytes,
)
from backend.services.datalayer.contracts import (
    SnapshotRequest,
    SnapshotSelectionRole,
)
from backend.services.datalayer.errors import DatalayerScopeConflict
from backend.services.datalayer.local_files import VerifiedLocalArtifact
from backend.services.datalayer.snapshot_selection import (
    SelectedRequestManifest,
    SelectedRequestManifestEntry,
    SnapshotRequirement,
    SnapshotRequirements,
)
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_rosters_request,
    build_league_users_request,
    build_losers_bracket_request,
    build_matchups_request,
    build_player_catalog_request,
    build_traded_picks_request,
    build_transactions_request,
    build_winners_bracket_request,
    normalize_league,
    normalize_league_rosters,
)
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class SnapshotPreparationMode(StrEnum):
    LIVE = "live"
    READINESS_ONLY = "readiness_only"


class PrepareSnapshotRequest(ContractModel):
    snapshot: SnapshotRequest
    mode: SnapshotPreparationMode
    requested_at: AwareDatetime


class SnapshotSeasonSettings(ContractModel):
    playoff_start_week: int | None
    playoff_team_count: int | None
    draft_rounds: int = Field(strict=True, ge=0)
    league_average_match: int | None


class ResolvedSnapshotSeason(ContractModel):
    identity: SnapshotSeasonIdentity
    role: SnapshotSeasonRole
    through_week: int = Field(strict=True, ge=1, le=18)
    settings: SnapshotSeasonSettings
    requirement_scopes: tuple[ScopeKey, ...]


class ResolvedRosterMapping(ContractModel):
    competition_id: UUID
    competition_season_id: UUID
    sleeper_roster_id: str
    season_roster_id: UUID
    franchise_id: UUID


class ResolvedSnapshotInputs(ContractModel):
    primary: SnapshotRequest
    seasons: tuple[ResolvedSnapshotSeason, ...]
    requirements: SnapshotRequirements
    manifest: SelectedRequestManifest
    roster_mappings: tuple[ResolvedRosterMapping, ...]
    input_revision: Sha256

    @model_validator(mode="after")
    def validate_inputs(self) -> "ResolvedSnapshotInputs":
        primary = [season for season in self.seasons if season.role is SnapshotSeasonRole.PRIMARY]
        if len(primary) != 1:
            raise ValueError("resolved snapshot inputs require one primary season")
        if primary[0].identity.competition_season_id != self.primary.competition_season_id:
            raise ValueError("resolved primary season does not match the request")
        if self.requirements.scope_keys != tuple(
            entry.scope_key for entry in self.manifest.entries
        ):
            raise ValueError("resolved manifest must follow exact requirement order")
        return self


class RefreshSeason(ContractModel):
    season: SnapshotSeasonIdentity
    through_week: int = Field(strict=True, ge=1, le=18)
    reason: RefreshNeedReason
    missing_scopes: tuple[ScopeKey, ...] = ()
    coverage_fingerprint: Sha256


class MapSeasonRosters(ContractModel):
    season: SnapshotSeasonIdentity
    roster_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_rosters(self) -> "MapSeasonRosters":
        if not self.roster_ids:
            raise ValueError("mapping state requires at least one roster")
        if len(set(self.roster_ids)) != len(self.roster_ids):
            raise ValueError("mapping roster IDs must be unique")
        return self


ResolutionState: TypeAlias = ResolvedSnapshotInputs | RefreshSeason | MapSeasonRosters


class SnapshotLineageReader(Protocol):
    def get_snapshot_lineage(self, competition_season_id: UUID) -> SnapshotLineage: ...


class SnapshotCandidateReader(Protocol):
    def list_latest_complete_candidates(
        self,
        query: LatestCompleteCandidatesQuery,
    ) -> tuple[ApiRequestCandidate, ...]: ...

    def resolve_verified_payloads(
        self,
        request_ids: Collection[UUID],
    ) -> tuple[VerifiedPayload, ...]: ...


class SnapshotMappingReader(Protocol):
    def list_snapshot_mappings(
        self,
        competition_season_ids: Collection[UUID],
    ) -> tuple[CoreRosterIdentity, ...]: ...


class SnapshotPayloadFileReader(Protocol):
    def open_verified(
        self,
        storage_key: str,
        *,
        expected_sha256: str,
        expected_byte_length: int,
    ) -> VerifiedLocalArtifact: ...


class SnapshotInputResolver:
    """Return one closed preparation state from durable snapshot evidence."""

    def __init__(
        self,
        *,
        lineage: SnapshotLineageReader,
        requests: SnapshotCandidateReader,
        mappings: SnapshotMappingReader,
        files: SnapshotPayloadFileReader,
        live_max_age_seconds: int = 900,
    ) -> None:
        if (
            isinstance(live_max_age_seconds, bool)
            or not isinstance(live_max_age_seconds, int)
            or live_max_age_seconds < 1
        ):
            raise ValueError("live_max_age_seconds must be a positive integer")
        self._lineage = lineage
        self._requests = requests
        self._mappings = mappings
        self._files = files
        self._live_max_age = timedelta(seconds=live_max_age_seconds)

    def resolve(self, request: PrepareSnapshotRequest) -> ResolutionState:
        lineage = self._lineage.get_snapshot_lineage(
            request.snapshot.competition_season_id
        )
        cutoffs = {
            season.competition_season_id: (
                request.snapshot.through_week
                if season.competition_season_id
                == request.snapshot.competition_season_id
                else 18
            )
            for season in lineage.seasons
        }
        league_requirements = tuple(
            SnapshotRequirement(
                request=build_league_request(
                    season.competition_season_id,
                    season.sleeper_league_id,
                ),
                selection_role=SnapshotSelectionRole.LEAGUE,
            )
            for season in lineage.seasons
        )
        league_candidates = self._latest(
            tuple(item.request.scope_key for item in league_requirements)
        )
        for season, requirement in zip(
            lineage.seasons, league_requirements, strict=True
        ):
            if requirement.request.scope_key not in league_candidates:
                return _refresh_state(
                    season,
                    cutoffs[season.competition_season_id],
                    RefreshNeedReason.MISSING,
                    (requirement.request.scope_key,),
                    league_candidates.values(),
                )

        league_payloads = self._payload_values(
            tuple(
                league_candidates[item.request.scope_key]
                for item in league_requirements
            )
        )
        settings: dict[UUID, SnapshotSeasonSettings] = {}
        for season, requirement, payload in zip(
            lineage.seasons,
            league_requirements,
            league_payloads,
            strict=True,
        ):
            records = normalize_league(payload, requirement.request)
            if (
                records.league.sleeper_league_id != season.sleeper_league_id
                or records.league.season != str(season.season_year)
            ):
                raise DatalayerScopeConflict(
                    "selected League payload conflicts with core season identity"
                )
            raw_rounds = records.league.provider_settings.get("draft_rounds")
            draft_rounds = (
                raw_rounds
                if isinstance(raw_rounds, int)
                and not isinstance(raw_rounds, bool)
                and raw_rounds >= 0
                else 0
            )
            settings[season.competition_season_id] = SnapshotSeasonSettings(
                playoff_start_week=records.league.playoff_start_week,
                playoff_team_count=records.league.playoff_team_count,
                draft_rounds=draft_rounds,
                league_average_match=records.league.league_average_match,
            )

        requirements, resolved_seasons = _plan_requirements(
            request.snapshot,
            lineage,
            cutoffs,
            settings,
        )
        remaining_scopes = tuple(
            scope
            for scope in requirements.scope_keys
            if scope not in league_candidates
        )
        candidates = dict(league_candidates)
        candidates.update(self._latest(remaining_scopes))
        _validate_candidates(requirements, candidates)

        global_scope = build_player_catalog_request().scope_key
        for season in resolved_seasons:
            missing = tuple(
                scope
                for scope in season.requirement_scopes
                if scope != global_scope and scope not in candidates
            )
            if missing:
                return _refresh_state(
                    season.identity,
                    season.through_week,
                    RefreshNeedReason.MISSING,
                    missing,
                    (
                        candidate
                        for scope, candidate in candidates.items()
                        if scope in season.requirement_scopes
                    ),
                )
        if global_scope not in candidates:
            primary = resolved_seasons[-1]
            return _refresh_state(
                primary.identity,
                primary.through_week,
                RefreshNeedReason.MISSING,
                (global_scope,),
                candidates.values(),
            )

        roster_candidates = tuple(
            candidates[
                build_league_rosters_request(
                    season.identity.competition_season_id,
                    season.identity.sleeper_league_id,
                ).scope_key
            ]
            for season in resolved_seasons
        )
        roster_payloads = self._payload_values(roster_candidates)
        stored_mappings = self._mappings.list_snapshot_mappings(
            [season.identity.competition_season_id for season in resolved_seasons]
        )
        resolved_mappings = _resolve_mappings(
            resolved_seasons,
            roster_payloads,
            stored_mappings,
        )
        if isinstance(resolved_mappings, MapSeasonRosters):
            if resolved_mappings.season.sequence_number == 1:
                season = next(
                    item
                    for item in resolved_seasons
                    if item.identity.competition_season_id
                    == resolved_mappings.season.competition_season_id
                )
                roster_scope = build_league_rosters_request(
                    season.identity.competition_season_id,
                    season.identity.sleeper_league_id,
                ).scope_key
                return _refresh_state(
                    season.identity,
                    season.through_week,
                    RefreshNeedReason.MISSING,
                    (roster_scope,),
                    (
                        candidate
                        for scope, candidate in candidates.items()
                        if scope in season.requirement_scopes
                    ),
                )
            return resolved_mappings

        primary = resolved_seasons[-1]
        if (
            request.mode is SnapshotPreparationMode.LIVE
            and lineage.primary_is_latest
        ):
            primary_candidates = [
                candidates[scope]
                for scope in primary.requirement_scopes
                if scope != global_scope
            ]
            oldest = min(candidate.completed_at for candidate in primary_candidates)
            if request.requested_at - oldest > self._live_max_age:
                return _refresh_state(
                    primary.identity,
                    primary.through_week,
                    RefreshNeedReason.STALE,
                    (),
                    primary_candidates,
                )

        manifest = SelectedRequestManifest(
            entries=tuple(
                _manifest_entry(requirement, candidates[requirement.request.scope_key])
                for requirement in requirements.entries
            )
        )
        return ResolvedSnapshotInputs(
            primary=request.snapshot,
            seasons=resolved_seasons,
            requirements=requirements,
            manifest=manifest,
            roster_mappings=resolved_mappings,
            input_revision=_input_revision(
                resolved_seasons,
                manifest,
                resolved_mappings,
            ),
        )

    def _latest(
        self,
        scopes: tuple[ScopeKey, ...],
    ) -> dict[ScopeKey, ApiRequestCandidate]:
        if not scopes:
            return {}
        candidates = self._requests.list_latest_complete_candidates(
            LatestCompleteCandidatesQuery(scope_keys=scopes)
        )
        by_scope = {candidate.scope_key: candidate for candidate in candidates}
        if len(by_scope) != len(candidates) or any(scope not in scopes for scope in by_scope):
            raise DatalayerScopeConflict(
                "latest candidate reader returned contradictory scope membership"
            )
        return by_scope

    def _payload_values(
        self,
        candidates: tuple[ApiRequestCandidate, ...],
    ) -> tuple[JsonValue, ...]:
        payloads = self._requests.resolve_verified_payloads(
            [candidate.request_id for candidate in candidates]
        )
        if len(payloads) != len(candidates):
            raise DatalayerScopeConflict(
                "resolved payload count does not match selected candidates"
            )
        values: list[JsonValue] = []
        for candidate, payload in zip(candidates, payloads, strict=True):
            if (
                payload.request_id != candidate.request_id
                or payload.scope_key != candidate.scope_key
                or payload.sha256 != candidate.response_sha256
            ):
                raise DatalayerScopeConflict(
                    "resolved payload does not match its selected candidate"
                )
            if isinstance(payload, InlineVerifiedPayload):
                values.append(payload.payload)
            elif isinstance(payload, ObjectVerifiedPayload):
                artifact = self._files.open_verified(
                    payload.storage_key,
                    expected_sha256=payload.sha256,
                    expected_byte_length=payload.byte_length,
                )
                values.append(parse_json_bytes(Path(artifact.path).read_bytes()))
            else:
                raise AssertionError(f"unsupported payload type: {type(payload)!r}")
        return tuple(values)


def _plan_requirements(
    request: SnapshotRequest,
    lineage: SnapshotLineage,
    cutoffs: dict[UUID, int],
    settings: dict[UUID, SnapshotSeasonSettings],
) -> tuple[SnapshotRequirements, tuple[ResolvedSnapshotSeason, ...]]:
    entries: list[SnapshotRequirement] = []
    seasons: list[ResolvedSnapshotSeason] = []
    for identity in lineage.seasons:
        season_settings = settings[identity.competition_season_id]
        through_week = cutoffs[identity.competition_season_id]
        season_entries = _season_requirements(identity, through_week, season_settings)
        entries.extend(season_entries)
        seasons.append(
            ResolvedSnapshotSeason(
                identity=identity,
                role=(
                    SnapshotSeasonRole.PRIMARY
                    if identity.competition_season_id == request.competition_season_id
                    else SnapshotSeasonRole.HISTORY
                ),
                through_week=through_week,
                settings=season_settings,
                requirement_scopes=tuple(
                    item.request.scope_key for item in season_entries
                ),
            )
        )
    entries.append(
        SnapshotRequirement(
            request=build_player_catalog_request(),
            selection_role=SnapshotSelectionRole.PLAYER_CATALOG,
        )
    )
    return SnapshotRequirements(entries=tuple(entries)), tuple(seasons)


def _season_requirements(
    season: SnapshotSeasonIdentity,
    through_week: int,
    settings: SnapshotSeasonSettings,
) -> tuple[SnapshotRequirement, ...]:
    season_id = season.competition_season_id
    league_id = season.sleeper_league_id
    entries = [
        SnapshotRequirement(
            request=build_league_request(season_id, league_id),
            selection_role=SnapshotSelectionRole.LEAGUE,
        ),
        SnapshotRequirement(
            request=build_league_users_request(season_id, league_id),
            selection_role=SnapshotSelectionRole.LEAGUE_USERS,
        ),
        SnapshotRequirement(
            request=build_league_rosters_request(season_id, league_id),
            selection_role=SnapshotSelectionRole.LEAGUE_ROSTERS,
        ),
    ]
    if settings.draft_rounds > 0:
        entries.append(
            SnapshotRequirement(
                request=build_traded_picks_request(season_id, league_id),
                selection_role=SnapshotSelectionRole.TRADED_PICKS,
            )
        )
    for week in range(1, through_week + 1):
        entries.extend(
            (
                SnapshotRequirement(
                    request=build_matchups_request(season_id, league_id, week),
                    selection_role=SnapshotSelectionRole.WEEK_MATCHUPS,
                ),
                SnapshotRequirement(
                    request=build_transactions_request(season_id, league_id, week),
                    selection_role=SnapshotSelectionRole.WEEK_TRANSACTIONS,
                ),
            )
        )
    if settings.playoff_start_week is None or through_week >= settings.playoff_start_week:
        entries.extend(
            (
                SnapshotRequirement(
                    request=build_winners_bracket_request(season_id, league_id),
                    selection_role=SnapshotSelectionRole.WINNERS_BRACKET,
                ),
                SnapshotRequirement(
                    request=build_losers_bracket_request(season_id, league_id),
                    selection_role=SnapshotSelectionRole.LOSERS_BRACKET,
                ),
            )
        )
    return tuple(entries)


def _validate_candidates(
    requirements: SnapshotRequirements,
    candidates: dict[ScopeKey, ApiRequestCandidate],
) -> None:
    for requirement in requirements.entries:
        candidate = candidates.get(requirement.request.scope_key)
        if candidate is None:
            continue
        expected = requirement.request
        expected_season = _scope_season(expected.scope_key)
        if (
            candidate.endpoint_kind is not expected.endpoint_kind
            or candidate.week != expected.week
            or candidate.bracket_kind != expected.bracket_kind
            or candidate.competition_season_id != expected_season
        ):
            raise DatalayerScopeConflict(
                "latest candidate metadata conflicts with its exact requirement"
            )


def _resolve_mappings(
    seasons: tuple[ResolvedSnapshotSeason, ...],
    roster_payloads: tuple[JsonValue, ...],
    stored: tuple[CoreRosterIdentity, ...],
) -> tuple[ResolvedRosterMapping, ...] | MapSeasonRosters:
    by_season: dict[UUID, list[CoreRosterIdentity]] = {
        season.identity.competition_season_id: [] for season in seasons
    }
    for mapping in stored:
        target = by_season.get(mapping.competition_season_id)
        if target is None:
            raise DatalayerScopeConflict("roster mapping is outside snapshot lineage")
        target.append(mapping)
    resolved: list[ResolvedRosterMapping] = []
    for season, payload in zip(seasons, roster_payloads, strict=True):
        endpoint = build_league_rosters_request(
            season.identity.competition_season_id,
            season.identity.sleeper_league_id,
        )
        records = normalize_league_rosters(payload, endpoint)
        observed = {roster.sleeper_roster_id for roster in records.rosters}
        mappings = by_season[season.identity.competition_season_id]
        mapped = {mapping.sleeper_roster_id: mapping for mapping in mappings}
        if len(mapped) != len(mappings):
            raise DatalayerScopeConflict("season has duplicate Sleeper roster mappings")
        franchise_ids = [mapping.franchise_id for mapping in mappings]
        season_roster_ids = [mapping.id for mapping in mappings]
        if (
            len(franchise_ids) != len(set(franchise_ids))
            or len(season_roster_ids) != len(set(season_roster_ids))
        ):
            raise DatalayerScopeConflict("season roster mappings are not one-to-one")
        missing = tuple(sorted(observed - set(mapped)))
        if missing:
            return MapSeasonRosters(season=season.identity, roster_ids=missing)
        if set(mapped) - observed:
            raise DatalayerScopeConflict(
                "season roster mapping is absent from the selected roster payload"
            )
        resolved.extend(
            ResolvedRosterMapping(
                competition_id=season.identity.competition_id,
                competition_season_id=season.identity.competition_season_id,
                sleeper_roster_id=mapping.sleeper_roster_id,
                season_roster_id=mapping.id,
                franchise_id=mapping.franchise_id,
            )
            for mapping in sorted(mappings, key=lambda item: item.sleeper_roster_id)
        )
    return tuple(resolved)


def _manifest_entry(
    requirement: SnapshotRequirement,
    candidate: ApiRequestCandidate,
) -> SelectedRequestManifestEntry:
    return SelectedRequestManifestEntry(
        request_id=candidate.request_id,
        endpoint_kind=candidate.endpoint_kind,
        scope_key=candidate.scope_key,
        selection_role=requirement.selection_role,
        response_sha256=candidate.response_sha256,
    )


def _refresh_state(
    season: SnapshotSeasonIdentity,
    through_week: int,
    reason: RefreshNeedReason,
    missing_scopes: tuple[ScopeKey, ...],
    candidates: Iterable[ApiRequestCandidate],
) -> RefreshSeason:
    candidate_values = tuple(candidates)
    return RefreshSeason(
        season=season,
        through_week=through_week,
        reason=reason,
        missing_scopes=tuple(sorted(missing_scopes, key=lambda item: item.value)),
        coverage_fingerprint=canonical_json_sha256(
            {
                "candidates": [
                    {
                        "completed_at": candidate.completed_at.isoformat(),
                        "request_id": str(candidate.request_id),
                        "response_sha256": candidate.response_sha256,
                        "scope_key": candidate.scope_key.value,
                    }
                    for candidate in sorted(
                        candidate_values, key=lambda item: item.scope_key.value
                    )
                ],
                "missing_scopes": sorted(scope.value for scope in missing_scopes),
                "season_id": str(season.competition_season_id),
                "through_week": through_week,
            }
        ),
    )


def _input_revision(
    seasons: tuple[ResolvedSnapshotSeason, ...],
    manifest: SelectedRequestManifest,
    mappings: tuple[ResolvedRosterMapping, ...],
) -> str:
    return canonical_json_sha256(
        {
            "mappings": [
                {
                    "competition_season_id": str(mapping.competition_season_id),
                    "franchise_id": str(mapping.franchise_id),
                    "season_roster_id": str(mapping.season_roster_id),
                    "sleeper_roster_id": mapping.sleeper_roster_id,
                }
                for mapping in sorted(
                    mappings,
                    key=lambda item: (
                        str(item.competition_season_id),
                        item.sleeper_roster_id,
                    ),
                )
            ],
            "seasons": [
                {
                    "competition_season_id": str(season.identity.competition_season_id),
                    "role": season.role.value,
                    "season_year": season.identity.season_year,
                    "sequence_number": season.identity.sequence_number,
                    "sleeper_league_id": season.identity.sleeper_league_id,
                    "through_week": season.through_week,
                }
                for season in seasons
            ],
            "sources": [
                {
                    "response_sha256": entry.response_sha256,
                    "scope_key": entry.scope_key.value,
                }
                for entry in sorted(
                    manifest.entries, key=lambda item: item.scope_key.value
                )
            ],
        }
    )


def _scope_season(scope: ScopeKey) -> UUID | None:
    parts = scope.value.split(":")
    if parts[0] == EndpointKind.PLAYER_CATALOG.value:
        return None
    try:
        return UUID(parts[1])
    except (IndexError, ValueError) as error:
        raise DatalayerScopeConflict("snapshot scope has no season identity") from error


__all__ = [
    "MapSeasonRosters",
    "PrepareSnapshotRequest",
    "RefreshSeason",
    "ResolutionState",
    "ResolvedRosterMapping",
    "ResolvedSnapshotInputs",
    "ResolvedSnapshotSeason",
    "SnapshotInputResolver",
    "SnapshotPreparationMode",
    "SnapshotSeasonSettings",
]
