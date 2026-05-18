# Phase 2: RunLog

**Goal:** Build the run log with typed entries, streaming to disk, and derived
properties.

**Files to create:**
- `reporter_v2/runner/run_log.py`
- `reporter_v2/tests/test_run_log.py`

**Dependencies:** None (independent of Phase 1 schemas)

---

## `reporter_v2/runner/run_log.py`

```python
# reporter_v2/runner/run_log.py
"""Run log for tracking all events during a runner session."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from pydantic import BaseModel, Field
from uuid import uuid4


class ProcedureSwitch(BaseModel):
    from_procedure: str | None
    to_procedure: str
    turn: int


class RunLogEntry(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    turn: int = 0
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)


class RunLog(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    entries: list[RunLogEntry] = Field(default_factory=list)

    _stream_file: TextIO | None = None
    _start_time: datetime | None = None

    class Config:
        underscore_attrs_are_private = True

    def model_post_init(self, __context: Any) -> None:
        self._start_time = datetime.now()

    def _add(self, entry: RunLogEntry) -> None:
        self.entries.append(entry)
        self._stream_entry(entry)

    def add_tool_call(
        self, tool_name: str, params: dict[str, Any],
        result_summary: str, duration_ms: int, *, turn: int
    ) -> None:
        self._add(RunLogEntry(
            turn=turn, event_type="tool_call",
            data={"tool_name": tool_name, "params": params,
                  "result_summary": result_summary, "duration_ms": duration_ms},
        ))

    def add_procedure_switch(
        self, from_proc: str | None, to_proc: str, *, turn: int
    ) -> None:
        self._add(RunLogEntry(
            turn=turn, event_type="procedure_switch",
            data={"from_procedure": from_proc, "to_procedure": to_proc},
        ))

    def add_artifact_write(
        self, artifact: str, operation: str, key: str,
        revision: int | None = None, *, turn: int
    ) -> None:
        self._add(RunLogEntry(
            turn=turn, event_type="artifact_write",
            data={"artifact": artifact, "operation": operation,
                  "key": key, "brief_revision": revision},
        ))

    def add_model_text(self, text_preview: str, *, turn: int) -> None:
        self._add(RunLogEntry(
            turn=turn, event_type="model_text",
            data={"text_preview": text_preview[:200]},
        ))

    def add_guardrail(
        self, guardrail_type: str, current: int, limit: int, *, turn: int
    ) -> None:
        self._add(RunLogEntry(
            turn=turn, event_type="guardrail",
            data={"guardrail_type": guardrail_type,
                  "current_count": current, "limit": limit},
        ))

    def add_completion(self, stats: dict[str, Any], *, turn: int) -> None:
        self._add(RunLogEntry(
            turn=turn, event_type="completion", data=stats,
        ))

    @property
    def tool_call_count(self) -> int:
        return sum(1 for e in self.entries if e.event_type == "tool_call")

    @property
    def procedure_history(self) -> list[ProcedureSwitch]:
        switches = []
        for e in self.entries:
            if e.event_type == "procedure_switch":
                switches.append(ProcedureSwitch(
                    from_procedure=e.data.get("from_procedure"),
                    to_procedure=e.data["to_procedure"],
                    turn=e.turn,
                ))
        return switches

    def start_streaming(self, path: Path) -> None:
        self._stream_file = open(path, "w", encoding="utf-8")
        self._stream_file.write(f"# Run Log: {self.session_id}\n")
        self._stream_file.write(f"Started: {self.started_at}\n\n")
        self._stream_file.flush()

    def stop_streaming(self) -> None:
        if self._stream_file:
            self._stream_file.write(f"\nCompleted: {datetime.now().isoformat()}\n")
            self._stream_file.write(f"Total tool calls: {self.tool_call_count}\n")
            self._stream_file.close()
            self._stream_file = None

    def _stream_entry(self, entry: RunLogEntry) -> None:
        if not self._stream_file:
            return
        elapsed = self._format_elapsed(entry)
        line = self._format_entry(entry, elapsed)
        self._stream_file.write(line + "\n")
        self._stream_file.flush()

    def _format_elapsed(self, entry: RunLogEntry) -> str:
        if self._start_time is None:
            return "[??:??]"
        delta = datetime.fromisoformat(entry.timestamp) - self._start_time
        minutes, seconds = divmod(int(delta.total_seconds()), 60)
        return f"[{minutes:02d}:{seconds:02d}]"

    def _format_entry(self, entry: RunLogEntry, elapsed: str) -> str:
        d = entry.data
        if entry.event_type == "procedure_switch":
            prev = f" (was: {d['from_procedure']})" if d.get("from_procedure") else ""
            return f"{elapsed} Loaded procedure: {d['to_procedure']}{prev}"
        elif entry.event_type == "tool_call":
            ms = d.get("duration_ms", 0)
            return f"{elapsed} {d['tool_name']}() -> {d['result_summary']} [{ms}ms]"
        elif entry.event_type == "artifact_write":
            rev = f" -> brief rev {d['brief_revision']}" if d.get("brief_revision") else ""
            return f"{elapsed} {d['operation']}({d['key']}){rev}"
        elif entry.event_type == "model_text":
            return f"{elapsed} Model: {d['text_preview'][:80]}"
        elif entry.event_type == "guardrail":
            return f"{elapsed} GUARDRAIL: {d['guardrail_type']} ({d['current_count']}/{d['limit']})"
        elif entry.event_type == "completion":
            return f"{elapsed} COMPLETE: {json.dumps(d)}"
        return f"{elapsed} {entry.event_type}: {d}"
```

## Tests

- `test_add_tool_call` -- add entry, verify `tool_call_count` increments
- `test_procedure_history` -- add multiple switches, verify `procedure_history` returns correct list
- `test_streaming` -- use `tmp_path`, start streaming, add entries, stop, read file and verify content
- `test_format_elapsed` -- verify elapsed time formatting
- All unit tests, no external dependencies.
