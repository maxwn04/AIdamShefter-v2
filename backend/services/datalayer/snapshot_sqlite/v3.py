"""Pure multi-season projection over a frozen resolved input set."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Literal

from pydantic import model_validator

from backend.resources._contracts import ContractModel
from backend.resources.sleeper_data.league_seasons import SnapshotPlanningContext
from backend.resources.sleeper_data.rosters import SeasonRosterIdentity
from backend.resources.sleeper_data.snapshots import SnapshotSeasonRole
from backend.services.datalayer.contracts import SnapshotRequest
from backend.services.datalayer.snapshot_inputs import (
    ResolvedSnapshotInputs,
    ResolvedSnapshotSeason,
    Sha256,
)
from backend.services.datalayer.snapshot_selection import SelectedRequestManifest
from backend.services.datalayer.snapshot_service import (
    SnapshotEndpointRecords,
    SnapshotMaterializationInput,
)
from backend.services.datalayer.snapshot_sqlite.derivations import derive_snapshot_rows
from backend.services.datalayer.snapshot_sqlite.projection import (
    SnapshotProjection,
    project_source_records,
)
from backend.services.datalayer.sleeper.scope import EndpointKind


class ResolvedSnapshotMaterializationInput(ContractModel):
    """The complete immutable input accepted by projection version 3."""

    inputs: ResolvedSnapshotInputs
    build_key: Sha256
    snapshot_projection_version: Literal["3"] = "3"
    endpoint_records: tuple[SnapshotEndpointRecords, ...]

    @model_validator(mode="after")
    def validate_frozen_coverage(self) -> "ResolvedSnapshotMaterializationInput":
        manifest = self.inputs.manifest.entries
        if tuple(item.manifest_entry for item in self.endpoint_records) != manifest:
            raise ValueError("snapshot endpoint records must follow the frozen manifest")

        seasons = self.inputs.seasons
        competition_ids = {season.identity.competition_id for season in seasons}
        season_ids = [season.identity.competition_season_id for season in seasons]
        league_ids = [season.identity.sleeper_league_id for season in seasons]
        years = [season.identity.season_year for season in seasons]
        sequences = [season.identity.sequence_number for season in seasons]
        if len(competition_ids) != 1:
            raise ValueError("resolved snapshot seasons must share one competition")
        for values, label in (
            (season_ids, "competition-season IDs"),
            (league_ids, "league IDs"),
            (years, "season years"),
            (sequences, "season sequences"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"resolved snapshot seasons require unique {label}")
        if sequences != sorted(sequences):
            raise ValueError("resolved snapshot seasons must be oldest to primary")
        if seasons[-1].role is not SnapshotSeasonRole.PRIMARY:
            raise ValueError("resolved snapshot lineage must end with the primary")
        if any(
            season.through_week != 18
            for season in seasons[:-1]
            if season.role is SnapshotSeasonRole.HISTORY
        ):
            raise ValueError("historical snapshot seasons require a week-18 cutoff")

        season_scopes = tuple(
            scope for season in seasons for scope in season.requirement_scopes
        )
        if len(season_scopes) != len(set(season_scopes)):
            raise ValueError("snapshot season requirements overlap")
        global_scopes = tuple(
            requirement.request.scope_key
            for requirement in self.inputs.requirements.entries
            if requirement.request.endpoint_kind is EndpointKind.PLAYER_CATALOG
        )
        if len(global_scopes) != 1:
            raise ValueError("resolved snapshot requires one player catalog")
        if self.inputs.requirements.scope_keys != season_scopes + global_scopes:
            raise ValueError("resolved snapshot requirements do not exactly cover seasons")

        mapping_seasons = {
            mapping.competition_season_id
            for mapping in self.inputs.roster_mappings
        }
        if mapping_seasons - set(season_ids):
            raise ValueError("resolved roster mappings are outside snapshot lineage")
        return self


def project_resolved_snapshot(
    materialization: ResolvedSnapshotMaterializationInput,
) -> SnapshotProjection:
    """Project and derive every season independently, then merge canonically."""

    rows: dict[str, list[dict[str, Any]]] = {}
    warnings = []
    provenance = []
    for season in materialization.inputs.seasons:
        single = _single_season_input(materialization, season)
        source = project_source_records(single)
        projection = derive_snapshot_rows(single, source)
        league_id = season.identity.sleeper_league_id
        for table_name, table_rows in projection.rows.items():
            for row in table_rows:
                value = dict(row)
                if table_name in {"users", "transaction_moves"}:
                    value["league_id"] = league_id
                rows.setdefault(table_name, []).append(value)
        warnings.extend(projection.warnings)
        provenance.extend(projection.provenance)

    competition_id = str(materialization.inputs.seasons[0].identity.competition_id)
    rows["snapshot_seasons"] = [
        {
            "competition_id": competition_id,
            "competition_season_id": str(season.identity.competition_season_id),
            "league_id": season.identity.sleeper_league_id,
            "season_year": season.identity.season_year,
            "sequence_number": season.identity.sequence_number,
            "role": season.role.value,
            "through_week": season.through_week,
        }
        for season in materialization.inputs.seasons
    ]
    frozen_rows = MappingProxyType(
        {
            table: tuple(
                MappingProxyType(row)
                for row in sorted(table_rows, key=lambda item: repr(sorted(item.items())))
            )
            for table, table_rows in rows.items()
        }
    )
    frozen_warnings = tuple(
        sorted(
            set(warnings),
            key=lambda warning: (
                warning.code,
                warning.scope_key.value if warning.scope_key else "",
            ),
        )
    )
    return SnapshotProjection(
        rows=frozen_rows,
        warnings=frozen_warnings,
        provenance=tuple(sorted(provenance, key=lambda item: (
            item.table_name,
            item.row_key,
            item.scope_key.value,
        ))),
    )


def _single_season_input(
    materialization: ResolvedSnapshotMaterializationInput,
    season: ResolvedSnapshotSeason,
) -> SnapshotMaterializationInput:
    global_scope = next(
        requirement.request.scope_key
        for requirement in materialization.inputs.requirements.entries
        if requirement.request.endpoint_kind is EndpointKind.PLAYER_CATALOG
    )
    selected_scopes = set(season.requirement_scopes)
    if season.role is SnapshotSeasonRole.PRIMARY:
        selected_scopes.add(global_scope)
    manifest = SelectedRequestManifest(
        entries=tuple(
            entry
            for entry in materialization.inputs.manifest.entries
            if entry.scope_key in selected_scopes
        )
    )
    endpoint_records = tuple(
        endpoint
        for endpoint in materialization.endpoint_records
        if endpoint.manifest_entry.scope_key in selected_scopes
    )
    identity = season.identity
    settings = season.settings
    planning = SnapshotPlanningContext(
        competition_id=identity.competition_id,
        competition_season_id=identity.competition_season_id,
        sleeper_league_id=identity.sleeper_league_id,
        season_year=identity.season_year,
        playoff_start_week=settings.playoff_start_week,
        playoff_team_count=settings.playoff_team_count,
        draft_rounds=settings.draft_rounds,
        league_average_match=settings.league_average_match,
    )
    roster_identities = tuple(
        SeasonRosterIdentity(
            competition_id=mapping.competition_id,
            competition_season_id=mapping.competition_season_id,
            season_roster_id=mapping.season_roster_id,
            franchise_id=mapping.franchise_id,
            sleeper_roster_id=mapping.sleeper_roster_id,
        )
        for mapping in materialization.inputs.roster_mappings
        if mapping.competition_season_id == identity.competition_season_id
    )
    return SnapshotMaterializationInput(
        request=SnapshotRequest(
            competition_season_id=identity.competition_season_id,
            through_week=season.through_week,
            as_of_date=materialization.inputs.primary.as_of_date,
        ),
        planning_context=planning,
        build_key=materialization.build_key,
        snapshot_projection_version="2",
        manifest=manifest,
        endpoint_records=endpoint_records,
        roster_identities=roster_identities,
    )


__all__ = [
    "ResolvedSnapshotMaterializationInput",
    "project_resolved_snapshot",
]
