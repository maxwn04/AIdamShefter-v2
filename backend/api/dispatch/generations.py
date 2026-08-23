"""Local FastAPI background dispatch for durable generations."""

import asyncio
from dataclasses import dataclass
import logging
from typing import Protocol
from uuid import UUID

from fastapi import BackgroundTasks

from backend.worker.execution import execute_one_generation


logger = logging.getLogger(__name__)


class GenerationDispatcher(Protocol):
    def dispatch(self, competition_id: UUID, generation_id: UUID) -> None: ...


@dataclass(frozen=True, slots=True)
class BackgroundGenerationDispatcher:
    """Schedule worker-scoped execution after the HTTP response is sent."""

    tasks: BackgroundTasks

    def dispatch(self, competition_id: UUID, generation_id: UUID) -> None:
        self.tasks.add_task(
            _execute_generation_background,
            competition_id,
            generation_id,
        )


def get_generation_dispatcher(
    background_tasks: BackgroundTasks,
) -> GenerationDispatcher:
    return BackgroundGenerationDispatcher(background_tasks)


def _execute_generation_background(
    competition_id: UUID,
    generation_id: UUID,
) -> None:
    """Run worker async code in FastAPI's threadpool with safe diagnostics."""

    try:
        result = asyncio.run(execute_one_generation(competition_id, generation_id))
    except Exception as exc:
        logger.error(
            "background generation execution failed: generation_id=%s error_type=%s",
            generation_id,
            type(exc).__name__,
        )
        return
    logger.info(
        "background generation execution finished: generation_id=%s status=%s",
        generation_id,
        result.generation.status.value,
    )
