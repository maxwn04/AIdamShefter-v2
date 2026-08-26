"""Tests for generic reporter artifact schemas and state."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from backend.services.reporter.runner.schemas import (
    ArtifactSnapshot,
    ReporterOutput,
    WorkingArtifact,
)
from backend.services.reporter.runner.state import (
    ArtifactStore,
    ArtifactStoreError,
    ProcedureHistoryMode,
    ProcedureState,
    RunnerConfig,
)


def test_working_artifact_keeps_immutable_snapshot_history() -> None:
    artifact = WorkingArtifact.create(path="research_brief.md", content="# Brief")
    first = artifact.current

    second = artifact.append("# Brief\n\nMore evidence.")

    assert artifact.media_type == "text/markdown"
    assert artifact.snapshots == (first, second)
    assert first.revision == 1
    assert first.content == "# Brief"
    assert second.revision == 2
    assert second.media_type == "text/markdown"
    assert second.content_hash == hashlib.sha256(
        second.content.encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValidationError):
        first.content = "changed"


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/article.md",
        "../article.md",
        "research/../article.md",
        "./article.md",
        "research\\brief.md",
        "research//brief.md",
        "C:/article.md",
        "article.txt",
        "article.MD",
        " article.md",
    ],
)
def test_artifact_paths_are_safe_portable_markdown_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        WorkingArtifact.create(path=path, content="content")


def test_working_artifact_rejects_invalid_history() -> None:
    with pytest.raises(ValidationError, match="content_hash"):
        WorkingArtifact(
            path="article.md",
            snapshots=(
                ArtifactSnapshot(
                    path="article.md",
                    content="content",
                    revision=1,
                    content_hash="0" * 64,
                ),
            ),
        )


def test_artifact_store_create_read_list_and_casefold_collision() -> None:
    store = ArtifactStore()

    article = store.create("article.md", "# Article")
    brief, _ = store.sync_managed("research_brief.md", "# Brief")

    assert store.read("article.md") is article
    assert store.list() == (article, brief)
    with pytest.raises(ArtifactStoreError) as exc_info:
        store.create("ARTICLE.md", "duplicate")
    assert exc_info.value.code == "artifact_exists"


def test_edit_appends_revision_and_preserves_prior_snapshot() -> None:
    store = ArtifactStore()
    first = store.create("article.md", "Alpha beta")

    second, changed = store.edit(
        "article.md",
        old_text="beta",
        new_text="gamma",
        expected_revision=1,
    )

    working = store.artifacts["article.md"]
    assert changed is True
    assert working.snapshots == (first, second)
    assert first.content == "Alpha beta"
    assert second.content == "Alpha gamma"
    assert second.revision == 2


@pytest.mark.parametrize(
    ("old_text", "expected_revision", "code"),
    [
        ("missing", 1, "match_not_found"),
        ("same", 1, "match_not_unique"),
        ("same", 2, "revision_conflict"),
        ("", 1, "invalid_edit"),
    ],
)
def test_edit_reports_typed_conflicts(
    old_text: str,
    expected_revision: int,
    code: str,
) -> None:
    store = ArtifactStore()
    store.create("article.md", "same and same")

    with pytest.raises(ArtifactStoreError) as exc_info:
        store.edit(
            "article.md",
            old_text=old_text,
            new_text="new",
            expected_revision=expected_revision,
        )
    assert exc_info.value.code == code


def test_submit_pins_existing_current_snapshot_without_new_revision() -> None:
    store = ArtifactStore()
    current = store.create("drafts/week-8.md", "# Final article")

    submitted = store.submit("drafts/week-8.md", expected_revision=1)

    working = store.artifacts["drafts/week-8.md"]
    assert submitted is current
    assert working.final is current
    assert working.finalized_revision == 1
    assert len(working.snapshots) == 1
    assert store.submitted_path == "drafts/week-8.md"
    with pytest.raises(ArtifactStoreError) as exc_info:
        store.edit(
            "drafts/week-8.md",
            old_text="Final",
            new_text="Changed",
            expected_revision=1,
        )
    assert exc_info.value.code == "artifact_finalized"


def test_reporter_output_exposes_submitted_content_and_all_artifacts() -> None:
    store = ArtifactStore()
    store.sync_managed("research_brief.md", "# Brief")
    store.create("article.md", "# Article")
    store.submit("article.md", expected_revision=1)

    output = ReporterOutput(
        submitted_path=store.submitted_path,
        artifacts=store.list(),
    )

    assert output.article == "# Article"
    assert output.submitted_artifact == store.submitted_artifact
    assert [artifact.path for artifact in output.artifacts] == [
        "article.md",
        "research_brief.md",
    ]


def test_state_defaults() -> None:
    assert ArtifactStore().artifacts == {}
    assert ProcedureState().active is None
    assert RunnerConfig().max_turns == 60
    assert RunnerConfig().procedure_history_mode == ProcedureHistoryMode.REPLACE
