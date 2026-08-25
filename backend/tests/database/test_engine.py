from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine

from backend.database import engine as engine_module
from backend.database.engine import EngineSettings, build_runtime_engine


def test_runtime_engine_rejects_privileged_role() -> None:
    settings = EngineSettings(
        database_url="postgresql+psycopg://postgres:secret@localhost/aidam",
        application_name="aidam-api",
        pool_size=5,
        max_overflow=5,
        require_tls=False,
    )

    with pytest.raises(ValueError, match="privileged"):
        _ = build_runtime_engine(settings)


def test_runtime_engine_rejects_privileged_supavisor_login() -> None:
    settings = EngineSettings(
        database_url=(
            "postgresql+psycopg://postgres.project-ref:secret@localhost/aidam"
        ),
        application_name="aidam-api",
        pool_size=5,
        max_overflow=5,
        require_tls=False,
    )

    with pytest.raises(ValueError, match="privileged"):
        _ = build_runtime_engine(settings)


def test_runtime_engine_requires_psycopg3() -> None:
    settings = EngineSettings(
        database_url="postgresql://aidam_api:secret@localhost/aidam",
        application_name="aidam-api",
        pool_size=5,
        max_overflow=5,
        require_tls=False,
    )

    with pytest.raises(ValueError, match=r"postgresql\+psycopg"):
        _ = build_runtime_engine(settings)


def test_verified_tls_requires_existing_ca_file(tmp_path: Path) -> None:
    settings = EngineSettings(
        database_url="postgresql+psycopg://aidam_api:secret@localhost/aidam",
        application_name="aidam-api",
        pool_size=5,
        max_overflow=5,
        ca_file=tmp_path / "missing.pem",
    )

    with pytest.raises(ValueError, match="does not exist"):
        _ = build_runtime_engine(settings)


def test_runtime_engine_applies_pool_timeouts_and_restricted_search_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected_engine = cast(Engine, object())

    def fake_create_engine(url: str, **kwargs: object) -> Engine:
        captured["url"] = url
        captured.update(kwargs)
        return expected_engine

    monkeypatch.setattr(engine_module, "create_engine", fake_create_engine)
    settings = EngineSettings.for_process(
        "postgresql+psycopg://aidam_api:secret@localhost/aidam",
        "api",
        require_tls=False,
    )

    result = build_runtime_engine(settings)

    assert result is expected_engine
    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == 5
    assert captured["max_overflow"] == 5
    connect_args = cast(dict[str, str | int], captured["connect_args"])
    assert connect_args["application_name"] == "aidam-api"
    assert connect_args["sslmode"] == "disable"
    options = cast(str, connect_args["options"])
    assert "search_path=pg_catalog" in options
