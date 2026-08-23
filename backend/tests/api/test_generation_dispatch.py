import logging
from types import SimpleNamespace
from uuid import uuid4

from fastapi import BackgroundTasks
import pytest

import backend.api.dispatch.generations as dispatch_module
from backend.api.dispatch import BackgroundGenerationDispatcher
from backend.resources.reporting.generations import GenerationStatus


@pytest.mark.asyncio
async def test_background_dispatch_runs_shared_worker_execution_after_scheduling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    competition_id = uuid4()
    generation_id = uuid4()
    calls: list[tuple[object, object]] = []

    async def execute(scoped_competition_id: object, scoped_generation_id: object):
        calls.append((scoped_competition_id, scoped_generation_id))
        return SimpleNamespace(
            generation=SimpleNamespace(status=GenerationStatus.SUCCEEDED)
        )

    monkeypatch.setattr(dispatch_module, "execute_one_generation", execute)
    tasks = BackgroundTasks()
    dispatcher = BackgroundGenerationDispatcher(tasks)

    dispatcher.dispatch(competition_id, generation_id)

    assert calls == []
    assert len(tasks.tasks) == 1
    await tasks()
    assert calls == [(competition_id, generation_id)]


@pytest.mark.asyncio
async def test_background_dispatch_logs_only_safe_failure_metadata(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def execute(_competition_id: object, _generation_id: object):
        raise RuntimeError("secret provider response")

    monkeypatch.setattr(dispatch_module, "execute_one_generation", execute)
    tasks = BackgroundTasks()
    generation_id = uuid4()
    BackgroundGenerationDispatcher(tasks).dispatch(uuid4(), generation_id)

    with caplog.at_level(logging.ERROR, logger=dispatch_module.__name__):
        await tasks()

    assert str(generation_id) in caplog.text
    assert "RuntimeError" in caplog.text
    assert "secret provider response" not in caplog.text
