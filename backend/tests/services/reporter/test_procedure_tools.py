"""Tests for backend.services.reporter procedure-loading tools."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.services.reporter.runner.run_log import RunLog, ProcedureSwitch
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools import procedure_tools
from backend.services.reporter.runner.tools.procedure_tools import load_procedure


def make_context(*, turn: int = 0) -> ToolContext:
    return ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(),
        turn=turn,
    )


def test_load_valid_procedure(tmp_path, monkeypatch) -> None:
    procedure_text = "# Research\n\nGather the facts first.\n"
    (tmp_path / "research.md").write_text(procedure_text, encoding="utf-8")
    monkeypatch.setattr(procedure_tools, "PROCEDURE_DIR", tmp_path)
    ctx = make_context(turn=2)

    result = load_procedure(ctx, name="research")

    assert result == procedure_text
    assert ctx.procedures.active == "research"


def test_load_invalid_procedure() -> None:
    ctx = make_context()

    result = json.loads(load_procedure(ctx, name="bogus"))

    assert result == {
        "error": (
            "Unknown procedure: bogus. "
            "Valid: ['drafting', 'research', 'storyline', 'verification']"
        )
    }
    assert ctx.procedures.active is None
    assert ctx.log.procedure_history == []


def test_load_missing_procedure_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(procedure_tools, "PROCEDURE_DIR", tmp_path)
    ctx = make_context()

    result = json.loads(load_procedure(ctx, name="research"))

    assert result == {"error": f"Procedure file not found: {tmp_path / 'research.md'}"}
    assert ctx.procedures.active is None
    assert ctx.log.procedure_history == []


def test_procedure_switch_logged(tmp_path, monkeypatch) -> None:
    (tmp_path / "research.md").write_text("research text", encoding="utf-8")
    (tmp_path / "drafting.md").write_text("drafting text", encoding="utf-8")
    monkeypatch.setattr(procedure_tools, "PROCEDURE_DIR", tmp_path)
    ctx = make_context(turn=4)

    load_procedure(ctx, name="research")
    ctx.turn = 7
    load_procedure(ctx, name="drafting")

    assert ctx.log.procedure_history == [
        ProcedureSwitch(from_procedure=None, to_procedure="research", turn=4),
        ProcedureSwitch(from_procedure="research", to_procedure="drafting", turn=7),
    ]


def test_procedure_state_updated(tmp_path, monkeypatch) -> None:
    (tmp_path / "storyline.md").write_text("storyline text", encoding="utf-8")
    (tmp_path / "verification.md").write_text("verification text", encoding="utf-8")
    monkeypatch.setattr(procedure_tools, "PROCEDURE_DIR", tmp_path)
    ctx = make_context()

    load_procedure(ctx, name="storyline")
    assert ctx.procedures.active == "storyline"

    load_procedure(ctx, name="verification")
    assert ctx.procedures.active == "verification"


def test_prompts_reference_only_generic_artifact_tools() -> None:
    reporter_root = (
        Path(__file__).parents[4] / "backend" / "services" / "reporter"
    )
    prompt_paths = [
        reporter_root / "prompts" / "system.md",
        *(reporter_root / "procedures").glob("*.md"),
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in prompt_paths)

    removed_tools = {
        "read_brief",
        "save_fact",
        "save_storyline",
        "set_style",
        "set_bias",
        "set_outline",
        "save_memory_callback",
        "read_article",
        "write_section",
        "rewrite_section",
        "set_section_order",
        "submit_article",
    }
    for tool_name in removed_tools:
        assert re.search(rf"`{re.escape(tool_name)}(?:`|\()", content) is None

    for tool_name in {
        "list_artifacts",
        "read_artifact",
        "create_artifact",
        "edit_artifact",
        "submit_artifact",
    }:
        assert f"`{tool_name}" in content
