import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import backend.api.dependencies.generations as api_dependencies
import backend.worker.dependencies as worker_dependencies
from backend.resources.context import LocalUserActor, SystemProcessActor


ROOT = Path(__file__).parents[3]


def test_api_dependency_uses_local_actor_and_url_competition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition_id = uuid4()
    correlation_id = uuid4()
    sentinel = object()
    captured: list[object] = []

    def build(session_factory: object, context: object) -> object:
        captured.extend((session_factory, context))
        return sentinel

    monkeypatch.setattr(api_dependencies, "build_generation_dependencies", build)
    runtime = SimpleNamespace(session_factory="factory")

    result = api_dependencies.get_generation_api_dependencies(
        competition_id,
        correlation_id,
        runtime,
    )

    assert result is sentinel
    assert captured[0] == "factory"
    context = captured[1]
    assert isinstance(context.actor, LocalUserActor)
    assert context.scope.competition_id == competition_id
    assert context.correlation_id == correlation_id


def test_worker_dependency_uses_system_actor_and_competition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition_id = uuid4()
    correlation_id = uuid4()
    sentinel = object()
    captured: list[object] = []

    def build(session_factory: object, context: object) -> object:
        captured.extend((session_factory, context))
        return sentinel

    monkeypatch.setattr(worker_dependencies, "build_generation_dependencies", build)
    runtime = SimpleNamespace(session_factory="factory")

    result = worker_dependencies.build_worker_generation_dependencies(
        runtime,
        competition_id,
        correlation_id=correlation_id,
    )

    assert result is sentinel
    context = captured[1]
    assert isinstance(context.actor, SystemProcessActor)
    assert context.actor.process_name == "generation-worker"
    assert context.scope.competition_id == competition_id
    assert context.correlation_id == correlation_id


@pytest.mark.parametrize(
    "relative_path",
    [
        "backend/api/dependencies/generations.py",
        "backend/api/routes/generations.py",
        "backend/worker/dependencies.py",
        "backend/worker/main.py",
    ],
)
def test_generation_process_boundaries_do_not_import_database_internals(
    relative_path: str,
) -> None:
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert not {
        name
        for name in imports
        if name == "sqlalchemy"
        or name.startswith("sqlalchemy.")
        or name.startswith("backend.database")
    }
