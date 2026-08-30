"""Generic Markdown artifact tools for the reporter runtime."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.state import ArtifactStoreError
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry


ARTIFACT_TOOL_IMPLEMENTATION_VERSION = "5"


ARTIFACT_TOOL_SPECS: list[ToolDef] = [
    {
        "type": "function",
        "function": {
            "name": "list_artifacts",
            "description": "List Markdown artifacts in the current reporter workspace.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_artifact",
            "description": "Read one Markdown artifact and its current revision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative POSIX .md path, such as research_brief.md.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_artifact",
            "description": (
                "Create a new Markdown artifact. The path must not already exist; "
                "use edit_artifact for later changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative POSIX .md path.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete initial Markdown content.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_artifact",
            "description": (
                "Replace exactly one literal text occurrence in an existing Markdown "
                "artifact. Read first and pass its current revision."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {
                        "type": "string",
                        "description": (
                            "Exact non-empty text expected once, including "
                            "whitespace."
                        ),
                    },
                    "new_text": {"type": "string"},
                    "expected_revision": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Revision returned by the most recent read or write.",
                    },
                },
                "required": ["path", "old_text", "new_text", "expected_revision"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_artifact",
            "description": (
                "Submit a Markdown artifact as the final reporter output. Submission "
                "pins the existing revision and makes that artifact immutable."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative POSIX path of the publishable artifact.",
                    },
                    "expected_revision": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": ["path", "expected_revision"],
            },
        },
    },
]


def register_artifact_tools(registry: ToolRegistry) -> None:
    """Register the generic artifact workspace tools."""
    handlers: dict[str, Callable[..., str]] = {
        "list_artifacts": list_artifacts,
        "read_artifact": read_artifact,
        "create_artifact": create_artifact,
        "edit_artifact": edit_artifact,
        "submit_artifact": submit_artifact,
    }
    for spec in ARTIFACT_TOOL_SPECS:
        name = spec["function"]["name"]
        registry.register_context_tool(
            name,
            handlers[name],
            spec,
            ARTIFACT_TOOL_IMPLEMENTATION_VERSION,
        )


def list_artifacts(ctx: ToolContext) -> str:
    artifacts = []
    for path in sorted(ctx.artifacts.artifacts):
        working = ctx.artifacts.artifacts[path]
        payload = working.current.model_dump(exclude={"content"})
        payload.update(
            {
                "revision_count": len(working.snapshots),
                "finalized_revision": working.finalized_revision,
            }
        )
        artifacts.append(payload)
    return _success({"artifacts": artifacts, "artifact_count": len(artifacts)})


def read_artifact(ctx: ToolContext, *, path: str) -> str:
    def operation() -> str:
        snapshot = ctx.artifacts.read(path)
        working = ctx.artifacts.artifacts[snapshot.path]
        return _success(
            {
                "artifact": snapshot.model_dump(),
                "revision_count": len(working.snapshots),
                "finalized_revision": working.finalized_revision,
            }
        )

    return _execute(operation)


def create_artifact(ctx: ToolContext, *, path: str, content: str) -> str:
    def operation() -> str:
        artifact = ctx.artifacts.create(
            path,
            content,
            on_change=ctx.record_artifact_mutation,
        )
        ctx.log.add_artifact_write(
            artifact.path,
            "create_artifact",
            artifact.path,
            artifact.revision,
            turn=ctx.turn,
        )
        return _success(
            {"artifact": artifact.model_dump(), "finalized_revision": None}
        )

    return _execute(operation)


def edit_artifact(
    ctx: ToolContext,
    *,
    path: str,
    old_text: str,
    new_text: str,
    expected_revision: int,
) -> str:
    def operation() -> str:
        artifact, changed = ctx.artifacts.edit(
            path,
            old_text=old_text,
            new_text=new_text,
            expected_revision=expected_revision,
            on_change=ctx.record_artifact_mutation,
        )
        if changed:
            ctx.log.add_artifact_write(
                artifact.path,
                "edit_artifact",
                artifact.path,
                artifact.revision,
                turn=ctx.turn,
            )
        return _success(
            {
                "artifact": artifact.model_dump(),
                "changed": changed,
                "replacement_count": 1,
                "finalized_revision": None,
            }
        )

    return _execute(operation)


def submit_artifact(
    ctx: ToolContext,
    *,
    path: str,
    expected_revision: int,
) -> str:
    def operation() -> str:
        readiness = ctx.brief.brief.readiness()
        if not readiness.submission_allowed:
            return _json(
                {
                    "ok": False,
                    "error": {
                        "code": "brief_not_ready",
                        "message": (
                            "Save at least one verified fact before submitting "
                            "an article."
                        ),
                        "readiness": readiness.model_dump(mode="json"),
                    },
                }
            )
        artifact = ctx.artifacts.submit(
            path,
            expected_revision=expected_revision,
        )
        stats = {
            "submitted_path": artifact.path,
            "revision": artifact.revision,
            "total_word_count": _word_count(artifact.content),
            "total_char_count": len(artifact.content),
        }
        ctx.log.add_artifact_write(
            artifact.path,
            "submit_artifact",
            artifact.path,
            artifact.revision,
            turn=ctx.turn,
        )
        ctx.log.add_memory_closeout(
            "article_submitted",
            turn=ctx.turn,
            submitted_path=artifact.path,
            revision=artifact.revision,
        )
        result: dict[str, Any] = {
            "artifact": artifact.model_dump(),
            "finalized_revision": artifact.revision,
            "stats": stats,
            "brief_readiness": readiness.model_dump(mode="json"),
        }
        if ctx.memory_closeout is not None:
            result["next_action"] = {
                "type": "mandatory_procedure",
                "name": "memory_closeout",
                "content": ctx.memory_closeout.procedure,
                "completion_tool": "complete_memory_review",
                "memory_writes_enabled": (
                    ctx.memory_closeout.memory_writes_enabled
                ),
            }
        return _success(result)

    return _execute(operation)


def _execute(operation: Callable[[], str]) -> str:
    try:
        return operation()
    except ArtifactStoreError as exc:
        return _json({"ok": False, "error": exc.as_dict()})


def _success(data: dict[str, Any]) -> str:
    return _json({"ok": True, **data})


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True)


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[.'-][A-Za-z0-9]+)*", text))


__all__ = [
    "ARTIFACT_TOOL_SPECS",
    "create_artifact",
    "edit_artifact",
    "list_artifacts",
    "read_artifact",
    "register_artifact_tools",
    "submit_artifact",
]
