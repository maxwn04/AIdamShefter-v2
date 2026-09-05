"""Context object injected into runner v2 tools."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from backend.services.reporter.runner.evidence import EvidenceCatalog

from backend.services.reporter.runner.recording import (
    ArtifactMutation,
    ArtifactRecorder,
    ArtifactRecordingError,
)
from backend.services.reporter.runner.research_brief import (
    RESEARCH_BRIEF_PATH,
    BriefMutation,
    ResearchBrief,
    ResearchBriefStore,
)
from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.schemas import ArtifactSnapshot
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState

if TYPE_CHECKING:
    from backend.services.reporter.runner.memory_closeout import MemoryCloseoutState


@dataclass
class ToolContext:
    artifacts: ArtifactStore
    procedures: ProcedureState
    log: RunLog
    brief: ResearchBriefStore = field(default_factory=ResearchBriefStore)
    turn: int = 0
    artifact_recorder: ArtifactRecorder | None = None
    memory_closeout: MemoryCloseoutState | None = None
    evidence: EvidenceCatalog = field(default_factory=EvidenceCatalog)

    def __post_init__(self) -> None:
        self._evidence_invocation: ContextVar[str | None] = ContextVar(
            f"reporter_evidence_invocation_{id(self)}", default=None
        )
        self._direct_evidence_sequence = 0
        self._source_tool_call_id: ContextVar[UUID | None] = ContextVar(
            f"reporter_source_tool_call_id_{id(self)}",
            default=None,
        )

    @contextmanager
    def bind_tool_execution(
        self,
        tool_call_id: UUID | None,
        *,
        invocation: str | None = None,
    ) -> Iterator[None]:
        token: Token[UUID | None] = self._source_tool_call_id.set(tool_call_id)
        invocation_token = self._evidence_invocation.set(invocation)
        try:
            yield
        finally:
            self._source_tool_call_id.reset(token)
            self._evidence_invocation.reset(invocation_token)

    def evidence_source(self) -> str:
        """Allocate before invoking data; never derive IDs from completion order."""
        source = self._evidence_invocation.get()
        if source is not None:
            return source
        self._direct_evidence_sequence += 1
        return f"direct{self._direct_evidence_sequence}"

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

    def commit_brief_mutation(self, mutation: BriefMutation) -> ResearchBrief:
        """Commit structured state and its managed projection atomically."""

        def persist(content: str) -> None:
            self.artifacts.sync_managed(
                RESEARCH_BRIEF_PATH,
                content,
                on_change=self.record_artifact_mutation,
            )

        brief = self.brief.commit(mutation, persist)
        if mutation.changed:
            self.log.add_artifact_write(
                RESEARCH_BRIEF_PATH,
                mutation.operation,
                mutation.entity_id,
                brief.revision,
                turn=self.turn,
            )
        return brief

    @property
    def current_tool_call_id(self) -> UUID | None:
        """Return durable provenance for the tool handler currently executing."""

        return self._source_tool_call_id.get()
