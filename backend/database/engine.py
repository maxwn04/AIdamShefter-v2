"""Synchronous SQLAlchemy engine construction for persistent processes."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

ProcessKind = Literal["api", "worker"]

_PRIVILEGED_RUNTIME_USERS = {
    "postgres",
    "aidam_owner",
    "aidam_migrator",
    "service_role",
}


@dataclass(frozen=True, slots=True)
class EngineSettings:
    """Connection and pool limits for one persistent backend process."""

    database_url: str
    application_name: str
    pool_size: int
    max_overflow: int
    ca_file: Path | None = None
    require_tls: bool = True
    pool_timeout_seconds: int = 10
    pool_recycle_seconds: int = 1_800
    connect_timeout_seconds: int = 10
    statement_timeout_ms: int = 30_000
    lock_timeout_ms: int = 5_000
    idle_in_transaction_timeout_ms: int = 30_000

    @classmethod
    def for_process(
        cls,
        database_url: str,
        process: ProcessKind,
        *,
        ca_file: Path | None = None,
        require_tls: bool = True,
    ) -> "EngineSettings":
        if process == "api":
            return cls(
                database_url=database_url,
                application_name="aidam-api",
                pool_size=5,
                max_overflow=5,
                ca_file=ca_file,
                require_tls=require_tls,
            )
        return cls(
            database_url=database_url,
            application_name="aidam-worker",
            pool_size=2,
            max_overflow=2,
            ca_file=ca_file,
            require_tls=require_tls,
        )

    def validate(self) -> None:
        url = make_url(self.database_url)
        if url.drivername != "postgresql+psycopg":
            raise ValueError("database URL must use the postgresql+psycopg driver")
        if url.username in _PRIVILEGED_RUNTIME_USERS:
            raise ValueError(f"runtime database user {url.username!r} is privileged")
        if not self.application_name.strip():
            raise ValueError("application_name must not be empty")
        for field_name in (
            "pool_size",
            "pool_timeout_seconds",
            "pool_recycle_seconds",
            "connect_timeout_seconds",
            "statement_timeout_ms",
            "lock_timeout_ms",
            "idle_in_transaction_timeout_ms",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")
        if self.max_overflow < 0:
            raise ValueError("max_overflow must be non-negative")
        if self.require_tls:
            if self.ca_file is None:
                raise ValueError("ca_file is required when TLS verification is enabled")
            if not self.ca_file.is_file():
                raise ValueError(f"database CA file does not exist: {self.ca_file}")


def build_runtime_engine(settings: EngineSettings) -> Engine:
    """Build a bounded engine for a trusted API or worker process."""

    settings.validate()
    connect_args: dict[str, str | int] = {
        "application_name": settings.application_name,
        "connect_timeout": settings.connect_timeout_seconds,
        "options": " ".join(
            (
                f"-c statement_timeout={settings.statement_timeout_ms}",
                f"-c lock_timeout={settings.lock_timeout_ms}",
                f"-c idle_in_transaction_session_timeout={settings.idle_in_transaction_timeout_ms}",
                "-c search_path=pg_catalog",
            )
        ),
    }
    if settings.require_tls:
        connect_args.update(
            sslmode="verify-full",
            sslrootcert=str(settings.ca_file),
        )
    else:
        connect_args["sslmode"] = "disable"

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
        pool_recycle=settings.pool_recycle_seconds,
        isolation_level="READ COMMITTED",
        connect_args=connect_args,
    )
