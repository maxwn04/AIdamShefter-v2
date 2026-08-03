"""Tests for reporter v2 CLI configuration helpers."""

from __future__ import annotations

import pytest

from reporter_v2.app.runner import (
    _make_sleeper_data,
    _resolve_fallback_models,
    _resolve_max_retries,
    _resolve_procedure_history_mode,
)
from reporter_v2.runner.state import ProcedureHistoryMode


def test_resolve_procedure_history_mode_defaults_to_replace(monkeypatch) -> None:
    monkeypatch.delenv("REPORTER_V2_PROCEDURE_MODE", raising=False)

    assert _resolve_procedure_history_mode(None) == ProcedureHistoryMode.REPLACE


def test_resolve_procedure_history_mode_uses_env(monkeypatch) -> None:
    monkeypatch.setenv("REPORTER_V2_PROCEDURE_MODE", "append")

    assert _resolve_procedure_history_mode(None) == ProcedureHistoryMode.APPEND


def test_resolve_procedure_history_mode_cli_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("REPORTER_V2_PROCEDURE_MODE", "append")

    assert _resolve_procedure_history_mode("replace") == ProcedureHistoryMode.REPLACE


def test_resolve_procedure_history_mode_rejects_invalid_env(monkeypatch) -> None:
    monkeypatch.setenv("REPORTER_V2_PROCEDURE_MODE", "bogus")

    with pytest.raises(ValueError, match="REPORTER_V2_PROCEDURE_MODE must be one of"):
        _resolve_procedure_history_mode(None)


def test_resolve_fallback_models_from_cli(monkeypatch) -> None:
    monkeypatch.delenv("REPORTER_V2_FALLBACK_MODELS", raising=False)
    monkeypatch.delenv("REPORTER_FALLBACK_MODELS", raising=False)

    assert _resolve_fallback_models(
        ["deepseek/deepseek-chat", "claude-sonnet-4-6"],
        "gpt-5-mini",
    ) == ["deepseek/deepseek-chat", "claude-sonnet-4-6"]


def test_resolve_fallback_models_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "REPORTER_FALLBACK_MODELS",
        "deepseek/deepseek-chat, gpt-5-mini, claude-sonnet-4-6",
    )

    assert _resolve_fallback_models(None, "gpt-5-mini") == [
        "deepseek/deepseek-chat",
        "claude-sonnet-4-6",
    ]


def test_resolve_fallback_models_cli_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("REPORTER_FALLBACK_MODELS", "from-env")

    assert _resolve_fallback_models(["from-cli"], "primary") == ["from-cli"]


def test_resolve_max_retries_defaults_and_env(monkeypatch) -> None:
    monkeypatch.delenv("REPORTER_V2_MAX_RETRIES", raising=False)
    assert _resolve_max_retries(None) == 3

    monkeypatch.setenv("REPORTER_V2_MAX_RETRIES", "5")
    assert _resolve_max_retries(None) == 5
    assert _resolve_max_retries(1) == 1


def test_resolve_max_retries_rejects_negative(monkeypatch) -> None:
    monkeypatch.setenv("REPORTER_V2_MAX_RETRIES", "-1")
    with pytest.raises(ValueError, match="REPORTER_V2_MAX_RETRIES"):
        _resolve_max_retries(None)


def test_make_sleeper_data_uses_cli_week_override_without_env_league(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SLEEPER_LEAGUE_ID", raising=False)

    data = _make_sleeper_data("league_cli", 8)

    assert data.league_id == "league_cli"
    assert data.week_override == 8


def test_make_sleeper_data_week_override_uses_env_league(monkeypatch) -> None:
    monkeypatch.setenv("SLEEPER_LEAGUE_ID", "league_env")

    data = _make_sleeper_data(None, 9)

    assert data.league_id == "league_env"
    assert data.week_override == 9


def test_make_sleeper_data_cli_league_overrides_env_for_week_override(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SLEEPER_LEAGUE_ID", "league_env")

    data = _make_sleeper_data("league_cli", 10)

    assert data.league_id == "league_cli"
    assert data.week_override == 10


def test_make_sleeper_data_week_override_requires_league(monkeypatch) -> None:
    monkeypatch.delenv("SLEEPER_LEAGUE_ID", raising=False)

    with pytest.raises(ValueError, match="SLEEPER_LEAGUE_ID must be set"):
        _make_sleeper_data(None, 8)
