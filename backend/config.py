"""Environment-backed product configuration."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal

from backend.database.engine import EngineSettings


def _boolean(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    value = default if raw_value is None else int(raw_value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Database settings shared by API and worker composition roots."""

    runtime_url: str
    migration_url: str | None
    ca_file: Path | None
    pool_size: int
    max_overflow: int
    statement_timeout_ms: int
    require_tls: bool

    @classmethod
    def from_environment(
        cls,
        process: Literal["api", "worker"],
    ) -> "DatabaseSettings":
        runtime_url = os.getenv("AIDAM_DATABASE_URL")
        if not runtime_url:
            raise ValueError("AIDAM_DATABASE_URL is required")
        default_pool_size, default_overflow = (5, 5) if process == "api" else (2, 2)
        max_overflow = int(
            os.getenv("AIDAM_DATABASE_MAX_OVERFLOW", str(default_overflow))
        )
        if max_overflow < 0:
            raise ValueError("AIDAM_DATABASE_MAX_OVERFLOW must be non-negative")
        ca_value = os.getenv("AIDAM_DATABASE_CA_FILE")
        return cls(
            runtime_url=runtime_url,
            migration_url=os.getenv("AIDAM_MIGRATION_DATABASE_URL"),
            ca_file=Path(ca_value) if ca_value else None,
            pool_size=_positive_int("AIDAM_DATABASE_POOL_SIZE", default_pool_size),
            max_overflow=max_overflow,
            statement_timeout_ms=_positive_int(
                "AIDAM_DATABASE_STATEMENT_TIMEOUT_MS", 30_000
            ),
            require_tls=_boolean("AIDAM_DATABASE_REQUIRE_TLS", True),
        )

    def engine_settings(
        self,
        process: Literal["api", "worker"],
        *,
        require_tls: bool | None = None,
    ) -> EngineSettings:
        application_name = "aidam-api" if process == "api" else "aidam-worker"
        return EngineSettings(
            database_url=self.runtime_url,
            application_name=application_name,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            ca_file=self.ca_file,
            require_tls=self.require_tls if require_tls is None else require_tls,
            statement_timeout_ms=self.statement_timeout_ms,
        )
