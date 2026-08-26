"""Run log for tracking all events during a runner session."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from pydantic import BaseModel, Field, PrivateAttr


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

    _stream_file: TextIO | None = PrivateAttr(default=None)
    _start_time: datetime = PrivateAttr(default_factory=datetime.now)

    def _add(self, entry: RunLogEntry) -> None:
        self.entries.append(entry)
        self._stream_entry(entry)

    def add_tool_call(
        self,
        tool_name: str,
        params: dict[str, Any],
        result_summary: str,
        duration_ms: int,
        *,
        turn: int,
    ) -> None:
        self._add(
            RunLogEntry(
                turn=turn,
                event_type="tool_call",
                data={
                    "tool_name": tool_name,
                    "params": params,
                    "result_summary": result_summary,
                    "duration_ms": duration_ms,
                },
            )
        )

    def add_procedure_switch(
        self,
        from_proc: str | None,
        to_proc: str,
        *,
        turn: int,
    ) -> None:
        self._add(
            RunLogEntry(
                turn=turn,
                event_type="procedure_switch",
                data={"from_procedure": from_proc, "to_procedure": to_proc},
            )
        )

    def add_artifact_write(
        self,
        artifact: str,
        operation: str,
        key: str,
        revision: int | None = None,
        *,
        turn: int,
    ) -> None:
        self._add(
            RunLogEntry(
                turn=turn,
                event_type="artifact_write",
                data={
                    "artifact": artifact,
                    "operation": operation,
                    "key": key,
                    "brief_revision": revision,
                },
            )
        )

    def add_model_text(self, text_preview: str, *, turn: int) -> None:
        self._add(
            RunLogEntry(
                turn=turn,
                event_type="model_text",
                data={"text_preview": text_preview[:200]},
            )
        )

    def add_guardrail(
        self,
        guardrail_type: str,
        current: int,
        limit: int,
        *,
        turn: int,
    ) -> None:
        self._add(
            RunLogEntry(
                turn=turn,
                event_type="guardrail",
                data={
                    "guardrail_type": guardrail_type,
                    "current_count": current,
                    "limit": limit,
                },
            )
        )

    def add_completion(self, stats: dict[str, Any], *, turn: int) -> None:
        self._add(RunLogEntry(turn=turn, event_type="completion", data=stats))

    @property
    def tool_call_count(self) -> int:
        return sum(1 for entry in self.entries if entry.event_type == "tool_call")

    @property
    def procedure_history(self) -> list[ProcedureSwitch]:
        switches: list[ProcedureSwitch] = []
        for entry in self.entries:
            if entry.event_type == "procedure_switch":
                switches.append(
                    ProcedureSwitch(
                        from_procedure=entry.data.get("from_procedure"),
                        to_procedure=entry.data["to_procedure"],
                        turn=entry.turn,
                    )
                )
        return switches

    def first_artifact_write_turn(
        self,
        *,
        operations: frozenset[str],
        artifact: str | None = None,
        excluded_artifacts: frozenset[str] = frozenset(),
    ) -> int | None:
        """Return the first successful matching artifact-write turn."""
        for entry in self.entries:
            if entry.event_type != "artifact_write":
                continue
            entry_artifact = entry.data.get("artifact")
            if entry.data.get("operation") not in operations:
                continue
            if artifact is not None and entry_artifact != artifact:
                continue
            if entry_artifact in excluded_artifacts:
                continue
            return entry.turn
        return None

    def start_streaming(self, path: Path) -> None:
        self._stream_file = open(path, "w", encoding="utf-8")
        self._stream_file.write(f"# Run Log: {self.session_id}\n")
        self._stream_file.write(f"Started: {self.started_at}\n\n")
        self._stream_file.flush()

    def stop_streaming(self) -> None:
        if self._stream_file is None:
            return

        self._stream_file.write(f"\nCompleted: {datetime.now().isoformat()}\n")
        self._stream_file.write(f"Total tool calls: {self.tool_call_count}\n")
        self._stream_file.close()
        self._stream_file = None

    def _stream_entry(self, entry: RunLogEntry) -> None:
        if self._stream_file is None:
            return

        elapsed = self._format_elapsed(entry)
        line = self._format_entry(entry, elapsed)
        self._stream_file.write(line + "\n")
        self._stream_file.flush()

    def _format_elapsed(self, entry: RunLogEntry) -> str:
        delta = datetime.fromisoformat(entry.timestamp) - self._start_time
        minutes, seconds = divmod(int(delta.total_seconds()), 60)
        return f"[{minutes:02d}:{seconds:02d}]"

    def _format_entry(self, entry: RunLogEntry, elapsed: str) -> str:
        data = entry.data
        if entry.event_type == "procedure_switch":
            previous = (
                f" (was: {data['from_procedure']})"
                if data.get("from_procedure")
                else ""
            )
            return f"{elapsed} Loaded procedure: {data['to_procedure']}{previous}"
        if entry.event_type == "tool_call":
            duration_ms = data.get("duration_ms", 0)
            params = self._format_params(data.get("params", {}))
            return (
                f"{elapsed} {data['tool_name']}({params}) -> "
                f"{data['result_summary']} [{duration_ms}ms]"
            )
        if entry.event_type == "artifact_write":
            revision = (
                f" -> brief rev {data['brief_revision']}"
                if data.get("brief_revision")
                else ""
            )
            return f"{elapsed} {data['operation']}({data['key']}){revision}"
        if entry.event_type == "model_text":
            return f"{elapsed} Model: {data['text_preview'][:80]}"
        if entry.event_type == "guardrail":
            return (
                f"{elapsed} GUARDRAIL: {data['guardrail_type']} "
                f"({data['current_count']}/{data['limit']})"
            )
        if entry.event_type == "completion":
            return f"{elapsed} COMPLETE: {json.dumps(data)}"
        return f"{elapsed} {entry.event_type}: {data}"

    @staticmethod
    def _format_params(params: Any, *, max_chars: int = 300) -> str:
        if not params:
            return ""

        formatted = json.dumps(
            params,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        if len(formatted) <= max_chars:
            return formatted
        return formatted[: max_chars - 3] + "..."
