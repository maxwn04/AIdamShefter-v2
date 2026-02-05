"""Clarification agent for gathering article requirements interactively."""

from __future__ import annotations

import json
from typing import Optional, Any

from agents import Agent, Runner, function_tool

from datalayer.sleeper_data import SleeperLeagueData

from agent.config import ReportConfig, TimeRange, ToneControls, BiasProfile


class ClarificationAgent:
    """Agent that clarifies user requirements through interactive questions.

    This agent analyzes the user's initial prompt and asks targeted questions
    to fill in missing details before research begins.
    """

    def __init__(
        self,
        data: SleeperLeagueData,
        *,
        default_week: Optional[int] = None,
        model: str = "gpt-5-mini",
    ):
        self.data = data
        self.default_week = default_week or data.effective_week
        self.model = model

        # State for building config
        self._config_data: dict[str, Any] = {
            "week_start": self.default_week,
            "week_end": self.default_week,
            "voice": "sports columnist",
            "snark_level": 1,
            "hype_level": 1,
            "length_target": 1000,
            "focus_hints": [],
            "focus_teams": [],
            "avoid_topics": [],
            "favored_teams": [],
            "disfavored_teams": [],
            "bias_intensity": 2,
            "custom_instructions": "",
        }

        # Get team names for validation
        self._team_names = self._get_team_names()

    def _get_team_names(self) -> list[str]:
        """Get list of team names from the data."""
        try:
            result = self.data.run_sql(
                "SELECT DISTINCT team_name FROM rosters WHERE team_name IS NOT NULL"
            )
            if result.get("data"):
                return [row["team_name"] for row in result["data"]]
        except Exception:
            pass
        return []

    def _build_tools(self):
        """Build the tools for the clarification agent."""

        @function_tool
        def ask_user(question: str, options: list[str] | None = None) -> str:
            """Ask the user a clarifying question.

            Args:
                question: The question to ask the user.
                options: Optional list of suggested options (user can also type freely).

            Returns:
                The user's response.
            """
            print()
            print(f"Q: {question}")
            if options:
                print(f"   Options: {', '.join(options)}")
            response = input("A: ").strip()
            return response if response else "(no response)"

        @function_tool
        def set_week(week: int) -> dict:
            """Set the week to cover in the article.

            Args:
                week: The week number.
            """
            self._config_data["week_start"] = week
            self._config_data["week_end"] = week
            return {"set": "week", "value": week}

        @function_tool
        def set_week_range(week_start: int, week_end: int) -> dict:
            """Set a range of weeks to cover.

            Args:
                week_start: Starting week.
                week_end: Ending week.
            """
            self._config_data["week_start"] = week_start
            self._config_data["week_end"] = week_end
            return {"set": "week_range", "value": f"{week_start}-{week_end}"}

        @function_tool
        def set_voice(voice: str) -> dict:
            """Set the writing voice/persona.

            Args:
                voice: The voice to use. Examples:
                    - "sports columnist" (default, professional)
                    - "snarky columnist" (witty, irreverent)
                    - "hype broadcaster" (energetic, excitable)
                    - "beat reporter" (factual, measured)
                    - "noir detective" (moody, dramatic)
            """
            self._config_data["voice"] = voice
            return {"set": "voice", "value": voice}

        @function_tool
        def set_tone(snark_level: int = 1, hype_level: int = 1) -> dict:
            """Set the tone levels for the article.

            Args:
                snark_level: 0=none, 1=light, 2=moderate, 3=savage
                hype_level: 0=reserved, 1=normal, 2=energetic, 3=maximum
            """
            self._config_data["snark_level"] = max(0, min(3, snark_level))
            self._config_data["hype_level"] = max(0, min(3, hype_level))
            return {
                "set": "tone",
                "snark_level": self._config_data["snark_level"],
                "hype_level": self._config_data["hype_level"],
            }

        @function_tool
        def set_length(words: int) -> dict:
            """Set target article length.

            Args:
                words: Target word count (500=short, 1000=medium, 1500=long).
            """
            self._config_data["length_target"] = words
            return {"set": "length_target", "value": words}

        @function_tool
        def add_focus(topics: list[str]) -> dict:
            """Add topics to focus on in the article.

            Args:
                topics: Topics to emphasize. Examples:
                    - "upsets" - unexpected wins
                    - "trades" - transaction analysis
                    - "standings" - playoff implications
                    - "top performers" - best players
                    - "close games" - nail-biters
            """
            self._config_data["focus_hints"].extend(topics)
            return {"set": "focus_hints", "value": self._config_data["focus_hints"]}

        @function_tool
        def add_focus_teams(teams: list[str]) -> dict:
            """Add specific teams to focus on.

            Args:
                teams: Team names to emphasize.
            """
            self._config_data["focus_teams"].extend(teams)
            return {"set": "focus_teams", "value": self._config_data["focus_teams"]}

        @function_tool
        def set_bias(
            favored: list[str] | None = None,
            disfavored: list[str] | None = None,
            intensity: int = 2,
        ) -> dict:
            """Set bias for team framing (affects word choice, not facts).

            Args:
                favored: Teams to frame positively.
                disfavored: Teams to frame negatively/mockingly.
                intensity: 1=subtle, 2=noticeable, 3=heavy.
            """
            if favored:
                self._config_data["favored_teams"] = favored
            if disfavored:
                self._config_data["disfavored_teams"] = disfavored
            self._config_data["bias_intensity"] = max(1, min(3, intensity))
            return {
                "set": "bias",
                "favored": self._config_data["favored_teams"],
                "disfavored": self._config_data["disfavored_teams"],
                "intensity": self._config_data["bias_intensity"],
            }

        @function_tool
        def set_custom_instructions(instructions: str) -> dict:
            """Set additional custom instructions for the article.

            Args:
                instructions: Any special requirements or notes.
            """
            self._config_data["custom_instructions"] = instructions
            return {"set": "custom_instructions", "value": instructions}

        @function_tool
        def finalize_config() -> dict:
            """Signal that clarification is complete and config is ready.

            Call this when you have gathered enough information to proceed.
            """
            return {"status": "complete", "config": self._config_data}

        return [
            ask_user,
            set_week,
            set_week_range,
            set_voice,
            set_tone,
            set_length,
            add_focus,
            add_focus_teams,
            set_bias,
            set_custom_instructions,
            finalize_config,
        ]

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the clarification agent."""
        team_list = (
            ", ".join(self._team_names[:10])
            if self._team_names
            else "(teams not loaded)"
        )

        return f"""You are a helpful assistant that gathers requirements for a fantasy football article.

Your job is to understand what the user wants and configure the article accordingly.
Ask clarifying questions ONLY when truly necessary - many requests are clear enough to proceed.

## Current Context
- Current week: {self.default_week}
- Teams in league: {team_list}

## When to Ask Questions

Ask questions if:
- The week is ambiguous and matters for the request
- The user mentions a team name that's unclear
- The tone/style is ambiguous (e.g., "funny" could mean snarky or playful)
- There's a specific team they want to highlight but didn't name

DON'T ask questions if:
- The request is clear (e.g., "weekly recap" → use defaults)
- The week is obvious from context or current week is fine
- The style is explicitly stated (e.g., "snarky" → set snark_level=3)

## Interpreting Requests

Common patterns:
- "weekly recap" → standard recap, use defaults
- "snarky recap" → set voice="snarky columnist", snark_level=3
- "roast [team]" → set disfavored_teams=[team], bias_intensity=3
- "power rankings" → add_focus(["standings", "rankings"])
- "deep dive on [team]" → add_focus_teams([team])
- "hype article" → set voice="hype broadcaster", hype_level=3

## Process

1. Analyze the user's request
2. Set obvious config values immediately (don't ask about things you can infer)
3. Ask 1-2 clarifying questions if truly needed
4. Call finalize_config() when ready

Keep it conversational and efficient. Most requests need 0-2 questions.
"""

    async def clarify(self, prompt: str) -> ReportConfig:
        """Run the clarification process and return a ReportConfig.

        Args:
            prompt: The user's initial request.

        Returns:
            A fully configured ReportConfig.
        """
        # Store the prompt as custom instructions
        self._config_data["custom_instructions"] = prompt

        system_prompt = self._build_system_prompt()
        tools = self._build_tools()

        agent = Agent(
            name="clarifier",
            instructions=system_prompt,
            model=self.model,
            tools=tools,
        )

        user_message = f"""User request: "{prompt}"

Analyze this request and configure the article. Ask clarifying questions only if truly necessary.
When you have enough information, call finalize_config().
"""

        # Run the agent
        await Runner.run(agent, user_message)

        # Build the config from collected data
        return self._build_config()

    def _build_config(self) -> ReportConfig:
        """Build a ReportConfig from the collected data."""
        # Build time range
        time_range = TimeRange(
            week_start=self._config_data["week_start"],
            week_end=self._config_data["week_end"],
        )

        # Build tone
        tone = ToneControls(
            snark_level=self._config_data["snark_level"],
            hype_level=self._config_data["hype_level"],
        )

        # Build bias profile if any bias is set
        bias_profile = None
        if self._config_data["favored_teams"] or self._config_data["disfavored_teams"]:
            bias_profile = BiasProfile(
                favored_teams=self._config_data["favored_teams"],
                disfavored_teams=self._config_data["disfavored_teams"],
                intensity=self._config_data["bias_intensity"],
            )

        return ReportConfig(
            time_range=time_range,
            focus_hints=self._config_data["focus_hints"],
            avoid_topics=self._config_data["avoid_topics"],
            focus_teams=self._config_data["focus_teams"],
            voice=self._config_data["voice"],
            tone=tone,
            bias_profile=bias_profile,
            length_target=self._config_data["length_target"],
            custom_instructions=self._config_data["custom_instructions"],
        )
