"""Reporter agent with iterative research-driven article generation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from agents import Agent, Runner, AgentOutputSchema, RunHooks, RunContextWrapper, Tool

from datalayer.sleeper_data import SleeperLeagueData

from agent.config import ReportConfig, TimeRange, ToneControls, BiasProfile
from agent.research_log import ResearchLog
from agent.schemas import (
    ReportBrief,
    ArticleOutput,
    BriefMeta,
    Fact,
    Storyline,
    Section,
    ResolvedStyle,
    ResolvedBias,
)
from tools.sleeper_tools import ResearchToolAdapter, TOOL_DOCS
from tools.registry import create_tool_registry


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_path = prompts_dir / name
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


class ResearchLoggingHooks(RunHooks):
    """Hooks that capture model reasoning and tool calls, streaming to a log file.

    This middleware automatically logs:
    - Tool calls with parameters (captured from adapter)
    - Tool results with timing
    - Model reasoning (extracted from conversation context)
    """

    def __init__(self, research_log: ResearchLog):
        self.log = research_log
        self._tool_start_times: dict[str, float] = {}
        self._last_reasoning: Optional[str] = None

    def _extract_last_reasoning(self, context: RunContextWrapper) -> Optional[str]:
        """Extract the most recent assistant text from conversation context.

        This captures the model's reasoning that preceded tool calls.
        """
        try:
            # Try to access the conversation messages
            # The structure depends on the OpenAI Agents SDK version
            if hasattr(context, 'messages'):
                messages = context.messages
            elif hasattr(context, 'context') and hasattr(context.context, 'messages'):
                messages = context.context.messages
            else:
                return None

            # Find the last assistant message with text content
            for msg in reversed(messages):
                if getattr(msg, 'role', None) == 'assistant':
                    # Extract text content
                    content = getattr(msg, 'content', None)
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    elif isinstance(content, list):
                        # Handle content blocks
                        for block in content:
                            if hasattr(block, 'text') and block.text:
                                return block.text.strip()
                            elif isinstance(block, dict) and block.get('text'):
                                return block['text'].strip()
        except Exception:
            pass
        return None

    async def on_tool_start(
        self, context: RunContextWrapper, agent: Agent, tool: Tool
    ) -> None:
        """Called when a tool is about to be invoked."""
        # Record start time for duration calculation
        self._tool_start_times[tool.name] = time.time()

        # Try to capture preceding reasoning
        reasoning = self._extract_last_reasoning(context)
        if reasoning and reasoning != self._last_reasoning:
            self.log.add_reasoning(reasoning)
            self._last_reasoning = reasoning

        # Print progress to console
        print(f"  -> {tool.name}...", end="", flush=True)

    async def on_tool_end(
        self, context: RunContextWrapper, agent: Agent, tool: Tool, result: Any
    ) -> None:
        """Called after a tool completes."""
        # Calculate duration
        start_time = self._tool_start_times.pop(tool.name, time.time())
        duration_ms = int((time.time() - start_time) * 1000)

        # Convert result to string for logging
        if isinstance(result, str):
            result_str = result
        else:
            try:
                result_str = json.dumps(result, default=str)
            except Exception:
                result_str = str(result)

        # Truncate long results
        if len(result_str) > 1000:
            result_str = result_str[:1000] + "..."

        # Log tool end with result
        self.log.add_tool_end(
            tool_name=tool.name,
            tool_result=result_str,
            duration_ms=duration_ms,
        )

        print(f" done ({duration_ms}ms)")


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
        model: str = "gpt-4o",
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

        # Create hooks for logging
        hooks = ResearchLoggingHooks(self.research_log)

        try:
            # Allow more turns for iterative research (default is 10)
            result = await Runner.run(agent, user_prompt, max_turns=30, hooks=hooks)

            # Log the final output
            if result.final_output:
                preview = str(result.final_output)[:200]
                self.research_log.add_output(f"ReportBrief generated: {preview}...")

            return result.final_output, self.research_log
        finally:
            # Always close the streaming file
            self.research_log.stop_streaming()


class DraftAgent:
    """Agent that writes the article from a brief.

    This agent has NO access to data tools. It writes purely from the
    research brief, applying the configured voice and style.
    """

    def __init__(self, config: ReportConfig, *, model: str = "gpt-4o"):
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
        model: str = "gpt-4o",
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
