"""Pure daily identity, requirement planning, and request selection."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from backend.resources._contracts import ContractModel
from backend.resources.sleeper_data.league_seasons import SnapshotPlanningContext
from backend.resources.sleeper_data.requests import ApiRequestCandidate
from backend.services.datalayer.canonical_json import canonical_json_sha256
from backend.services.datalayer.contracts import (
    SnapshotRequest,
    SnapshotSelectionRole,
)
from backend.services.datalayer.errors import (
    DatalayerScopeConflict,
    SnapshotUnavailable,
)
from backend.services.datalayer.sleeper.endpoints import (
    build_league_request,
    build_league_rosters_request,
    build_league_users_request,
    build_losers_bracket_request,
    build_matchups_request,
    build_nfl_state_request,
    build_player_catalog_request,
    build_traded_picks_request,
    build_transactions_request,
    build_winners_bracket_request,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
_GLOBAL_ENDPOINTS = {EndpointKind.NFL_STATE, EndpointKind.PLAYER_CATALOG}


class SnapshotRequirement(ContractModel):
    request: EndpointRequest
    selection_role: SnapshotSelectionRole


class SnapshotRequirements(ContractModel):
    entries: tuple[SnapshotRequirement, ...]

    @model_validator(mode="after")
    def validate_entries(self) -> "SnapshotRequirements":
        if not self.entries:
            raise ValueError("snapshot requirements must not be empty")
        scopes = [entry.request.scope_key for entry in self.entries]
        if len(scopes) != len(set(scopes)):
            raise ValueError("snapshot requirement scopes must be unique")
        return self

    @property
    def scope_keys(self) -> tuple[ScopeKey, ...]:
        return tuple(entry.request.scope_key for entry in self.entries)


class SelectedRequestManifestEntry(ContractModel):
    request_id: UUID
    endpoint_kind: EndpointKind
    scope_key: ScopeKey
    selection_role: SnapshotSelectionRole
    response_sha256: Sha256


class SelectedRequestManifest(ContractModel):
    entries: tuple[SelectedRequestManifestEntry, ...]

    @model_validator(mode="after")
    def validate_entries(self) -> "SelectedRequestManifest":
        if not self.entries:
            raise ValueError("selected request manifest must not be empty")
        request_ids = [entry.request_id for entry in self.entries]
        scopes = [entry.scope_key for entry in self.entries]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("selected request IDs must be unique")
        if len(scopes) != len(set(scopes)):
            raise ValueError("selected request scopes must be unique")
        return self


def canonical_snapshot_build_key(
    request: SnapshotRequest,
    snapshot_projection_version: str,
) -> str:
    """Return the stable daily identity before any candidate reads."""

    version = snapshot_projection_version
    if not version or version != version.strip():
        raise ValueError("snapshot projection version must not be empty")
    return canonical_json_sha256(
        {
            "as_of_date": request.as_of_date.isoformat(),
            "competition_season_id": str(request.competition_season_id),
            "snapshot_projection_version": version,
            "through_week": request.through_week,
        }
    )


def plan_snapshot_requirements(
    request: SnapshotRequest,
    context: SnapshotPlanningContext,
) -> SnapshotRequirements:
    """Expand stable season settings into the exact required request scopes."""

    if context.competition_season_id != request.competition_season_id:
        raise DatalayerScopeConflict("snapshot planning context is for another season")

    season_id = request.competition_season_id
    league_id = context.sleeper_league_id
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
            request=build_nfl_state_request(),
            selection_role=SnapshotSelectionRole.NFL_STATE,
        ),
        SnapshotRequirement(
            request=build_player_catalog_request(),
            selection_role=SnapshotSelectionRole.PLAYER_CATALOG,
        ),
        SnapshotRequirement(
            request=build_league_rosters_request(season_id, league_id),
            selection_role=SnapshotSelectionRole.LEAGUE_ROSTERS,
        ),
    ]
    if context.draft_rounds > 0:
        entries.append(
            SnapshotRequirement(
                request=build_traded_picks_request(season_id, league_id),
                selection_role=SnapshotSelectionRole.TRADED_PICKS,
            )
        )
    for week in range(1, request.through_week + 1):
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
    if (
        context.playoff_start_week is None
        or request.through_week >= context.playoff_start_week
    ):
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
    return SnapshotRequirements(entries=tuple(entries))


def select_snapshot_requests(
    request: SnapshotRequest,
    requirements: SnapshotRequirements,
    candidates: Iterable[ApiRequestCandidate],
) -> SelectedRequestManifest:
    """Select the latest structurally valid observation for every requirement."""

    by_scope: dict[ScopeKey, list[ApiRequestCandidate]] = {
        scope: [] for scope in requirements.scope_keys
    }
    for candidate in candidates:
        matching = by_scope.get(candidate.scope_key)
        if matching is not None:
            matching.append(candidate)

    selected: list[SelectedRequestManifestEntry] = []
    missing: list[ScopeKey] = []
    for requirement in requirements.entries:
        eligible = [
            candidate
            for candidate in by_scope[requirement.request.scope_key]
            if _candidate_is_eligible(request, requirement, candidate)
        ]
        if not eligible:
            missing.append(requirement.request.scope_key)
            continue
        candidate = max(
            eligible,
            key=lambda item: (item.requested_at, item.request_id.int),
        )
        selected.append(
            SelectedRequestManifestEntry(
                request_id=candidate.request_id,
                endpoint_kind=candidate.endpoint_kind,
                scope_key=candidate.scope_key,
                selection_role=requirement.selection_role,
                response_sha256=candidate.response_sha256,
            )
        )
    if missing:
        raise SnapshotUnavailable(
            "required snapshot inputs are unavailable",
            missing_scopes=missing,
        )
    return SelectedRequestManifest(entries=tuple(selected))


def _candidate_is_eligible(
    snapshot_request: SnapshotRequest,
    requirement: SnapshotRequirement,
    candidate: ApiRequestCandidate,
) -> bool:
    expected = requirement.request
    if candidate.endpoint_kind is not expected.endpoint_kind:
        raise DatalayerScopeConflict(
            "snapshot candidate endpoint does not match its required scope"
        )
    if candidate.endpoint_kind in _GLOBAL_ENDPOINTS:
        if candidate.competition_season_id is not None:
            raise DatalayerScopeConflict(
                "global snapshot candidate unexpectedly belongs to a season"
            )
    elif (
        candidate.competition_season_id
        != snapshot_request.competition_season_id
    ):
        raise DatalayerScopeConflict(
            "snapshot candidate belongs to another competition season"
        )
    if (
        candidate.week != expected.week
        or candidate.bracket_kind != expected.bracket_kind
    ):
        raise DatalayerScopeConflict(
            "snapshot candidate metadata does not match its required scope"
        )
    return candidate.week is None or candidate.week <= snapshot_request.through_week
