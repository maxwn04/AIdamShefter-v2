"""Tests for reporter_v2 runner run logs."""

from __future__ import annotations

from datetime import datetime, timedelta

from reporter_v2.runner.run_log import RunLog, RunLogEntry, ProcedureSwitch


def test_add_tool_call() -> None:
    log = RunLog(session_id="test1234")

    log.add_tool_call(
        "standings",
        {"week": 8},
        "12 teams in standings",
        42,
        turn=3,
    )

    assert log.tool_call_count == 1
    assert len(log.entries) == 1

    entry = log.entries[0]
    assert entry.event_type == "tool_call"
    assert entry.turn == 3
    assert entry.data == {
        "tool_name": "standings",
        "params": {"week": 8},
        "result_summary": "12 teams in standings",
        "duration_ms": 42,
    }


def test_procedure_history() -> None:
    log = RunLog()

    log.add_procedure_switch(None, "research", turn=1)
    log.add_tool_call("league_snapshot", {}, "snapshot loaded", 10, turn=2)
    log.add_procedure_switch("research", "drafting", turn=5)

    assert log.procedure_history == [
        ProcedureSwitch(from_procedure=None, to_procedure="research", turn=1),
        ProcedureSwitch(from_procedure="research", to_procedure="drafting", turn=5),
    ]


def test_streaming(tmp_path) -> None:
    path = tmp_path / "run-log.md"
    log = RunLog(session_id="stream01", started_at="2026-05-18T10:00:00")

    log.start_streaming(path)
    log.add_procedure_switch(None, "research", turn=1)
    log.add_tool_call("standings", {}, "12 teams", 25, turn=2)
    log.add_artifact_write("brief", "save_fact", "fact_001", revision=1, turn=3)
    log.add_model_text("Drafting a lead from the standings.", turn=4)
    log.add_guardrail("tool_limit", 40, 50, turn=5)
    log.add_completion({"status": "done"}, turn=6)
    log.stop_streaming()

    content = path.read_text(encoding="utf-8")
    assert content.startswith("# Run Log: stream01\nStarted: 2026-05-18T10:00:00")
    assert "Loaded procedure: research" in content
    assert "standings() -> 12 teams [25ms]" in content
    assert "save_fact(fact_001) -> brief rev 1" in content
    assert "Model: Drafting a lead from the standings." in content
    assert "GUARDRAIL: tool_limit (40/50)" in content
    assert 'COMPLETE: {"status": "done"}' in content
    assert "Completed:" in content
    assert "Total tool calls: 1" in content
    assert log._stream_file is None


def test_format_elapsed() -> None:
    log = RunLog()
    log._start_time = datetime(2026, 5, 18, 10, 0, 0)
    entry = RunLogEntry(
        timestamp=(log._start_time + timedelta(minutes=2, seconds=7)).isoformat(),
        event_type="model_text",
        data={"text_preview": "hello"},
    )

    assert log._format_elapsed(entry) == "[02:07]"


def test_model_text_truncates_to_200_chars() -> None:
    log = RunLog()

    log.add_model_text("x" * 250, turn=1)

    assert len(log.entries[0].data["text_preview"]) == 200


def test_artifact_write_metadata_with_optional_revision() -> None:
    log = RunLog()

    log.add_artifact_write("brief", "set_outline", "outline", turn=7)

    entry = log.entries[0]
    assert entry.event_type == "artifact_write"
    assert entry.turn == 7
    assert entry.data == {
        "artifact": "brief",
        "operation": "set_outline",
        "key": "outline",
        "brief_revision": None,
    }
