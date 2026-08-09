"""Typed construction functions for backend process dependencies."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from backend.config import DatabaseSettings
from backend.database.engine import build_runtime_engine
from backend.database.health import assert_database_ready, read_database_health


class ApiRuntimeDependencies(Protocol):
    """Dependencies the HTTP process needs from its composition root."""

    def assert_ready(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ApiRuntime:
    """Long-lived dependencies owned by one API process."""

    engine: Engine
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
    engine = build_runtime_engine(settings.engine_settings("api"))
    return ApiRuntime(
        engine=engine,
        expected_database=url.database,
        expected_role=url.username,
        require_tls=settings.require_tls,
    )
