"""Typed construction functions for backend process dependencies."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from backend.config import (
    DatabaseSettings,
    DatalayerSettings,
    GenerationRuntimeSettings,
)
from backend.database.engine import build_runtime_engine
from backend.database.health import assert_database_ready, read_database_health
from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.context import (
    CompetitionScope,
    GlobalScope,
    ManagerContext,
)
from backend.resources.core import (
    CompetitionManager,
    CompetitionOverviewReader,
    CompetitionSeasonManager,
)
from backend.resources.memory.context_notes import ContextNoteManager
from backend.resources.memory.events import EventManager
from backend.resources.memory.facts import FactManager
from backend.resources.memory.revisions import RevisionManager
from backend.resources.memory.search_documents import SearchDocumentManager
from backend.resources.memory.storylines import StorylineManager
from backend.resources.memory.triggers import TriggerManager
from backend.resources.reporting.ai_calls import AICallManager
from backend.resources.reporting.artifact_versions import ArtifactVersionManager
from backend.resources.reporting.artifacts import ArtifactManager
from backend.resources.reporting.generations import GenerationManager
from backend.resources.reporting.tool_calls import ToolCallManager
from backend.resources.sleeper_data import (
    ApiRequestManager,
    DataSnapshotManager,
    LeagueSeasonManager,
    NormalizedScopeManager,
    RefreshRunManager,
    RosterManager,
)
from backend.services.datalayer import (
    DatalayerSnapshotService,
    LocalDatalayerFileStore,
    SQLiteSnapshotMaterializer,
    SleeperSourceClient,
)
from backend.services.datalayer.refresh_service import DatalayerRefreshService
from backend.services.generations import GenerationFinalizer, GenerationService
from backend.services.memory import MemoryMutationService, MemoryRetrievalService


class ApiRuntimeDependencies(Protocol):
    """Dependencies the HTTP process needs from its composition root."""

    def assert_ready(self) -> None: ...

    def close(self) -> None: ...


class MemoryApiRuntimeDependencies(ApiRuntimeDependencies, Protocol):
    """Runtime capabilities required by competition-scoped memory routes."""

    session_factory: SessionFactory


class GenerationRuntimeDependencies(ApiRuntimeDependencies, Protocol):
    """Runtime capabilities required by generation API and worker boundaries."""

    session_factory: SessionFactory


class CompetitionApiRuntimeDependencies(ApiRuntimeDependencies, Protocol):
    """Runtime capabilities required by competition product routes."""

    session_factory: SessionFactory


@dataclass(frozen=True, slots=True)
class ApiRuntime:
    """Long-lived dependencies owned by one API process."""

    engine: Engine
    session_factory: SessionFactory
    expected_database: str
    expected_role: str
    require_tls: bool

    def assert_ready(self) -> None:
        """Verify the API's bounded runtime database invariants."""

        health = read_database_health(self.engine)
        assert_database_ready(
            health,
            expected_database=self.expected_database,
            expected_role=self.expected_role,
            require_tls=self.require_tls,
        )

    def close(self) -> None:
        """Release process-owned connection-pool resources."""

        self.engine.dispose()


@dataclass(frozen=True, slots=True)
class WorkerRuntime:
    """Long-lived dependencies owned by one worker process."""

    engine: Engine
    session_factory: SessionFactory
    expected_database: str
    expected_role: str
    require_tls: bool

    def assert_ready(self) -> None:
        health = read_database_health(self.engine)
        assert_database_ready(
            health,
            expected_database=self.expected_database,
            expected_role=self.expected_role,
            require_tls=self.require_tls,
        )

    def close(self) -> None:
        self.engine.dispose()


@dataclass(frozen=True, slots=True)
class MemoryApiDependencies:
    """One request's competition-scoped memory managers and services."""

    revisions: RevisionManager
    facts: FactManager
    events: EventManager
    storylines: StorylineManager
    triggers: TriggerManager
    context_notes: ContextNoteManager
    retrieval: MemoryRetrievalService
    mutations: MemoryMutationService


@dataclass(frozen=True, slots=True)
class CompetitionCatalogDependencies:
    """One request's global competition catalog capabilities."""

    competitions: CompetitionManager
    overviews: CompetitionOverviewReader


@dataclass(frozen=True, slots=True)
class CompetitionSeasonDependencies:
    """One request's competition-scoped season capabilities."""

    seasons: CompetitionSeasonManager
    overviews: CompetitionOverviewReader


@dataclass(frozen=True, slots=True)
class DatalayerRefreshDependencies:
    """One scoped refresh service and its owned source transport."""

    refresh: DatalayerRefreshService
    source: SleeperSourceClient

    def close(self) -> None:
        self.source.close()


@dataclass(frozen=True, slots=True)
class DatalayerSnapshotDependencies:
    """One competition-scoped immutable snapshot capability."""

    snapshot: DatalayerSnapshotService


@dataclass(frozen=True, slots=True)
class GenerationDependencies:
    """One competition-scoped generation workflow and its read managers."""

    service: GenerationService
    generations: GenerationManager
    ai_calls: AICallManager
    tool_calls: ToolCallManager
    artifacts: ArtifactManager
    artifact_versions: ArtifactVersionManager


def build_competition_catalog_dependencies(
    session_factory: SessionFactory,
    context: ManagerContext[GlobalScope],
) -> CompetitionCatalogDependencies:
    """Compose global competition lifecycle and overview reads."""

    return CompetitionCatalogDependencies(
        competitions=CompetitionManager(session_factory, context),
        overviews=CompetitionOverviewReader(session_factory),
    )


def build_competition_season_dependencies(
    session_factory: SessionFactory,
    context: ManagerContext[CompetitionScope],
) -> CompetitionSeasonDependencies:
    """Compose scoped season lifecycle and overview reads."""

    return CompetitionSeasonDependencies(
        seasons=CompetitionSeasonManager(session_factory, context),
        overviews=CompetitionOverviewReader(session_factory),
    )


def build_memory_api_dependencies(
    session_factory: SessionFactory,
    context: ManagerContext[CompetitionScope],
) -> MemoryApiDependencies:
    """Compose memory capabilities for one already-resolved request context."""

    revisions = RevisionManager(session_factory, context)
    facts = FactManager(session_factory, context)
    events = EventManager(session_factory, context)
    storylines = StorylineManager(session_factory, context)
    triggers = TriggerManager(session_factory, context)
    context_notes = ContextNoteManager(session_factory, context)
    search_documents = SearchDocumentManager(session_factory, context)
    return MemoryApiDependencies(
        revisions=revisions,
        facts=facts,
        events=events,
        storylines=storylines,
        triggers=triggers,
        context_notes=context_notes,
        retrieval=MemoryRetrievalService(
            search_documents=search_documents,
            facts=facts,
            events=events,
            storylines=storylines,
            triggers=triggers,
            context_notes=context_notes,
        ),
        mutations=MemoryMutationService(revisions),
    )


def build_datalayer_refresh_dependencies(
    session_factory: SessionFactory,
    context: ManagerContext[CompetitionScope],
    *,
    settings: DatalayerSettings | None = None,
) -> DatalayerRefreshDependencies:
    """Compose one competition-scoped synchronous refresh capability."""

    resolved = settings or DatalayerSettings.from_environment()
    source = SleeperSourceClient(
        base_url=resolved.sleeper_base_url,
        timeout_seconds=resolved.sleeper_timeout_seconds,
    )
    refreshes = RefreshRunManager(session_factory, context)
    attempts = ApiRequestManager(session_factory, context)
    scopes = NormalizedScopeManager(session_factory, context)
    identities = LeagueSeasonManager(session_factory, context)
    files = LocalDatalayerFileStore(resolved.data_root)
    return DatalayerRefreshDependencies(
        refresh=DatalayerRefreshService(
            source=source,
            identities=identities,
            refreshes=refreshes,
            attempts=attempts,
            scopes=scopes,
            files=files,
            code_version=resolved.code_version,
            max_attempts=resolved.sleeper_max_attempts,
            retry_backoff_seconds=resolved.sleeper_retry_backoff_seconds,
            inline_payload_max_bytes=resolved.inline_payload_max_bytes,
        ),
        source=source,
    )


def build_datalayer_snapshot_dependencies(
    session_factory: SessionFactory,
    context: ManagerContext[CompetitionScope],
    *,
    settings: DatalayerSettings | None = None,
) -> DatalayerSnapshotDependencies:
    """Compose one competition-scoped snapshot service."""

    resolved = settings or DatalayerSettings.from_environment()
    files = LocalDatalayerFileStore(resolved.data_root)
    planning = LeagueSeasonManager(session_factory, context)
    return DatalayerSnapshotDependencies(
        snapshot=DatalayerSnapshotService(
            planning=planning,
            roster_identities=RosterManager(session_factory, context),
            requests=ApiRequestManager(session_factory, context),
            snapshots=DataSnapshotManager(session_factory, context),
            materializer=SQLiteSnapshotMaterializer(
                files.root / ".staging" / "snapshots"
            ),
            files=files,
            code_version=resolved.code_version,
        )
    )


def build_generation_dependencies(
    session_factory: SessionFactory,
    context: ManagerContext[CompetitionScope],
    *,
    datalayer_settings: DatalayerSettings | None = None,
    runtime_settings: GenerationRuntimeSettings | None = None,
) -> GenerationDependencies:
    """Compose one generation service and its competition-scoped read boundary."""

    runtime_revisions = runtime_settings or GenerationRuntimeSettings.from_environment()
    generations = GenerationManager(session_factory, context)
    ai_calls = AICallManager(session_factory, context)
    tool_calls = ToolCallManager(session_factory, context)
    artifacts = ArtifactManager(session_factory, context)
    artifact_versions = ArtifactVersionManager(session_factory, context)
    memory = build_memory_api_dependencies(session_factory, context)
    snapshots = build_datalayer_snapshot_dependencies(
        session_factory,
        context,
        settings=datalayer_settings,
    )
    service = GenerationService(
        generations=generations,
        snapshots=snapshots.snapshot,
        revisions=memory.revisions,
        retrieval=memory.retrieval,
        ai_calls=ai_calls,
        tool_calls=tool_calls,
        artifacts=artifacts,
        artifact_versions=artifact_versions,
        finalizer=GenerationFinalizer(session_factory, context),
        reporter_revision=runtime_revisions.reporter_revision,
        generation_revision=runtime_revisions.generation_revision,
    )
    return GenerationDependencies(
        service=service,
        generations=generations,
        ai_calls=ai_calls,
        tool_calls=tool_calls,
        artifacts=artifacts,
        artifact_versions=artifact_versions,
    )


def build_api_runtime() -> ApiRuntime:
    """Construct the API runtime from environment-backed configuration."""

    settings = DatabaseSettings.from_environment("api")
    url = make_url(settings.runtime_url)
    if url.database is None or url.username is None:
        raise ValueError("database URL must include a database and runtime user")
    engine = build_runtime_engine(settings.engine_settings("api"))
    return ApiRuntime(
        engine=engine,
        session_factory=create_session_factory(engine),
        expected_database=url.database,
        expected_role=url.username,
        require_tls=settings.require_tls,
    )


def build_worker_runtime() -> WorkerRuntime:
    """Construct the worker runtime from environment-backed configuration."""

    settings = DatabaseSettings.from_environment("worker")
    url = make_url(settings.runtime_url)
    if url.database is None or url.username is None:
        raise ValueError("database URL must include a database and runtime user")
    engine = build_runtime_engine(settings.engine_settings("worker"))
    return WorkerRuntime(
        engine=engine,
        session_factory=create_session_factory(engine),
        expected_database=url.database,
        expected_role=url.username,
        require_tls=settings.require_tls,
    )
