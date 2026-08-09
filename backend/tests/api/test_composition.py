from pathlib import Path
from uuid import UUID

from sqlalchemy.engine import make_url
import pytest

import backend.composition as composition
from backend.composition import build_api_runtime, open_datalayer_refresh_service
from backend.resources.context import ActorKind, ManagerContext
from backend.services.datalayer.refresh_service import DatalayerRefreshService


class StubSourceClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _configure_runtime(
    monkeypatch: pytest.MonkeyPatch,
    data_root: Path,
) -> None:
    monkeypatch.setenv(
        "AIDAM_DATABASE_URL",
        "postgresql+psycopg://aidam_api:secret@localhost/aidam_test",
    )
    monkeypatch.setenv("AIDAM_DATABASE_REQUIRE_TLS", "false")
    monkeypatch.setenv("AIDAM_CODE_VERSION", "test-sha")
    monkeypatch.setenv("AIDAM_DATALAYER_ROOT", str(data_root))


def test_build_api_runtime_uses_url_identity_and_local_tls_setting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_runtime(monkeypatch, tmp_path / "datalayer")

    runtime = build_api_runtime()
    try:
        url = make_url(str(runtime.engine.url))
        assert url.database == "aidam_test"
        assert runtime.expected_database == "aidam_test"
        assert runtime.expected_role == "aidam_api"
        assert runtime.require_tls is False
        assert runtime.session_factory.kw["bind"] is runtime.engine
        assert runtime.datalayer_settings.code_version == "test-sha"
        assert runtime.datalayer_file_store.root == (tmp_path / "datalayer").resolve()
    finally:
        runtime.close()


def test_refresh_service_factory_owns_one_source_client_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_runtime(monkeypatch, tmp_path / "datalayer")
    runtime = build_api_runtime()
    source_client = StubSourceClient()
    source_arguments: dict[str, object] = {}

    def build_source_client(**kwargs: object) -> StubSourceClient:
        source_arguments.update(kwargs)
        return source_client

    try:
        monkeypatch.setattr(composition, "SleeperSourceClient", build_source_client)
        context = ManagerContext.competition(
            actor_kind=ActorKind.API,
            actor_id="local-api",
            competition_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        )
        with open_datalayer_refresh_service(runtime, context) as service:
            assert isinstance(service, DatalayerRefreshService)
            assert source_client.closed is False

        assert source_arguments == {
            "base_url": "https://api.sleeper.app/v1",
            "timeout_seconds": 10,
        }
        assert source_client.closed is True
    finally:
        runtime.close()
