"""Typed Sleeper resources, grouped by resource kind."""

from backend.resources.sleeper_data.common import Page
from backend.resources.sleeper_data.league_seasons import (
    LeagueSeasonManager,
    LeagueSeasonOverview,
    RefreshSeasonIdentity,
    SnapshotPlanningContext,
)
from backend.resources.sleeper_data.matchups import (
    Matchup,
    MatchupManager,
    PlayerPerformance,
)
from backend.resources.sleeper_data.normalized_scopes import (
    ApplyResult,
    NormalizedScopeManager,
)
from backend.resources.sleeper_data.players import Player, PlayerManager, PlayerSearch
from backend.resources.sleeper_data.refreshes import (
    PlannedEndpointScope,
    RefreshRun,
    RefreshRunManager,
    RefreshRunPage,
    RefreshRunQuery,
    StartRefresh,
)
from backend.resources.sleeper_data.requests import (
    ApiRequest,
    ApiRequestCandidate,
    ApiRequestManager,
    InlineVerifiedPayload,
    NormalizationRejection,
    ObjectVerifiedPayload,
    RecordApiAttempt,
    SnapshotCandidateQuery,
    VerifiedPayload,
)
from backend.resources.sleeper_data.rosters import (
    RosterManager,
    RosterManagerAssignment,
    RosterPlayer,
    SeasonRosterIdentity,
    SeasonRosterState,
)
from backend.resources.sleeper_data.snapshots import (
    ArtifactFailure,
    BeginSnapshotBuild,
    ClaimedSnapshotBuild,
    DataSnapshot,
    DataSnapshotManager,
    DataSnapshotPage,
    DataSnapshotQuery,
    ExistingBuildingSnapshot,
    ExistingReadySnapshot,
    SealSnapshot,
    SnapshotBuildState,
    SnapshotFailure,
    SnapshotRequestMembership,
)
from backend.resources.sleeper_data.transactions import (
    Transaction,
    TransactionManager,
    TransactionMove,
    TransactionQuery,
)

__all__ = [
    "ApiRequest",
    "ApiRequestCandidate",
    "ApiRequestManager",
    "ArtifactFailure",
    "ApplyResult",
    "BeginSnapshotBuild",
    "ClaimedSnapshotBuild",
    "DataSnapshot",
    "DataSnapshotManager",
    "DataSnapshotPage",
    "DataSnapshotQuery",
    "ExistingBuildingSnapshot",
    "ExistingReadySnapshot",
    "InlineVerifiedPayload",
    "LeagueSeasonManager",
    "LeagueSeasonOverview",
    "Matchup",
    "MatchupManager",
    "NormalizationRejection",
    "NormalizedScopeManager",
    "ObjectVerifiedPayload",
    "Page",
    "PlannedEndpointScope",
    "Player",
    "PlayerManager",
    "PlayerPerformance",
    "PlayerSearch",
    "RecordApiAttempt",
    "RefreshRun",
    "RefreshRunManager",
    "RefreshRunPage",
    "RefreshRunQuery",
    "RefreshSeasonIdentity",
    "RosterManager",
    "RosterManagerAssignment",
    "RosterPlayer",
    "SealSnapshot",
    "SeasonRosterState",
    "SeasonRosterIdentity",
    "SnapshotCandidateQuery",
    "SnapshotBuildState",
    "SnapshotFailure",
    "SnapshotPlanningContext",
    "SnapshotRequestMembership",
    "StartRefresh",
    "Transaction",
    "TransactionManager",
    "TransactionMove",
    "TransactionQuery",
    "VerifiedPayload",
]
