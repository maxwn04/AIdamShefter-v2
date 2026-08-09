from pathlib import Path

import pytest

from backend.config import DatalayerSettings


def test_datalayer_settings_have_local_v1_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "AIDAM_DATALAYER_ROOT",
        "AIDAM_DATALAYER_INLINE_PAYLOAD_BYTES",
        "AIDAM_SLEEPER_BASE_URL",
        "AIDAM_SLEEPER_TIMEOUT_SECONDS",
        "AIDAM_SNAPSHOT_WAIT_SECONDS",
        "AIDAM_SNAPSHOT_STALE_SECONDS",
        "AIDAM_CODE_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = DatalayerSettings.from_environment()

    assert settings.data_root == Path(".data/datalayer")
    assert settings.inline_payload_threshold_bytes == 8 * 1024 * 1024
    assert settings.sleeper_timeout_seconds == 10
    assert settings.snapshot_stale_seconds > settings.snapshot_wait_seconds
    assert settings.code_version == "dev"


def test_datalayer_settings_accept_explicit_code_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_CODE_VERSION", "commit-abc123")

    assert DatalayerSettings.from_environment().code_version == "commit-abc123"

    monkeypatch.setenv("AIDAM_CODE_VERSION", "   ")
    with pytest.raises(ValueError, match="must not be empty"):
        DatalayerSettings.from_environment()
