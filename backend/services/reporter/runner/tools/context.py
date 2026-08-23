"""Context object injected into runner v2 tools."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID

from backend.services.reporter.runner.recording import (
    ArtifactMutation,
    ArtifactRecorder,
    ArtifactRecordingError,
)
from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.schemas import ArtifactSnapshot
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState


@dataclass
class ToolContext:
    artifacts: ArtifactStore
    procedures: ProcedureState
    log: RunLog
    turn: int = 0
    artifact_recorder: ArtifactRecorder | None = None

    def __post_init__(self) -> None:
        self._source_tool_call_id: ContextVar[UUID | None] = ContextVar(
            f"reporter_source_tool_call_id_{id(self)}",
            default=None,
        )

    @contextmanager
    def bind_tool_execution(
        self,
        tool_call_id: UUID | None,
    ) -> Iterator[None]:
        token: Token[UUID | None] = self._source_tool_call_id.set(tool_call_id)
        try:
            yield
        finally:
            self._source_tool_call_id.reset(token)

    def record_artifact_mutation(self, snapshot: ArtifactSnapshot) -> None:
        if self.artifact_recorder is None:
            return
        try:
            self.artifact_recorder.record_artifact_mutation(
                ArtifactMutation(
                    path=snapshot.path,
                    media_type=snapshot.media_type,
                    content=snapshot.content,
                    revision=snapshot.revision,
                    content_hash=snapshot.content_hash,
                    source_tool_call_id=self._source_tool_call_id.get(),
                )
            )
        except Exception as exc:
            raise ArtifactRecordingError(
                f"Could not record artifact mutation for {snapshot.path}"
            ) from exc
