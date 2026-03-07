"""Storyline curator — filters storylines by relevance before research."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agents import Agent, Runner, AgentOutputSchema

from reporter.agent.config import ReportConfig
from reporter.agent.schemas import CuratedContext


def _load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / name
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


class StorylineCurator:
    """Selects relevant storylines for a given article request.

    Single structured-output LLM call — no tools, no agent loop.
    """

    def __init__(self, *, model: str = "gpt-5-mini"):
        self.model = model

    async def curate(
        self,
        config: ReportConfig,
        storyline_summaries: list[dict],
        *,
        week_data: dict | None = None,
    ) -> CuratedContext:
        if not storyline_summaries and not week_data:
            return CuratedContext(
                relevant_storyline_ids=[],
                new_storyline_candidates=[],
                reasoning="No storylines or week data to curate.",
            )

        system_prompt = _load_prompt("curator.md")
        user_prompt = self._build_user_prompt(
            config, storyline_summaries, week_data=week_data
        )

        agent = Agent(
            name="storyline_curator",
            instructions=system_prompt,
            model=self.model,
            tools=[],
            output_type=AgentOutputSchema(CuratedContext, strict_json_schema=False),
        )

        result = await Runner.run(agent, user_prompt)
        return result.final_output

    @staticmethod
    def _build_user_prompt(
        config: ReportConfig,
        storyline_summaries: list[dict],
        *,
        week_data: dict | None = None,
    ) -> str:
        lines = [
            "## Article Request",
            "",
            f"**Week(s):** {config.time_range.week_start}"
            + (
                f"-{config.time_range.week_end}"
                if config.time_range.week_start != config.time_range.week_end
                else ""
            ),
            f"**Voice:** {config.voice}",
        ]

        if config.focus_hints:
            lines.append(f"**Focus areas:** {', '.join(config.focus_hints)}")
        if config.focus_teams:
            lines.append(f"**Focus teams:** {', '.join(config.focus_teams)}")
        if config.custom_instructions:
            lines.append(f"**Instructions:** {config.custom_instructions}")

        lines.extend(["", "## Existing Storylines", ""])

        for s in storyline_summaries:
            tags = ", ".join(s.get("tags", []))
            teams = ", ".join(str(t) for t in s.get("team_ids", []))
            lines.append(
                f"- **[{s['id']}]** (priority {s['priority']}, {s['status']}) "
                f"{s['headline']}: {s['summary']}"
            )
            if tags:
                lines.append(f"  Tags: {tags}")
            if teams:
                lines.append(f"  Teams: {teams}")

        data_section = StorylineCurator._format_week_data(week_data)
        if data_section:
            lines.extend(["", data_section])

        lines.extend([
            "",
            "Select the storylines relevant to this article request and suggest "
            "any new storyline candidates based on the request.",
        ])

        return "\n".join(lines)

    @staticmethod
    def _format_week_data(week_data: dict | None) -> str:
        if not week_data:
            return ""

        sections: list[str] = []

        # Scores
        games = week_data.get("games", [])
        if games:
            score_lines = ["### Scores"]
            for g in games:
                winner = g.get("winner", "")
                score_lines.append(
                    f"- {g['team_a']} {g['points_a']} vs {g['team_b']} {g['points_b']}"
                    f" (winner: {winner})"
                )
            sections.append("\n".join(score_lines))

        # Standings
        standings_data = week_data.get("standings")
        if standings_data and standings_data.get("standings"):
            standing_lines = ["### Standings"]
            for s in standings_data["standings"]:
                record = s.get("record", f"{s['wins']}-{s['losses']}")
                pf = s.get("points_for", 0)
                standing_lines.append(
                    f"- {s.get('rank', '?')}. {s['team_name']} ({record}, {pf} PF)"
                )
            sections.append("\n".join(standing_lines))

        # Top Performers
        performers = week_data.get("top_performers", [])
        if performers:
            perf_lines = ["### Top Performers"]
            for p in performers:
                perf_lines.append(
                    f"- {p['player_name']} ({p['position']}, {p['team_name']}): {p['points']} pts"
                )
            sections.append("\n".join(perf_lines))

        # Transactions
        transactions = week_data.get("transactions", [])
        if transactions:
            tx_lines = ["### Transactions"]
            for tx in transactions:
                tx_type = tx.get("type", "unknown")
                details = tx.get("details", [])
                if tx_type == "trade" and len(details) >= 2:
                    teams = [d["team_name"] for d in details]
                    tx_lines.append(f"- trade: {teams[0]} \u2194 {teams[1]}")
                elif details:
                    team = details[0].get("team_name", "?")
                    received = details[0].get("assets_received", [])
                    player_names = [
                        a["player_name"]
                        for a in received
                        if a.get("player_name")
                    ]
                    if player_names:
                        tx_lines.append(
                            f"- {tx_type}: {team} added {', '.join(player_names)}"
                        )
                    else:
                        tx_lines.append(f"- {tx_type}: {team}")
            sections.append("\n".join(tx_lines))

        if not sections:
            return ""

        return "## This Week's Data\n\n" + "\n\n".join(sections)
