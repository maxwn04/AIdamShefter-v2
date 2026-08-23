"""Tests for generic Markdown artifact tools."""

from __future__ import annotations

import json

from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState
from backend.services.reporter.runner.tools.artifact_tools import (
    ARTIFACT_TOOL_SPECS,
    create_artifact,
    edit_artifact,
    list_artifacts,
    read_artifact,
    submit_artifact,
)
from backend.services.reporter.runner.tools.context import ToolContext


def make_ctx() -> ToolContext:
    return ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(session_id="testlog"),
        turn=3,
    )


def decode(result: str) -> dict:
    return json.loads(result)


def test_tool_surface_is_generic() -> None:
    assert [spec["function"]["name"] for spec in ARTIFACT_TOOL_SPECS] == [
        "list_artifacts",
        "read_artifact",
        "create_artifact",
        "edit_artifact",
        "submit_artifact",
    ]
    submit_spec = next(
        spec
        for spec in ARTIFACT_TOOL_SPECS
        if spec["function"]["name"] == "submit_artifact"
    )
    assert "enum" not in submit_spec["function"]["parameters"]["properties"]["path"]


def test_create_list_and_read_artifacts() -> None:
    ctx = make_ctx()

    created = decode(
        create_artifact(ctx, path="research/brief.md", content="# Brief")
    )
    listed = decode(list_artifacts(ctx))
    read = decode(read_artifact(ctx, path="research/brief.md"))

    assert created["ok"] is True
    assert created["artifact"]["revision"] == 1
    assert created["artifact"]["media_type"] == "text/markdown"
    assert len(created["artifact"]["content_hash"]) == 64
    assert listed == {
        "ok": True,
        "artifact_count": 1,
        "artifacts": [
            {
                "path": "research/brief.md",
                "media_type": "text/markdown",
                "revision": 1,
                "content_hash": created["artifact"]["content_hash"],
                "revision_count": 1,
                "finalized_revision": None,
            }
        ],
    }
    assert read["artifact"] == created["artifact"]
    assert read["revision_count"] == 1
    assert read["finalized_revision"] is None


def test_invalid_path_and_duplicate_return_structured_errors() -> None:
    ctx = make_ctx()

    invalid = decode(create_artifact(ctx, path="../brief.md", content="x"))
    create_artifact(ctx, path="article.md", content="x")
    duplicate = decode(create_artifact(ctx, path="ARTICLE.md", content="y"))

    assert invalid["error"]["code"] == "invalid_path"
    assert duplicate["error"] == {
        "code": "artifact_exists",
        "message": "Artifact already exists: article.md",
        "path": "ARTICLE.md",
        "existing_path": "article.md",
    }


def test_edit_is_exact_single_replace_with_expected_revision() -> None:
    ctx = make_ctx()
    create_artifact(ctx, path="article.md", content="# Title\n\nOld sentence.")

    edited = decode(
        edit_artifact(
            ctx,
            path="article.md",
            old_text="Old sentence.",
            new_text="New sentence.",
            expected_revision=1,
        )
    )

    assert edited["ok"] is True
    assert edited["changed"] is True
    assert edited["replacement_count"] == 1
    assert edited["artifact"]["revision"] == 2
    assert edited["artifact"]["content"] == "# Title\n\nNew sentence."
    working = ctx.artifacts.artifacts["article.md"]
    assert [snapshot.content for snapshot in working.snapshots] == [
        "# Title\n\nOld sentence.",
        "# Title\n\nNew sentence.",
    ]


def test_edit_can_replace_the_full_document() -> None:
    ctx = make_ctx()
    original = "# Draft\n\nReplace the whole document."
    replacement = "# Rewritten\n\nA clean second draft."
    create_artifact(ctx, path="article.md", content=original)

    result = decode(
        edit_artifact(
            ctx,
            path="article.md",
            old_text=original,
            new_text=replacement,
            expected_revision=1,
        )
    )

    assert result["ok"] is True
    assert result["artifact"]["content"] == replacement
    assert result["artifact"]["revision"] == 2


def test_missing_artifact_returns_structured_error() -> None:
    ctx = make_ctx()

    result = decode(read_artifact(ctx, path="missing.md"))

    assert result["ok"] is False
    assert result["error"]["code"] == "artifact_not_found"
    assert result["error"]["path"] == "missing.md"


def test_edit_conflicts_are_structured_and_do_not_mutate() -> None:
    ctx = make_ctx()
    create_artifact(ctx, path="article.md", content="Repeat. Repeat.")

    stale = decode(
        edit_artifact(
            ctx,
            path="article.md",
            old_text="Repeat.",
            new_text="Changed.",
            expected_revision=2,
        )
    )
    ambiguous = decode(
        edit_artifact(
            ctx,
            path="article.md",
            old_text="Repeat.",
            new_text="Changed.",
            expected_revision=1,
        )
    )

    assert stale["error"]["code"] == "revision_conflict"
    assert stale["error"]["current_revision"] == 1
    assert ambiguous["error"]["code"] == "match_not_unique"
    assert ambiguous["error"]["match_count"] == 2
    assert len(ctx.artifacts.artifacts["article.md"].snapshots) == 1


def test_same_text_edit_is_noop_without_new_snapshot() -> None:
    ctx = make_ctx()
    create_artifact(ctx, path="article.md", content="Stable")

    result = decode(
        edit_artifact(
            ctx,
            path="article.md",
            old_text="Stable",
            new_text="Stable",
            expected_revision=1,
        )
    )

    assert result["changed"] is False
    assert result["artifact"]["revision"] == 1
    assert len(ctx.artifacts.artifacts["article.md"].snapshots) == 1


def test_submit_accepts_any_artifact_path_and_checks_revision_and_content() -> None:
    submitted_ctx = make_ctx()
    create_artifact(submitted_ctx, path="drafts/week-8.md", content="# Draft")
    submitted = decode(
        submit_artifact(
            submitted_ctx,
            path="drafts/week-8.md",
            expected_revision=1,
        )
    )

    stale_ctx = make_ctx()
    create_artifact(stale_ctx, path="article.md", content="# Article")
    stale = decode(submit_artifact(stale_ctx, path="article.md", expected_revision=2))

    empty_ctx = make_ctx()
    create_artifact(empty_ctx, path="empty.md", content="   ")
    empty = decode(submit_artifact(empty_ctx, path="empty.md", expected_revision=1))

    assert submitted["ok"] is True
    assert submitted_ctx.artifacts.submitted_path == "drafts/week-8.md"
    assert stale["error"]["code"] == "revision_conflict"
    assert empty["error"]["code"] == "empty_submission"


def test_submit_pins_existing_snapshot_and_final_artifact_is_immutable() -> None:
    ctx = make_ctx()
    created = decode(create_artifact(ctx, path="article.md", content="# Final"))
    before = ctx.artifacts.read("article.md")

    submitted = decode(
        submit_artifact(ctx, path="article.md", expected_revision=1)
    )
    after = ctx.artifacts.submitted_artifact
    repeated = decode(
        submit_artifact(ctx, path="article.md", expected_revision=1)
    )
    rejected_edit = decode(
        edit_artifact(
            ctx,
            path="article.md",
            old_text="Final",
            new_text="Changed",
            expected_revision=1,
        )
    )

    assert submitted["ok"] is True
    assert submitted["artifact"] == created["artifact"]
    assert submitted["finalized_revision"] == 1
    assert before is after
    assert len(ctx.artifacts.artifacts["article.md"].snapshots) == 1
    assert repeated["error"]["code"] == "artifact_finalized"
    assert rejected_edit["error"]["code"] == "artifact_finalized"
    assert ctx.log.entries[-2].data["operation"] == "submit_artifact"
    assert ctx.log.entries[-1].event_type == "completion"
