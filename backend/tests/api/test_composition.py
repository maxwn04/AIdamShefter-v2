from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from backend.composition import (
    build_api_runtime,
    build_datalayer_refresh_dependencies,
    build_memory_api_dependencies,
)
from backend.config import DatalayerSettings
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.services.datalayer.refresh_service import DatalayerRefreshService
from backend.services.memory import MemoryMutationService, MemoryRetrievalService


def test_build_api_runtime_uses_url_identity_and_local_tls_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AIDAM_DATABASE_URL",
        "postgresql+psycopg://aidam_api:secret@localhost/aidam_test",
    )
    monkeypatch.setenv("AIDAM_DATABASE_REQUIRE_TLS", "false")

    runtime = build_api_runtime()
    try:
        url = make_url(str(runtime.engine.url))
        assert url.database == "aidam_test"
        assert runtime.expected_database == "aidam_test"
        assert runtime.expected_role == "aidam_api"
        assert runtime.require_tls is False
        assert runtime.session_factory.kw["bind"] is runtime.engine
    finally:
        runtime.close()


def test_memory_api_composition_is_scoped_without_opening_a_session() -> None:
    competition_id = uuid4()
    engine = create_engine("sqlite://")
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "local_user"},
            "scope": {
                "kind": "competition",
                "competition_id": competition_id,
            },
            "correlation_id": uuid4(),
        }
    )
    try:
        runtime = build_memory_api_dependencies(
            create_session_factory(engine),
            context,
        )

        assert runtime.revisions.competition_id == competition_id
        assert isinstance(runtime.retrieval, MemoryRetrievalService)
        assert isinstance(runtime.mutations, MemoryMutationService)
    finally:
        engine.dispose()


def test_datalayer_refresh_composition_is_scoped_without_opening_a_session(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://")
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "system_process", "process_name": "test"},
            "scope": {"kind": "competition", "competition_id": uuid4()},
            "correlation_id": uuid4(),
        }
    )
    dependencies = build_datalayer_refresh_dependencies(
        create_session_factory(engine),
        context,
        settings=DatalayerSettings(
            data_root=tmp_path,
            sleeper_base_url="https://source.example/v1",
            sleeper_timeout_seconds=5,
            sleeper_max_attempts=3,
            sleeper_retry_backoff_seconds=0.25,
            inline_payload_max_bytes=1024,
            code_version="test",
        ),
    )
    try:
        assert isinstance(dependencies.refresh, DatalayerRefreshService)
    finally:
        dependencies.close()
        engine.dispose()
