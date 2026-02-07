"""Reporter agent with iterative research-driven article generation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from agents import Agent, Runner, AgentOutputSchema

from datalayer.sleeper_data import SleeperLeagueData

from reporter.agent.config import ReportConfig, TimeRange, ToneControls, BiasProfile
from reporter.agent.research_log import ResearchLog
from reporter.agent.schemas import (
    ReportBrief,
    ArticleOutput,
    BriefMeta,
    Fact,
    Storyline,
    Section,
    ResolvedStyle,
    ResolvedBias,
)
from reporter.tools.sleeper_tools import ResearchToolAdapter, TOOL_DOCS
from reporter.tools.registry import create_tool_registry


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_path = prompts_dir / name
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


def _format_args(args: dict) -> str:
    """Format tool arguments for compact console display."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        if v is None:
            continue
        if isinstance(v, str) and len(v) > 30:
            v = v[:27] + "..."
        parts.append(f"{k}={v}")
    return ", ".join(parts)


class ResearchAgent:
    """Agent that iteratively researches and builds a brief.

    This agent has full access to data retrieval tools. It explores the
    league data, identifies storylines, and produces a ReportBrief for
    the draft phase. All tool calls and reasoning are automatically logged.
    """

    def __init__(
        self,
        data: SleeperLeagueData,
        config: ReportConfig,
        *,
        model: str = "gpt-5-mini",
        log_path: Optional[Path] = None,
    ):
        self.data = data
        self.config = config
        self.model = model
        self.log_path = log_path

        # Create research log and set up streaming if path provided
        self.research_log = ResearchLog()
        if log_path:
            self.research_log.start_streaming(log_path)

        # Create adapter with the shared log
        self.adapter = ResearchToolAdapter(data, research_log=self.research_log)
        self.tools = create_tool_registry(self.adapter)

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the research agent."""
        base_prompt = load_prompt("research_agent.md")

        # Add tool documentation
        prompt = f"{base_prompt}\n\n---\n\n{TOOL_DOCS}"

        return prompt

    def _build_user_prompt(self) -> str:
        """Build the user prompt with config details."""
        week_desc = (
            f"Week {self.config.time_range.week_start}"
            if self.config.time_range.week_start == self.config.time_range.week_end
            else f"Weeks {self.config.time_range.week_start}-{self.config.time_range.week_end}"
        )

        lines = [
            f"Research and build a brief for a fantasy football article covering {week_desc}.",
            "",
        ]

        if self.config.focus_hints:
            lines.append(f"**Focus areas:** {', '.join(self.config.focus_hints)}")

        if self.config.focus_teams:
            lines.append(f"**Focus teams:** {', '.join(self.config.focus_teams)}")

        if self.config.avoid_topics:
            lines.append(f"**Avoid topics:** {', '.join(self.config.avoid_topics)}")

        if self.config.custom_instructions:
            lines.append(
                f"\n**Special instructions:** {self.config.custom_instructions}"
            )

        lines.extend(
            [
                "",
                f"**Target voice:** {self.config.voice}",
                f"**Tone:** snark={self.config.tone.snark_level}, hype={self.config.tone.hype_level}",
                f"**Target length:** ~{self.config.length_target} words",
            ]
        )

        if self.config.bias_profile:
            bp = self.config.bias_profile
            if bp.favored_teams:
                lines.append(
                    f"**Favor teams:** {', '.join(bp.favored_teams)} (intensity {bp.intensity})"
                )
            if bp.disfavored_teams:
                lines.append(
                    f"**Roast teams:** {', '.join(bp.disfavored_teams)} (intensity {bp.intensity})"
                )

        lines.extend(
            [
                "",
                "Begin by getting the league snapshot with get_league_snapshot().",
                "Continue researching until you have enough material for a compelling article.",
                "Then output the complete ReportBrief JSON.",
            ]
        )

        return "\n".join(lines)

    async def research(self) -> tuple[ReportBrief, ResearchLog]:
        """Run the research agent to produce a brief and log.

        Uses Runner.run_streamed() to capture tool calls and model reasoning
        in real-time as they happen.

        Returns:
            Tuple of (ReportBrief, ResearchLog)
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt()

        agent = Agent(
            name="researcher",
            instructions=system_prompt,
            model=self.model,
            tools=self.tools,
            output_type=AgentOutputSchema(ReportBrief, strict_json_schema=False),
        )

        # Track tool call timing by call_id for duration calculation
        tool_start_times: dict[str, float] = {}
        tool_call_names: dict[str, str] = {}

        try:
            stream = Runner.run_streamed(agent, user_prompt, max_turns=30)

            async for event in stream.stream_events():
                if event.type != "run_item_stream_event":
                    continue

                if event.name == "message_output_created":
                    # Model's text output — reasoning before tool calls
                    msg = event.item.raw_item
                    for block in getattr(msg, "content", []):
                        text = getattr(block, "text", None)
                        if not text:
                            continue
                        text = text.strip()
                        # Skip large JSON blobs (likely the final structured output)
                        if not text or (text[0] in "{[" and len(text) > 500):
                            continue
                        self.research_log.add_reasoning(text)
                        preview = text[:120].replace("\n", " ")
                        print(
                            f"  \U0001f4ad {preview}{'...' if len(text) > 120 else ''}"
                        )

                elif event.name == "reasoning_item_created":
                    # Reasoning blocks from reasoning models (o1/o3)
                    reasoning = event.item.raw_item
                    for summary in getattr(reasoning, "summary", []):
                        text = getattr(summary, "text", "").strip()
                        if text:
                            self.research_log.add_reasoning(text)
                            preview = text[:120].replace("\n", " ")
                            print(
                                f"  \U0001f4ad {preview}"
                                f"{'...' if len(text) > 120 else ''}"
                            )

                elif event.name == "tool_called":
                    # Tool invocation — log with params and record start time
                    raw = event.item.raw_item
                    call_id = raw.call_id
                    tool_start_times[call_id] = time.time()
                    tool_call_names[call_id] = raw.name
                    args = json.loads(raw.arguments) if raw.arguments else {}
                    self.research_log.add_tool_start(raw.name, args)
                    args_str = _format_args(args)
                    print(f"  -> {raw.name}({args_str})", flush=True)

                elif event.name == "tool_output":
                    # Tool result — log with timing
                    raw = event.item.raw_item
                    call_id = getattr(raw, "call_id", None)
                    tool_name = tool_call_names.pop(call_id, "unknown") if call_id else "unknown"
                    start = tool_start_times.pop(call_id, time.time()) if call_id else time.time()
                    duration_ms = int((time.time() - start) * 1000)

                    result_str = getattr(raw, "output", "")
                    if not isinstance(result_str, str):
                        try:
                            result_str = json.dumps(result_str, default=str)
                        except Exception:
                            result_str = str(result_str)
                    if len(result_str) > 1000:
                        result_str = result_str[:1000] + "..."

                    self.research_log.add_tool_end(tool_name, result_str, duration_ms)
                    print(f"  <- {tool_name} ({duration_ms}ms)")

            # Log the final output
            if stream.final_output:
                preview = str(stream.final_output)[:200]
                self.research_log.add_output(f"ReportBrief generated: {preview}...")

            return stream.final_output, self.research_log
        finally:
            # Always close the streaming file
            self.research_log.stop_streaming()


class DraftAgent:
    """Agent that writes the article from a brief.

    This agent has NO access to data tools. It writes purely from the
    research brief, applying the configured voice and style.
    """

    def __init__(self, config: ReportConfig, *, model: str = "gpt-5-mini"):
        self.config = config
        self.model = model

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the draft agent."""
        return load_prompt("draft_agent.md")

    def _build_user_prompt(self, brief: ReportBrief) -> str:
        """Build the user prompt with brief and config."""
        lines = [
            "Write a fantasy football article based on this research brief.",
            "",
            "## Research Brief",
            "",
            brief.model_dump_json(indent=2),
            "",
            "## Configuration",
            "",
            f"**Voice:** {self.config.voice}",
            f"**Target length:** ~{self.config.length_target} words",
            f"**Tone:** snark={self.config.tone.snark_level}, hype={self.config.tone.hype_level}",
        ]

        if self.config.profanity_policy != "none":
            lines.append(f"**Profanity:** {self.config.profanity_policy}")

        bias_instructions = self.config.get_bias_instructions()
        if bias_instructions:
            lines.extend(["", bias_instructions])

        if self.config.custom_instructions:
            lines.extend(
                [
                    "",
                    "## Additional Instructions",
                    self.config.custom_instructions,
                ]
            )

        lines.extend(
            [
                "",
                "Write the article now. Use Markdown formatting.",
            ]
        )

        return "\n".join(lines)

    async def draft(self, brief: ReportBrief) -> str:
        """Write the article from the brief.

        Args:
            brief: The research brief to write from.

        Returns:
            The article as a Markdown string.
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(brief)

        agent = Agent(
            name="writer",
            instructions=system_prompt,
            model=self.model,
            tools=[],  # No tools in draft phase
        )

        result = await Runner.run(agent, user_prompt)
        return result.final_output


class ReporterAgent:
    """Main agent orchestrating research and drafting.

    This is the primary entry point for generating articles. It coordinates
    the research and draft phases, producing a complete ArticleOutput.
    """

    def __init__(
        self,
        data: SleeperLeagueData,
        *,
        model: str = "gpt-5-mini",
    ):
        self.data = data
        self.model = model

    async def run(
        self,
        request: str,
        *,
        week: Optional[int] = None,
        week_start: Optional[int] = None,
        week_end: Optional[int] = None,
        voice: str = "sports columnist",
        snark_level: int = 1,
        hype_level: int = 1,
        focus_hints: Optional[list[str]] = None,
        focus_teams: Optional[list[str]] = None,
        avoid_topics: Optional[list[str]] = None,
        favored_teams: Optional[list[str]] = None,
        disfavored_teams: Optional[list[str]] = None,
        bias_intensity: int = 2,
        length_target: int = 1000,
        profanity_policy: str = "none",
    ) -> ArticleOutput:
        """Generate an article from a natural language request.

        Args:
            request: The user's request (used as custom_instructions).
            week: Single week to cover (use this OR week_start/week_end).
            week_start: Start of week range (use with week_end).
            week_end: End of week range (use with week_start).
            voice: Writing voice/persona.
            snark_level: 0-3, how snarky the article should be.
            hype_level: 0-3, how hyped/energetic.
            focus_hints: Topics to emphasize.
            focus_teams: Teams to emphasize.
            avoid_topics: Topics to skip.
            favored_teams: Teams to frame positively.
            disfavored_teams: Teams to frame negatively.
            bias_intensity: 0-3, how strong the bias.
            length_target: Target word count.
            profanity_policy: "none", "mild", or "unrestricted".

        Returns:
            ArticleOutput with article, config, brief, and research log.
        """
        # Build time range
        if week is not None:
            time_range = TimeRange.single_week(week)
        elif week_start is not None and week_end is not None:
            time_range = TimeRange.range(week_start, week_end)
        else:
            # Default to current week from data
            current_week = self.data.effective_week
            time_range = TimeRange.single_week(current_week)

        # Build bias profile
        bias_profile = None
        if favored_teams or disfavored_teams:
            bias_profile = BiasProfile(
                favored_teams=favored_teams or [],
                disfavored_teams=disfavored_teams or [],
                intensity=bias_intensity,
            )

        # Build config
        config = ReportConfig(
            time_range=time_range,
            focus_hints=focus_hints or [],
            avoid_topics=avoid_topics or [],
            focus_teams=focus_teams or [],
            voice=voice,
            tone=ToneControls(snark_level=snark_level, hype_level=hype_level),
            profanity_policy=profanity_policy,
            bias_profile=bias_profile,
            length_target=length_target,
            custom_instructions=request,
        )

        # Phase 1: Research
        research_agent = ResearchAgent(self.data, config, model=self.model)
        brief, research_log = await research_agent.research()

        # Phase 2: Draft
        draft_agent = DraftAgent(config, model=self.model)
        article = await draft_agent.draft(brief)

        return ArticleOutput(
            article=article,
            config=config,
            brief=brief,
            research_log=research_log,
            verification=None,
            trace_id=None,
        )

    async def run_with_config(
        self,
        config: ReportConfig,
        *,
        log_path: Optional[Path] = None,
    ) -> ArticleOutput:
        """Generate an article from a pre-built config.

        Args:
            config: The ReportConfig to use.
            log_path: Optional path for streaming research log. If provided,
                the log will be written in real-time to this file.

        Returns:
            ArticleOutput with article, config, brief, and research log.
        """
        # Phase 1: Research
        research_agent = ResearchAgent(
            self.data, config, model=self.model, log_path=log_path
        )
        brief, research_log = await research_agent.research()

        # Phase 2: Draft
        draft_agent = DraftAgent(config, model=self.model)
        article = await draft_agent.draft(brief)

        return ArticleOutput(
            article=article,
            config=config,
            brief=brief,
            research_log=research_log,
            verification=None,
            trace_id=None,
        )
