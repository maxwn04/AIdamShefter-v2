"""Bounded resolve/act facade for multi-season snapshot preparation."""

from __future__ import annotations

from typing import Protocol, assert_never
from uuid import UUID

from backend.resources._contracts import ContractModel
from backend.services.datalayer.contracts import ReadyDataSnapshot
from backend.services.datalayer.errors import (
    RosterIdentityMappingRequired,
    SnapshotInputsUnavailable,
)
from backend.services.datalayer.refresh_coordination import RefreshReceipt
from backend.services.datalayer.snapshot_inputs import (
    MapSeasonRosters,
    PrepareSnapshotRequest,
    RefreshSeason,
    ResolvedSnapshotInputs,
    ResolutionState,
)


class PreparedSnapshot(ContractModel):
    snapshot: ReadyDataSnapshot
    refresh_receipts: tuple[RefreshReceipt, ...] = ()


class SnapshotInputsResolver(Protocol):
    def resolve(self, request: PrepareSnapshotRequest) -> ResolutionState: ...


class AutomaticRefreshCoordinator(Protocol):
    def ensure(self, need: RefreshSeason) -> RefreshReceipt: ...


class ResolvedSnapshotBuilder(Protocol):
    def get_or_create(self, inputs: ResolvedSnapshotInputs) -> ReadyDataSnapshot: ...


class DatalayerSnapshotPreparationService:
    """Resolve one action at a time and hand only frozen inputs to a builder."""

    def __init__(
        self,
        *,
        resolver: SnapshotInputsResolver,
        refreshes: AutomaticRefreshCoordinator,
        builder: ResolvedSnapshotBuilder,
    ) -> None:
        self._resolver = resolver
        self._refreshes = refreshes
        self._builder = builder

    def get_or_create(self, request: PrepareSnapshotRequest) -> PreparedSnapshot:
        attempted_seasons: set[UUID] = set()
        receipts: list[RefreshReceipt] = []
        while True:
            state = self._resolver.resolve(request)
            if isinstance(state, ResolvedSnapshotInputs):
                return PreparedSnapshot(
                    snapshot=self._builder.get_or_create(state),
                    refresh_receipts=tuple(receipts),
                )
            if isinstance(state, RefreshSeason):
                season_id = state.season.competition_season_id
                if season_id in attempted_seasons:
                    raise SnapshotInputsUnavailable(
                        season_id,
                        state.missing_scopes,
                    )
                attempted_seasons.add(season_id)
                receipts.append(self._refreshes.ensure(state))
                continue
            if isinstance(state, MapSeasonRosters):
                raise RosterIdentityMappingRequired(
                    "Sleeper rosters require durable franchise mappings",
                    competition_season_id=(
                        state.season.competition_season_id
                    ),
                    sleeper_roster_ids=state.roster_ids,
                )
            assert_never(state)


__all__ = [
    "DatalayerSnapshotPreparationService",
    "PreparedSnapshot",
    "ResolvedSnapshotBuilder",
]
