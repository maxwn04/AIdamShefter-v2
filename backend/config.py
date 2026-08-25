"""Environment-backed product configuration."""

from dataclasses import dataclass
import math
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


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    value = default if raw_value is None else float(raw_value)
    if not math.isfinite(value) or value <= 0:
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
        runtime_name = (
            "AIDAM_DATABASE_URL"
            if process == "api"
            else "AIDAM_WORKER_DATABASE_URL"
        )
        runtime_url = os.getenv(runtime_name)
        if not runtime_url:
            raise ValueError(f"{runtime_name} is required")
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


@dataclass(frozen=True, slots=True)
class GenerationRuntimeSettings:
    """Code revisions sealed into generation input manifests."""

    reporter_revision: str
    generation_revision: str

    @classmethod
    def from_environment(cls) -> "GenerationRuntimeSettings":
        code_revision = os.getenv("AIDAM_CODE_VERSION", "dev").strip()
        reporter_revision = os.getenv(
            "AIDAM_REPORTER_REVISION", code_revision
        ).strip()
        generation_revision = os.getenv(
            "AIDAM_GENERATION_REVISION", code_revision
        ).strip()
        if not reporter_revision:
            raise ValueError("AIDAM_REPORTER_REVISION must not be empty")
        if not generation_revision:
            raise ValueError("AIDAM_GENERATION_REVISION must not be empty")
        return cls(
            reporter_revision=reporter_revision,
            generation_revision=generation_revision,
        )


@dataclass(frozen=True, slots=True)
class ModelCatalogSettings:
    """Configured model choices exposed by the product API."""

    primary_model: str
    fallback_models: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> "ModelCatalogSettings":
        primary = os.getenv("REPORTER_MODEL", "gpt-5-mini").strip()
        if not primary:
            raise ValueError("REPORTER_MODEL must not be empty")
        raw_fallbacks = os.getenv("REPORTER_FALLBACK_MODELS", "")
        ordered: list[str] = []
        seen = {primary}
        for raw_model in raw_fallbacks.split(","):
            model = raw_model.strip()
            if model and model not in seen:
                seen.add(model)
                ordered.append(model)
        return cls(primary_model=primary, fallback_models=tuple(ordered))

    def model_chain(self) -> tuple[str, ...]:
        return (self.primary_model, *self.fallback_models)


@dataclass(frozen=True, slots=True)
class DatalayerSettings:
    """Local storage and Sleeper source settings for datalayer composition."""

    data_root: Path
    sleeper_base_url: str
    sleeper_timeout_seconds: int
    sleeper_max_attempts: int
    sleeper_retry_backoff_seconds: float
    inline_payload_max_bytes: int
    code_version: str

    @classmethod
    def from_environment(cls) -> "DatalayerSettings":
        data_root = os.getenv("AIDAM_DATALAYER_ROOT", ".data/datalayer").strip()
        if not data_root:
            raise ValueError("AIDAM_DATALAYER_ROOT must not be empty")
        base_url = os.getenv(
            "AIDAM_SLEEPER_BASE_URL", "https://api.sleeper.app/v1"
        ).strip().rstrip("/")
        if not base_url:
            raise ValueError("AIDAM_SLEEPER_BASE_URL must not be empty")
        code_version = os.getenv("AIDAM_CODE_VERSION", "dev").strip()
        if not code_version:
            raise ValueError("AIDAM_CODE_VERSION must not be empty")
        return cls(
            data_root=Path(data_root).expanduser(),
            sleeper_base_url=base_url,
            sleeper_timeout_seconds=_positive_int(
                "AIDAM_SLEEPER_TIMEOUT_SECONDS", 10
            ),
            sleeper_max_attempts=_positive_int("AIDAM_SLEEPER_MAX_ATTEMPTS", 3),
            sleeper_retry_backoff_seconds=_positive_float(
                "AIDAM_SLEEPER_RETRY_BACKOFF_SECONDS", 1.0
            ),
            inline_payload_max_bytes=_positive_int(
                "AIDAM_DATALAYER_INLINE_PAYLOAD_MAX_BYTES", 1024 * 1024
            ),
            code_version=code_version,
        )
