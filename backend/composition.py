"""Typed construction functions for backend process dependencies."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from backend.config import DatabaseSettings, DatalayerSettings
from backend.database.engine import build_runtime_engine
from backend.database.health import assert_database_ready, read_database_health
from backend.database.sessions import SessionFactory, create_session_factory
from backend.resources.context import ManagerContext
from backend.resources.sleeper_data.manager import SleeperDataManager
from backend.services.datalayer.local_files import LocalDatalayerFileStore
from backend.services.datalayer.refresh_service import DatalayerRefreshService
from backend.services.datalayer.sleeper.client import SleeperSourceClient


class ApiRuntimeDependencies(Protocol):
    """Dependencies the HTTP process needs from its composition root."""

    def assert_ready(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ApiRuntime:
    """Long-lived dependencies owned by one API process."""

    engine: Engine
    session_factory: SessionFactory
    datalayer_settings: DatalayerSettings
    datalayer_file_store: LocalDatalayerFileStore
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


def build_api_runtime() -> ApiRuntime:
    """Construct the API runtime from environment-backed configuration."""

    settings = DatabaseSettings.from_environment("api")
    url = make_url(settings.runtime_url)
    if url.database is None or url.username is None:
        raise ValueError("database URL must include a database and runtime user")
    datalayer_settings = DatalayerSettings.from_environment()
    datalayer_file_store = LocalDatalayerFileStore(datalayer_settings.data_root)
    engine = build_runtime_engine(settings.engine_settings("api"))
    return ApiRuntime(
        engine=engine,
        session_factory=create_session_factory(engine),
        datalayer_settings=datalayer_settings,
        datalayer_file_store=datalayer_file_store,
        expected_database=url.database,
        expected_role=url.username,
        require_tls=settings.require_tls,
    )


@contextmanager
def open_datalayer_refresh_service(
    runtime: ApiRuntime,
    context: ManagerContext,
) -> Iterator[DatalayerRefreshService]:
    """Construct one competition-scoped refresh service and close its HTTP client."""

    settings = runtime.datalayer_settings
    source_client = SleeperSourceClient(
        base_url=settings.sleeper_base_url,
        timeout_seconds=settings.sleeper_timeout_seconds,
    )
    try:
        yield DatalayerRefreshService(
            source_client=source_client,
            data_manager=SleeperDataManager(runtime.session_factory, context),
            file_store=runtime.datalayer_file_store,
            inline_payload_threshold_bytes=settings.inline_payload_threshold_bytes,
            code_version=settings.code_version,
        )
    finally:
        source_client.close()
