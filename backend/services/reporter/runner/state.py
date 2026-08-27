"""Runner state containers."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from backend.services.reporter.runner.research_brief import RESEARCH_BRIEF_PATH
from backend.services.reporter.runner.schemas import (
    ArtifactSnapshot,
    WorkingArtifact,
    validate_artifact_path,
)


class ArtifactStoreError(Exception):
    """Typed artifact operation failure suitable for a model-facing result."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.details}


class ProcedureHistoryMode(str, Enum):
    REPLACE = "replace"
    APPEND = "append"


class ArtifactStore(BaseModel):
    """In-memory Markdown workspace keyed by safe artifact path."""

    artifacts: dict[str, WorkingArtifact] = Field(default_factory=dict)
    managed_paths: frozenset[str] = Field(
        default_factory=lambda: frozenset({RESEARCH_BRIEF_PATH})
    )
    submitted_path: str | None = None

    @model_validator(mode="after")
    def _validate_workspace(self) -> ArtifactStore:
        folded_paths: set[str] = set()
        folded_managed_paths: set[str] = set()
        for path in self.managed_paths:
            validate_artifact_path(path)
            folded = path.casefold()
            if folded in folded_managed_paths:
                raise ValueError("managed artifact paths must be unique ignoring case")
            folded_managed_paths.add(folded)
        for key, artifact in self.artifacts.items():
            validate_artifact_path(key)
            if key != artifact.path:
                raise ValueError("artifact mapping key must match artifact.path")
            folded = key.casefold()
            if folded in folded_paths:
                raise ValueError("artifact paths must be unique ignoring case")
            folded_paths.add(folded)

        if self.submitted_path is not None:
            validate_artifact_path(self.submitted_path)
            submitted = self.artifacts.get(self.submitted_path)
            if submitted is None or submitted.final is None:
                raise ValueError("submitted_path must identify a final artifact")
        return self

    def list(self) -> tuple[ArtifactSnapshot, ...]:
        return tuple(
            self.artifacts[path].current for path in sorted(self.artifacts)
        )

    def read(self, path: str) -> ArtifactSnapshot:
        normalized = self._normalize_path(path)
        return self._get(normalized).current

    def create(
        self,
        path: str,
        content: str,
        *,
        on_change: Callable[[ArtifactSnapshot], None] | None = None,
    ) -> ArtifactSnapshot:
        normalized = self._normalize_path(path)
        self._require_generic_path(normalized)
        collision = self._casefold_collision(normalized)
        if collision is not None:
            raise ArtifactStoreError(
                "artifact_exists",
                f"Artifact already exists: {collision}",
                path=normalized,
                existing_path=collision,
            )

        artifact = WorkingArtifact.create(path=normalized, content=content)
        self.artifacts[normalized] = artifact
        try:
            if on_change is not None:
                on_change(artifact.current)
        except Exception:
            del self.artifacts[normalized]
            raise
        return artifact.current

    def edit(
        self,
        path: str,
        *,
        old_text: str,
        new_text: str,
        expected_revision: int,
        on_change: Callable[[ArtifactSnapshot], None] | None = None,
    ) -> tuple[ArtifactSnapshot, bool]:
        normalized = self._normalize_path(path)
        self._require_generic_path(normalized)
        artifact = self._get(normalized)
        self._check_revision(artifact, expected_revision)
        if artifact.finalized_revision is not None:
            raise ArtifactStoreError(
                "artifact_finalized",
                f"Final artifact cannot be edited: {normalized}",
                path=normalized,
                current_revision=artifact.current.revision,
            )
        if not old_text:
            raise ArtifactStoreError(
                "invalid_edit",
                "old_text must be non-empty",
                path=normalized,
            )

        match_count = artifact.current.content.count(old_text)
        if match_count == 0:
            raise ArtifactStoreError(
                "match_not_found",
                "old_text was not found in the artifact",
                path=normalized,
                current_revision=artifact.current.revision,
            )
        if match_count > 1:
            raise ArtifactStoreError(
                "match_not_unique",
                "old_text must match exactly one location",
                path=normalized,
                match_count=match_count,
                current_revision=artifact.current.revision,
            )

        updated = artifact.current.content.replace(old_text, new_text, 1)
        if updated == artifact.current.content:
            return artifact.current, False

        previous_snapshots = artifact.snapshots
        snapshot = artifact.append(updated)
        try:
            if on_change is not None:
                on_change(snapshot)
        except Exception:
            artifact.snapshots = previous_snapshots
            raise
        return snapshot, True

    def submit(self, path: str, *, expected_revision: int) -> ArtifactSnapshot:
        normalized = self._normalize_path(path)
        self._require_generic_path(normalized)
        artifact = self._get(normalized)
        self._check_revision(artifact, expected_revision)
        if artifact.finalized_revision is not None:
            raise ArtifactStoreError(
                "artifact_finalized",
                f"Artifact is already final: {normalized}",
                path=normalized,
                finalized_revision=artifact.finalized_revision,
            )
        if not artifact.current.content.strip():
            raise ArtifactStoreError(
                "empty_submission",
                "submitted artifact must contain non-whitespace Markdown",
                path=normalized,
                current_revision=artifact.current.revision,
            )
        if self.submitted_path is not None and self.submitted_path != normalized:
            raise ArtifactStoreError(
                "submission_exists",
                f"A final artifact is already pinned: {self.submitted_path}",
                submitted_path=self.submitted_path,
            )

        # Submission pins the existing current revision. It does not synthesize
        # another revision merely to change lifecycle state.
        artifact.finalized_revision = artifact.current.revision
        self.submitted_path = normalized
        return artifact.final

    def sync_managed(
        self,
        path: str,
        content: str,
        *,
        on_change: Callable[[ArtifactSnapshot], None] | None = None,
    ) -> tuple[ArtifactSnapshot, bool]:
        """Create or replace a runtime-owned artifact as one atomic mutation."""
        normalized = self._normalize_path(path)
        managed_path = self._managed_collision(normalized)
        if managed_path is None:
            raise ArtifactStoreError(
                "artifact_not_managed",
                f"Artifact is not runtime-managed: {normalized}",
                path=normalized,
            )
        if managed_path != normalized:
            raise ArtifactStoreError(
                "invalid_path",
                f"Managed artifact path casing must match: {managed_path}",
                path=normalized,
                managed_path=managed_path,
            )

        artifact = self.artifacts.get(normalized)
        if artifact is None:
            created = WorkingArtifact.create(path=normalized, content=content)
            self.artifacts[normalized] = created
            try:
                if on_change is not None:
                    on_change(created.current)
            except Exception:
                del self.artifacts[normalized]
                raise
            return created.current, True

        if artifact.finalized_revision is not None:
            raise ArtifactStoreError(
                "artifact_finalized",
                f"Managed artifact cannot change after finalization: {normalized}",
                path=normalized,
                current_revision=artifact.current.revision,
            )
        if artifact.current.content == content:
            return artifact.current, False

        previous_snapshots = artifact.snapshots
        snapshot = artifact.append(content)
        try:
            if on_change is not None:
                on_change(snapshot)
        except Exception:
            artifact.snapshots = previous_snapshots
            raise
        return snapshot, True

    @property
    def submitted_artifact(self) -> ArtifactSnapshot | None:
        if self.submitted_path is None:
            return None
        return self.artifacts[self.submitted_path].final

    @staticmethod
    def _normalize_path(path: str) -> str:
        try:
            return validate_artifact_path(path)
        except (TypeError, ValueError) as exc:
            raise ArtifactStoreError("invalid_path", str(exc), path=path) from exc

    def _get(self, path: str) -> WorkingArtifact:
        artifact = self.artifacts.get(path)
        if artifact is None:
            raise ArtifactStoreError(
                "artifact_not_found",
                f"Artifact not found: {path}",
                path=path,
            )
        return artifact

    def _casefold_collision(self, path: str) -> str | None:
        folded = path.casefold()
        return next(
            (existing for existing in self.artifacts if existing.casefold() == folded),
            None,
        )

    def _managed_collision(self, path: str) -> str | None:
        folded = path.casefold()
        return next(
            (managed for managed in self.managed_paths if managed.casefold() == folded),
            None,
        )

    def _require_generic_path(self, path: str) -> None:
        managed = self._managed_collision(path)
        if managed is not None:
            raise ArtifactStoreError(
                "managed_artifact",
                f"Artifact is runtime-managed and cannot be changed directly: {managed}",
                path=path,
                managed_path=managed,
            )

    @staticmethod
    def _check_revision(
        artifact: WorkingArtifact,
        expected_revision: int,
    ) -> None:
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise ArtifactStoreError(
                "invalid_revision",
                "expected_revision must be a positive integer",
                path=artifact.path,
            )
        if expected_revision != artifact.current.revision:
            raise ArtifactStoreError(
                "revision_conflict",
                "Artifact revision does not match expected_revision",
                path=artifact.path,
                expected_revision=expected_revision,
                current_revision=artifact.current.revision,
            )


class ProcedureState(BaseModel):
    active: str | None = None


class RunnerConfig(BaseModel):
    max_turns: int = 60
    procedure_history_mode: ProcedureHistoryMode = ProcedureHistoryMode.APPEND


__all__ = [
    "ArtifactStore",
    "ArtifactStoreError",
    "ProcedureHistoryMode",
    "ProcedureState",
    "RunnerConfig",
]
