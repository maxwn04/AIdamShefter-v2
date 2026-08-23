"""Reporter artifact and output schemas."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validate_artifact_path(value: str) -> str:
    """Return a safe, normalized Markdown artifact path."""
    if not isinstance(value, str) or not value:
        raise ValueError("artifact path must be a non-empty string")
    if value != value.strip():
        raise ValueError("artifact path cannot have surrounding whitespace")
    if "\x00" in value or "\\" in value:
        raise ValueError("artifact path must use POSIX separators")

    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise ValueError("artifact path must be a normalized relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("artifact path cannot contain dot segments")
    if not path.parts or ":" in path.parts[0]:
        raise ValueError("artifact path must be relative to the artifact workspace")
    if path.suffix != ".md":
        raise ValueError("artifact path must end in .md")
    return value


def hash_artifact_content(content: str) -> str:
    """Hash the exact UTF-8 bytes of artifact content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ArtifactSnapshot(BaseModel):
    """Immutable view of one current artifact revision."""

    model_config = ConfigDict(frozen=True)

    path: str
    media_type: Literal["text/markdown"] = "text/markdown"
    content: str
    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return validate_artifact_path(value)

    @model_validator(mode="after")
    def _validate_content_hash(self) -> ArtifactSnapshot:
        if self.content_hash != hash_artifact_content(self.content):
            raise ValueError("artifact snapshot content_hash is invalid")
        return self


class WorkingArtifact(BaseModel):
    """Artifact identity, append-only snapshot history, and final pin."""

    model_config = ConfigDict(validate_assignment=True)

    path: str
    media_type: Literal["text/markdown"] = "text/markdown"
    snapshots: tuple[ArtifactSnapshot, ...]
    finalized_revision: int | None = Field(default=None, ge=1)

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return validate_artifact_path(value)

    @model_validator(mode="after")
    def _validate_history(self) -> WorkingArtifact:
        if not self.snapshots:
            raise ValueError("working artifact requires at least one snapshot")
        for expected_revision, snapshot in enumerate(self.snapshots, start=1):
            if snapshot.path != self.path or snapshot.media_type != self.media_type:
                raise ValueError("artifact snapshots must share path and media_type")
            if snapshot.revision != expected_revision:
                raise ValueError("artifact snapshot revisions must be contiguous")
            if snapshot.content_hash != hash_artifact_content(snapshot.content):
                raise ValueError("artifact snapshot content_hash is invalid")
        if (
            self.finalized_revision is not None
            and self.finalized_revision != self.snapshots[-1].revision
        ):
            raise ValueError("finalized_revision must pin the current snapshot")
        return self

    @classmethod
    def create(cls, *, path: str, content: str) -> WorkingArtifact:
        snapshot = ArtifactSnapshot(
            path=path,
            content=content,
            revision=1,
            content_hash=hash_artifact_content(content),
        )
        return cls(path=path, snapshots=(snapshot,))

    @property
    def current(self) -> ArtifactSnapshot:
        return self.snapshots[-1]

    @property
    def final(self) -> ArtifactSnapshot | None:
        if self.finalized_revision is None:
            return None
        return self.snapshots[self.finalized_revision - 1]

    def append(self, content: str) -> ArtifactSnapshot:
        snapshot = ArtifactSnapshot(
            path=self.path,
            media_type=self.media_type,
            content=content,
            revision=self.current.revision + 1,
            content_hash=hash_artifact_content(content),
        )
        self.snapshots = (*self.snapshots, snapshot)
        return snapshot


class ReporterOutput(BaseModel):
    """Completed reporter run with submitted path and artifact snapshots."""

    submitted_path: str | None = None
    artifacts: tuple[ArtifactSnapshot, ...] = ()
    run_log_summary: dict[str, Any] = Field(default_factory=dict)
    run_log_entries: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    @field_validator("submitted_path")
    @classmethod
    def _validate_submitted_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_artifact_path(value)

    @model_validator(mode="after")
    def _validate_artifacts(self) -> ReporterOutput:
        paths = [artifact.path for artifact in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("ReporterOutput contains duplicate artifact paths")
        if self.submitted_path is not None and self.submitted_path not in paths:
            raise ValueError("submitted_path must identify an output artifact")
        return self

    @property
    def submitted_artifact(self) -> ArtifactSnapshot | None:
        if self.submitted_path is None:
            return None
        return next(
            (
                artifact
                for artifact in self.artifacts
                if artifact.path == self.submitted_path
            ),
            None,
        )

    @property
    def article(self) -> str:
        """Compatibility accessor for callers that still consume article text."""
        submitted = self.submitted_artifact
        return submitted.content if submitted is not None else ""


__all__ = [
    "ArtifactSnapshot",
    "ReporterOutput",
    "WorkingArtifact",
    "hash_artifact_content",
    "validate_artifact_path",
]
