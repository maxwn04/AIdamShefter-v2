"""Pure contracts shared by datalayer workflows and later adapters."""

from typing import Any

from backend.services.datalayer.contracts import (
    ApplyDisposition,
    CompletenessWarning,
    NormalizationStatus,
    RefreshOutcome,
    RefreshRequest,
    RefreshStatus,
    RefreshTrigger,
    RequestStatus,
    ScopeRefreshResult,
    SnapshotSelectionRole,
    SnapshotStatus,
    SnapshotRequest,
    ReadyDataSnapshot,
    ReadySnapshotSeason,
    WarningCode,
)
from backend.services.datalayer.errors import (
    DatalayerError,
    DatalayerResourceNotFound,
    DatalayerScopeConflict,
    EndpointPayloadRejected,
    InternalDatalayerFailure,
    InvalidDatalayerRequest,
    RefreshUnavailable,
    RosterIdentityMappingRequired,
    SnapshotInputsUnavailable,
    SnapshotUnavailable,
)
from backend.services.datalayer.local_files import (
    LocalArtifactKind,
    LocalArtifactVerificationError,
    LocalDatalayerFileStore,
    StoredLocalArtifact,
    VerifiedLocalArtifact,
)
from backend.services.datalayer.sleeper.client import SleeperSourceClient
from backend.services.datalayer.sleeper.endpoints import (
    BracketMatchupRecord,
    CompletenessFinding,
    EndpointApplyMetadata,
    EndpointRecords,
    LeagueEndpointRecords,
    LeagueRecord,
    LeagueRostersEndpointRecords,
    LeagueUserRecord,
    LeagueUsersEndpointRecords,
    LosersBracketEndpointRecords,
    MatchupRecord,
    MatchupsEndpointRecords,
    NflStateEndpointRecords,
    NflStateRecord,
    PlayerCatalogEndpointRecords,
    PlayerPerformanceRecord,
    PlayerRecord,
    RosterManagerRecord,
    RosterPlayerRecord,
    RosterRecord,
    TradedPickRecord,
    TradedPicksEndpointRecords,
    TransactionMoveRecord,
    TransactionRecord,
    TransactionsEndpointRecords,
    UserRecord,
    WinnersBracketEndpointRecords,
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
    get_endpoint_apply_metadata,
    missing_dependency_scope_keys,
    normalize_league,
    normalize_league_rosters,
    normalize_league_users,
    normalize_losers_bracket,
    normalize_matchups,
    normalize_nfl_state,
    normalize_player_catalog,
    normalize_traded_picks,
    normalize_transactions,
    normalize_winners_bracket,
    validate_league_completeness,
    validate_league_rosters_completeness,
    validate_league_users_completeness,
    validate_losers_bracket_completeness,
    validate_matchups_completeness,
    validate_nfl_state_completeness,
    validate_player_catalog_completeness,
    validate_traded_picks_completeness,
    validate_transactions_completeness,
    validate_winners_bracket_completeness,
)
from backend.services.datalayer.sleeper.responses import (
    EndpointRequest,
    FailedSourceAttempt,
    SanitizedSourceError,
    SourceAttempt,
    SuccessfulSourceAttempt,
)
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey
from backend.services.datalayer.versions import (
    INGESTION_NORMALIZER_VERSION,
    RESOLVED_SNAPSHOT_PROJECTION_VERSION,
    SNAPSHOT_PROJECTION_VERSION,
)

__all__ = [
    "AmbiguousRosterIdentity",
    "ApplyDisposition",
    "BracketMatchupRecord",
    "CompletenessWarning",
    "CompletenessFinding",
    "EndpointApplyMetadata",
    "DatalayerError",
    "DatalayerRefreshService",
    "DatalayerResolvedSnapshotBuilder",
    "DatalayerSnapshotService",
    "DatalayerResourceNotFound",
    "DatalayerScopeConflict",
    "DatalayerSnapshotPreparationService",
    "EndpointKind",
    "EndpointRecords",
    "EndpointRequest",
    "EndpointPayloadRejected",
    "FailedSourceAttempt",
    "FrozenLeagueData",
    "FrozenRosterIdentity",
    "FrozenSnapshotInvalid",
    "INGESTION_NORMALIZER_VERSION",
    "InternalDatalayerFailure",
    "InvalidDatalayerRequest",
    "LocalArtifactKind",
    "LocalArtifactVerificationError",
    "LocalDatalayerFileStore",
    "MaterializedSnapshot",
    "MapSeasonRosters",
    "LeagueEndpointRecords",
    "LeagueRecord",
    "LeagueRostersEndpointRecords",
    "LeagueUserRecord",
    "LeagueUsersEndpointRecords",
    "LosersBracketEndpointRecords",
    "MatchupRecord",
    "MatchupsEndpointRecords",
    "NormalizationStatus",
    "NflStateEndpointRecords",
    "NflStateRecord",
    "PlayerCatalogEndpointRecords",
    "PlayerPerformanceRecord",
    "PlayerRecord",
    "PlannedRefresh",
    "PreparedSnapshot",
    "PrepareSnapshotRequest",
    "RefreshCoordinator",
    "RefreshOutcome",
    "RefreshReceipt",
    "RefreshReceiptDisposition",
    "RefreshRequest",
    "RefreshSeason",
    "RefreshStatus",
    "RefreshTrigger",
    "RefreshUnavailable",
    "ResolvedRosterMapping",
    "ResolvedSnapshotMaterializationInput",
    "ResolvedSnapshotInputs",
    "ResolvedSnapshotSeason",
    "ResolvedRosterIdentity",
    "RosterIdentityNotFound",
    "RosterIdentityResolution",
    "RosterManagerRecord",
    "RosterPlayerRecord",
    "RosterRecord",
    "SanitizedSourceError",
    "RequestStatus",
    "RosterIdentityMappingRequired",
    "SNAPSHOT_PROJECTION_VERSION",
    "RESOLVED_SNAPSHOT_PROJECTION_VERSION",
    "ScopeKey",
    "ScopeRefreshResult",
    "SQLiteSnapshotMaterializer",
    "SelectedRequestManifest",
    "SelectedRequestManifestEntry",
    "SnapshotRequirement",
    "SnapshotRequirements",
    "SnapshotRequest",
    "SnapshotEndpointRecords",
    "SnapshotInputResolver",
    "SnapshotInputsUnavailable",
    "SnapshotMaterializationInput",
    "SnapshotPreparationMode",
    "SnapshotSelectionRole",
    "SnapshotSeason",
    "SnapshotStatus",
    "SnapshotSeasonSettings",
    "SnapshotUnavailable",
    "ReadyDataSnapshot",
    "ReadySnapshotSeason",
    "SleeperSourceClient",
    "SourceAttempt",
    "StoredLocalArtifact",
    "SuccessfulSourceAttempt",
    "TradedPickRecord",
    "TradedPicksEndpointRecords",
    "TransactionMoveRecord",
    "TransactionRecord",
    "TransactionsEndpointRecords",
    "UserRecord",
    "VerifiedLocalArtifact",
    "WarningCode",
    "WinnersBracketEndpointRecords",
    "build_league_request",
    "build_league_rosters_request",
    "build_league_users_request",
    "build_losers_bracket_request",
    "build_matchups_request",
    "build_nfl_state_request",
    "build_player_catalog_request",
    "build_standard_refresh_plan",
    "canonical_snapshot_build_key",
    "canonical_resolved_snapshot_build_key",
    "build_traded_picks_request",
    "build_transactions_request",
    "build_winners_bracket_request",
    "get_endpoint_apply_metadata",
    "missing_dependency_scope_keys",
    "plan_snapshot_requirements",
    "normalize_league",
    "normalize_league_rosters",
    "normalize_league_users",
    "normalize_losers_bracket",
    "normalize_matchups",
    "normalize_nfl_state",
    "normalize_player_catalog",
    "normalize_traded_picks",
    "normalize_transactions",
    "normalize_winners_bracket",
    "validate_league_completeness",
    "validate_league_rosters_completeness",
    "validate_league_users_completeness",
    "validate_losers_bracket_completeness",
    "validate_matchups_completeness",
    "validate_nfl_state_completeness",
    "validate_player_catalog_completeness",
    "validate_traded_picks_completeness",
    "validate_transactions_completeness",
    "validate_winners_bracket_completeness",
    "select_snapshot_requests",
]


def __getattr__(name: str) -> Any:
    """Lazily expose resource-composing workflows without import cycles."""

    if name in {
        "DatalayerRefreshService",
        "PlannedRefresh",
        "build_standard_refresh_plan",
        "DatalayerSnapshotService",
        "DatalayerResolvedSnapshotBuilder",
        "MaterializedSnapshot",
        "SnapshotEndpointRecords",
        "SnapshotMaterializationInput",
        "SelectedRequestManifest",
        "SelectedRequestManifestEntry",
        "SnapshotRequirement",
        "SnapshotRequirements",
        "canonical_snapshot_build_key",
        "plan_snapshot_requirements",
        "select_snapshot_requests",
        "SQLiteSnapshotMaterializer",
        "ResolvedSnapshotMaterializationInput",
        "FrozenLeagueData",
        "FrozenRosterIdentity",
        "FrozenSnapshotInvalid",
        "AmbiguousRosterIdentity",
        "ResolvedRosterIdentity",
        "RosterIdentityNotFound",
        "RosterIdentityResolution",
        "DatalayerSnapshotPreparationService",
        "PreparedSnapshot",
        "RefreshCoordinator",
        "RefreshReceipt",
        "RefreshReceiptDisposition",
        "MapSeasonRosters",
        "PrepareSnapshotRequest",
        "RefreshSeason",
        "ResolvedRosterMapping",
        "ResolvedSnapshotInputs",
        "ResolvedSnapshotSeason",
        "SnapshotInputResolver",
        "SnapshotPreparationMode",
        "SnapshotSeason",
        "SnapshotSeasonSettings",
        "canonical_resolved_snapshot_build_key",
    }:
        if name in {
            "DatalayerSnapshotPreparationService",
            "PreparedSnapshot",
        }:
            from backend.services.datalayer.preparation_service import (
                DatalayerSnapshotPreparationService,
                PreparedSnapshot,
            )

            return {
                "DatalayerSnapshotPreparationService": (
                    DatalayerSnapshotPreparationService
                ),
                "PreparedSnapshot": PreparedSnapshot,
            }[name]
        if name in {
            "RefreshCoordinator",
            "RefreshReceipt",
            "RefreshReceiptDisposition",
        }:
            from backend.services.datalayer.refresh_coordination import (
                RefreshCoordinator,
                RefreshReceipt,
                RefreshReceiptDisposition,
            )

            return {
                "RefreshCoordinator": RefreshCoordinator,
                "RefreshReceipt": RefreshReceipt,
                "RefreshReceiptDisposition": RefreshReceiptDisposition,
            }[name]
        if name in {
            "MapSeasonRosters",
            "PrepareSnapshotRequest",
            "RefreshSeason",
            "ResolvedRosterMapping",
            "ResolvedSnapshotInputs",
            "ResolvedSnapshotSeason",
            "SnapshotInputResolver",
            "SnapshotPreparationMode",
            "SnapshotSeasonSettings",
        }:
            from backend.services.datalayer.snapshot_inputs import (
                MapSeasonRosters,
                PrepareSnapshotRequest,
                RefreshSeason,
                ResolvedRosterMapping,
                ResolvedSnapshotInputs,
                ResolvedSnapshotSeason,
                SnapshotInputResolver,
                SnapshotPreparationMode,
                SnapshotSeasonSettings,
            )

            return {
                "MapSeasonRosters": MapSeasonRosters,
                "PrepareSnapshotRequest": PrepareSnapshotRequest,
                "RefreshSeason": RefreshSeason,
                "ResolvedRosterMapping": ResolvedRosterMapping,
                "ResolvedSnapshotInputs": ResolvedSnapshotInputs,
                "ResolvedSnapshotSeason": ResolvedSnapshotSeason,
                "SnapshotInputResolver": SnapshotInputResolver,
                "SnapshotPreparationMode": SnapshotPreparationMode,
                "SnapshotSeasonSettings": SnapshotSeasonSettings,
            }[name]
        if name in {
            "AmbiguousRosterIdentity",
            "FrozenLeagueData",
            "FrozenRosterIdentity",
            "FrozenSnapshotInvalid",
            "ResolvedRosterIdentity",
            "RosterIdentityNotFound",
            "RosterIdentityResolution",
            "SnapshotSeason",
        }:
            from backend.services.datalayer.query import (
                AmbiguousRosterIdentity,
                FrozenLeagueData,
                FrozenRosterIdentity,
                FrozenSnapshotInvalid,
                ResolvedRosterIdentity,
                RosterIdentityNotFound,
                RosterIdentityResolution,
                SnapshotSeason,
            )

            return {
                "AmbiguousRosterIdentity": AmbiguousRosterIdentity,
                "FrozenLeagueData": FrozenLeagueData,
                "FrozenRosterIdentity": FrozenRosterIdentity,
                "FrozenSnapshotInvalid": FrozenSnapshotInvalid,
                "ResolvedRosterIdentity": ResolvedRosterIdentity,
                "RosterIdentityNotFound": RosterIdentityNotFound,
                "RosterIdentityResolution": RosterIdentityResolution,
                "SnapshotSeason": SnapshotSeason,
            }[name]
        if name == "SQLiteSnapshotMaterializer":
            from backend.services.datalayer.snapshot_sqlite import (
                SQLiteSnapshotMaterializer,
            )

            return SQLiteSnapshotMaterializer
        if name == "ResolvedSnapshotMaterializationInput":
            from backend.services.datalayer.snapshot_sqlite import (
                ResolvedSnapshotMaterializationInput,
            )

            return ResolvedSnapshotMaterializationInput
        if name in {
            "DatalayerResolvedSnapshotBuilder",
            "canonical_resolved_snapshot_build_key",
        }:
            from backend.services.datalayer.resolved_snapshot_builder import (
                DatalayerResolvedSnapshotBuilder,
                canonical_resolved_snapshot_build_key,
            )

            return {
                "DatalayerResolvedSnapshotBuilder": DatalayerResolvedSnapshotBuilder,
                "canonical_resolved_snapshot_build_key": (
                    canonical_resolved_snapshot_build_key
                ),
            }[name]
        if name in {
            "DatalayerSnapshotService",
            "MaterializedSnapshot",
            "SnapshotEndpointRecords",
            "SnapshotMaterializationInput",
        }:
            from backend.services.datalayer.snapshot_service import (
                DatalayerSnapshotService,
                MaterializedSnapshot,
                SnapshotEndpointRecords,
                SnapshotMaterializationInput,
            )

            return {
                "DatalayerSnapshotService": DatalayerSnapshotService,
                "MaterializedSnapshot": MaterializedSnapshot,
                "SnapshotEndpointRecords": SnapshotEndpointRecords,
                "SnapshotMaterializationInput": SnapshotMaterializationInput,
            }[name]
        if name in {
            "SelectedRequestManifest",
            "SelectedRequestManifestEntry",
            "SnapshotRequirement",
            "SnapshotRequirements",
            "canonical_snapshot_build_key",
            "plan_snapshot_requirements",
            "select_snapshot_requests",
        }:
            from backend.services.datalayer.snapshot_selection import (
                SelectedRequestManifest,
                SelectedRequestManifestEntry,
                SnapshotRequirement,
                SnapshotRequirements,
                canonical_snapshot_build_key,
                plan_snapshot_requirements,
                select_snapshot_requests,
            )

            return {
                "SelectedRequestManifest": SelectedRequestManifest,
                "SelectedRequestManifestEntry": SelectedRequestManifestEntry,
                "SnapshotRequirement": SnapshotRequirement,
                "SnapshotRequirements": SnapshotRequirements,
                "canonical_snapshot_build_key": canonical_snapshot_build_key,
                "plan_snapshot_requirements": plan_snapshot_requirements,
                "select_snapshot_requests": select_snapshot_requests,
            }[name]
        from backend.services.datalayer.refresh_service import (
            DatalayerRefreshService,
            PlannedRefresh,
            build_standard_refresh_plan,
        )

        return {
            "DatalayerRefreshService": DatalayerRefreshService,
            "PlannedRefresh": PlannedRefresh,
            "build_standard_refresh_plan": build_standard_refresh_plan,
        }[name]
    raise AttributeError(name)
