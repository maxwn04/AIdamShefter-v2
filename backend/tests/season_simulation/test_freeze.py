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


@pytest.mark.parametrize(("name", "initial", "changed"), [
    ("AIDAM_MEMORY_SEMANTIC_ENABLED", "true", "false"),
    ("AIDAM_MEMORY_EMBEDDING_MODEL", "text-embedding-3-large", "text-embedding-3-small"),
    ("AIDAM_MEMORY_EMBEDDING_DIMENSIONS", "3072", "1536"),
    ("AIDAM_MEMORY_EMBEDDING_TIMEOUT_SECONDS", "30", "10"),
])
def test_semantic_configuration_is_frozen(tmp_path, monkeypatch, name, initial, changed):
    monkeypatch.setenv(name, initial)
    freeze = runtime_freeze(tmp_path)
    assert freeze.configuration[name] == initial
    assert_runtime(freeze, tmp_path)

    monkeypatch.setenv(name, changed)
    with pytest.raises(ValueError, match=name):
        assert_runtime(freeze, tmp_path)

    monkeypatch.delenv(name)
    with pytest.raises(ValueError, match=name):
        assert_runtime(freeze, tmp_path)
