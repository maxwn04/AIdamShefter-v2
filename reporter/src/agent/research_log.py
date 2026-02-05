"""Research log for tracking agent reasoning and tool calls with real-time streaming."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO
from uuid import uuid4

from pydantic import BaseModel, Field


class ResearchLogEntry(BaseModel):
    """A single entry in the research log."""

    entry_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    entry_type: str = Field(description="Type: reasoning, tool_start, tool_end, output")

    # For reasoning entries (captured from model output before tool calls)
    reasoning: Optional[str] = Field(
        default=None, description="The model's reasoning/thinking text"
    )

    # For tool_start entries
    tool_name: Optional[str] = Field(default=None, description="Name of the tool called")
    tool_params: Optional[dict] = Field(
        default=None, description="Parameters passed to the tool"
    )

    # For tool_end entries
    tool_result: Optional[str] = Field(
        default=None, description="Result from the tool (may be truncated)"
    )
    duration_ms: Optional[int] = Field(
        default=None, description="How long the tool call took"
    )

    # For output entries (final output from agent)
    output_preview: Optional[str] = Field(
        default=None, description="Preview of final output"
    )


class ResearchLog(BaseModel):
    """Complete log of the research process with optional real-time file streaming."""

    session_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    entries: list[ResearchLogEntry] = Field(default_factory=list)

    # Summary stats
    tool_calls: int = Field(default=0)
    reasoning_entries: int = Field(default=0)

    # File streaming (not serialized)
    _stream_file: Optional[TextIO] = None
    _stream_path: Optional[Path] = None

    class Config:
        underscore_attrs_are_private = True

    def start_streaming(self, file_path: Path) -> None:
        """Start streaming entries to a file in real-time.

        Args:
            file_path: Path to write the streaming log.
        """
        self._stream_path = file_path
        self._stream_file = open(file_path, "w", encoding="utf-8")
        # Write header
        self._stream_file.write(f"# Research Log: {self.session_id}\n")
        self._stream_file.write(f"Started: {self.started_at}\n")
        self._stream_file.write("=" * 60 + "\n\n")
        self._stream_file.flush()

    def stop_streaming(self) -> None:
        """Close the streaming file."""
        if self._stream_file:
            self._stream_file.write("\n" + "=" * 60 + "\n")
            self._stream_file.write(f"Completed: {datetime.now().isoformat()}\n")
            self._stream_file.write(f"Total tool calls: {self.tool_calls}\n")
            self._stream_file.write(f"Total reasoning entries: {self.reasoning_entries}\n")
            self._stream_file.close()
            self._stream_file = None

    def _stream_entry(self, entry: ResearchLogEntry) -> None:
        """Write an entry to the stream file immediately."""
        if not self._stream_file:
            return

        ts = entry.timestamp.split("T")[1].split(".")[0]  # Just HH:MM:SS

        if entry.entry_type == "reasoning":
            self._stream_file.write(f"\n[{ts}] 💭 REASONING\n")
            if entry.reasoning:
                # Indent the reasoning text
                for line in entry.reasoning.split("\n"):
                    self._stream_file.write(f"  {line}\n")

        elif entry.entry_type == "tool_start":
            self._stream_file.write(f"\n[{ts}] 🔧 TOOL: {entry.tool_name}\n")
            if entry.tool_params:
                self._stream_file.write(f"  Params: {entry.tool_params}\n")

        elif entry.entry_type == "tool_end":
            self._stream_file.write(f"[{ts}] ✓ RESULT ({entry.duration_ms}ms)\n")
            if entry.tool_result:
                # Truncate long results
                result = entry.tool_result
                if len(result) > 500:
                    result = result[:500] + "... (truncated)"
                for line in result.split("\n")[:10]:  # Max 10 lines
                    self._stream_file.write(f"  {line}\n")

        elif entry.entry_type == "output":
            self._stream_file.write(f"\n[{ts}] 📝 FINAL OUTPUT\n")
            if entry.output_preview:
                self._stream_file.write(f"  {entry.output_preview}\n")

        self._stream_file.flush()

    def add_entry(self, entry: ResearchLogEntry) -> None:
        """Add an entry to the log, update counts, and stream if enabled."""
        self.entries.append(entry)

        if entry.entry_type == "tool_start":
            self.tool_calls += 1
        elif entry.entry_type == "reasoning":
            self.reasoning_entries += 1

        # Stream to file if enabled
        self._stream_entry(entry)

    def add_reasoning(self, reasoning: str) -> ResearchLogEntry:
        """Add a reasoning entry captured from model output."""
        entry = ResearchLogEntry(
            entry_type="reasoning",
            reasoning=reasoning,
        )
        self.add_entry(entry)
        return entry

    def add_tool_start(
        self,
        tool_name: str,
        tool_params: dict,
    ) -> ResearchLogEntry:
        """Add a tool start entry."""
        entry = ResearchLogEntry(
            entry_type="tool_start",
            tool_name=tool_name,
            tool_params=tool_params,
        )
        self.add_entry(entry)
        return entry

    def add_tool_end(
        self,
        tool_name: str,
        tool_result: str,
        duration_ms: int = 0,
    ) -> ResearchLogEntry:
        """Add a tool end entry."""
        entry = ResearchLogEntry(
            entry_type="tool_end",
            tool_name=tool_name,
            tool_result=tool_result,
            duration_ms=duration_ms,
        )
        self.add_entry(entry)
        return entry

    def add_output(self, output_preview: str) -> ResearchLogEntry:
        """Add a final output entry."""
        entry = ResearchLogEntry(
            entry_type="output",
            output_preview=output_preview,
        )
        self.add_entry(entry)
        return entry

    def get_tool_calls_with_reasoning(self) -> list[dict]:
        """Get all tool calls paired with their preceding reasoning."""
        result = []
        pending_reasoning = None

        for entry in self.entries:
            if entry.entry_type == "reasoning":
                pending_reasoning = entry.reasoning
            elif entry.entry_type == "tool_start":
                result.append({
                    "tool": entry.tool_name,
                    "params": entry.tool_params,
                    "reasoning": pending_reasoning,
                })
                pending_reasoning = None

        return result

    def to_markdown(self) -> str:
        """Export log as readable markdown for debugging."""
        lines = [
            f"# Research Log: {self.session_id}",
            f"Started: {self.started_at}",
            "",
            "## Summary",
            f"- Tool calls: {self.tool_calls}",
            f"- Reasoning entries: {self.reasoning_entries}",
            "",
            "## Timeline",
            "",
        ]

        for entry in self.entries:
            ts = entry.timestamp.split("T")[1].split(".")[0]

            if entry.entry_type == "reasoning":
                lines.append(f"### [{ts}] Reasoning")
                if entry.reasoning:
                    lines.append(f"> {entry.reasoning[:200]}...")
                lines.append("")

            elif entry.entry_type == "tool_start":
                lines.append(f"### [{ts}] Tool: `{entry.tool_name}`")
                lines.append(f"**Params:** `{entry.tool_params}`")

            elif entry.entry_type == "tool_end":
                lines.append(f"**Duration:** {entry.duration_ms}ms")
                if entry.tool_result:
                    result = entry.tool_result[:200]
                    lines.append(f"**Result:** {result}...")
                lines.append("")

            elif entry.entry_type == "output":
                lines.append("### Final Output")
                if entry.output_preview:
                    lines.append(f"{entry.output_preview}")
                lines.append("")

        return "\n".join(lines)
