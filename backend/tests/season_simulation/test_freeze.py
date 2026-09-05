from pathlib import Path

import pytest

from backend.season_simulation.freeze import archive_runtime, assert_runtime, runtime_freeze


def test_changed_prompt_code_config_or_dependency_fails_closed(tmp_path, monkeypatch):
    backend = tmp_path / "backend"
    backend.mkdir()
    prompt = backend / "prompt.md"
    prompt.write_text("frozen prompt")
    freeze = runtime_freeze(tmp_path)
    archive_runtime(freeze, tmp_path / "archive", tmp_path)
    assert (tmp_path / "archive/backend/prompt.md").read_text() == "frozen prompt"
    assert_runtime(freeze, tmp_path)
    prompt.write_text("changed prompt")
    with pytest.raises(ValueError, match="runtime"): assert_runtime(freeze, tmp_path)
    prompt.write_text("frozen prompt")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://different.invalid")
    with pytest.raises(ValueError, match="runtime"): assert_runtime(freeze, tmp_path)
