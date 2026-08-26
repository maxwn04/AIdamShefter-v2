"""Turn-scoped coalescing for durable reporter artifact versions."""

from __future__ import annotations

from dataclasses import replace

from backend.services.reporter.runner.recording import (
    ArtifactMutation,
    ArtifactRecorder,
)
from backend.services.reporter.runner.schemas import ArtifactSnapshot


class TurnArtifactRecorder:
    """Buffer mutations and persist one final snapshot per artifact and turn."""

    def __init__(self, recorder: ArtifactRecorder) -> None:
        self._recorder = recorder
        self._pending: dict[str, ArtifactMutation] = {}
        self._durable_revisions: dict[str, int] = {}
        self._durable_content: dict[str, tuple[str, str]] = {}

    def record_artifact_mutation(
        self,
        mutation: ArtifactMutation,
    ) -> None:
        self._pending[mutation.path] = mutation

    def flush_turn(self) -> None:
        pending = tuple(self._pending.values())
        self._pending.clear()

        for mutation in pending:
            durable_content = self._durable_content.get(mutation.path)
            if durable_content == (mutation.content_hash, mutation.content):
                continue

            revision = self._durable_revisions.get(mutation.path, 0) + 1
            self._recorder.record_artifact_mutation(
                replace(mutation, revision=revision)
            )
            self._durable_revisions[mutation.path] = revision
            self._durable_content[mutation.path] = (
                mutation.content_hash,
                mutation.content,
            )

    def durable_snapshots(
        self,
        snapshots: tuple[ArtifactSnapshot, ...],
    ) -> tuple[ArtifactSnapshot, ...]:
        if self._pending:
            raise RuntimeError("artifact mutations must be flushed before output")
        return tuple(
            snapshot.model_copy(
                update={"revision": self._durable_revisions[snapshot.path]}
            )
            for snapshot in snapshots
        )


__all__ = ["TurnArtifactRecorder"]
