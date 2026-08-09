from sqlalchemy.engine import make_url
import pytest

from backend.composition import build_api_runtime


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
    finally:
        runtime.close()
