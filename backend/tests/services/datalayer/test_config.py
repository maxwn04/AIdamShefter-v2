from pathlib import Path

import pytest

from backend.config import DatalayerSettings


_ENVIRONMENT_NAMES = (
    "AIDAM_DATALAYER_ROOT",
    "AIDAM_SLEEPER_BASE_URL",
    "AIDAM_SLEEPER_TIMEOUT_SECONDS",
)


def test_datalayer_settings_have_local_source_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in _ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)

    settings = DatalayerSettings.from_environment()

    assert settings.data_root == Path(".data/datalayer")
    assert settings.sleeper_base_url == "https://api.sleeper.app/v1"
    assert settings.sleeper_timeout_seconds == 10


def test_datalayer_settings_read_environment_and_normalize_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_DATALAYER_ROOT", "custom-data")
    monkeypatch.setenv("AIDAM_SLEEPER_BASE_URL", "https://source.example/v1///")
    monkeypatch.setenv("AIDAM_SLEEPER_TIMEOUT_SECONDS", "25")

    settings = DatalayerSettings.from_environment()

    assert settings.data_root == Path("custom-data")
    assert settings.sleeper_base_url == "https://source.example/v1"
    assert settings.sleeper_timeout_seconds == 25


@pytest.mark.parametrize("value", ["0", "-1"])
def test_datalayer_settings_reject_nonpositive_timeout(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("AIDAM_SLEEPER_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError, match="must be positive"):
        DatalayerSettings.from_environment()


def test_datalayer_settings_reject_empty_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_SLEEPER_BASE_URL", "///")

    with pytest.raises(ValueError, match="must not be empty"):
        DatalayerSettings.from_environment()


def test_datalayer_settings_reject_empty_data_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIDAM_DATALAYER_ROOT", "   ")

    with pytest.raises(ValueError, match="must not be empty"):
        DatalayerSettings.from_environment()
