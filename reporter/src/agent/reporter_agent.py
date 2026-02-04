"""Reporter agent definition using the OpenAI Agents SDK."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents import Agent, Runner

from datalayer.sleeper_data import SleeperLeagueData

from agent.specs import ReportSpec, ArticleRequest, get_preset, WEEKLY_RECAP_PRESET
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
from tools.sleeper_tools import SleeperToolAdapter, TOOL_DOCS
from tools.registry import create_tool_registry


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_path = prompts_dir / name
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


def build_system_prompt(spec: ReportSpec) -> str:
    """Build the complete system prompt for the agent."""
    parts = [load_prompt("system_base.md")]

    # Add format-specific prompt
    format_map = {
        "weekly_recap": "formats/weekly_recap.md",
        "power_rankings": "formats/power_rankings.md",
        "team_deep_dive": "formats/team_deep_dive.md",
        "playoff_reaction": "formats/playoff_reaction.md",
    }
    format_prompt = format_map.get(spec.article_type.value)
    if format_prompt:
        parts.append(load_prompt(format_prompt))

    # Add style prompt based on tone
    if spec.tone_controls.snark_level >= 2:
        parts.append(load_prompt("styles/snarky_columnist.md"))
    elif spec.tone_controls.hype_level >= 2:
        parts.append(load_prompt("styles/hype_man.md"))
    else:
        parts.append(load_prompt("styles/straight_news.md"))

    # Add bias rules if bias is configured
    if spec.bias_profile and (
        spec.bias_profile.favored_teams or spec.bias_profile.disfavored_teams
    ):
        parts.append(load_prompt("bias/bias_rules.md"))

    return "\n\n---\n\n".join(parts)


class ReporterAgent:
    """The fantasy football reporter agent.

    Implements a simplified workflow:
    1. Gather data using tools directly
    2. Build a brief from the data
    3. Draft article from the brief
    """

    def __init__(
        self,
        data: SleeperLeagueData,
        *,
        model: str = "gpt-4o",
    ):
        self.data = data
        self.model = model
        self.adapter = SleeperToolAdapter(data)
        self.tools = create_tool_registry(self.adapter)

    def synthesize_spec(self, request: ArticleRequest) -> ReportSpec:
        """Convert a user request into a ReportSpec."""
        if request.preset:
            base_spec = get_preset(request.preset)
            if base_spec:
                spec_dict = base_spec.model_dump()
            else:
                spec_dict = WEEKLY_RECAP_PRESET.model_dump()
        else:
            spec_dict = WEEKLY_RECAP_PRESET.model_dump()

        if request.week:
            spec_dict["time_range"] = {
                "week_start": request.week,
                "week_end": request.week,
            }

        for key, value in request.overrides.items():
            if key in spec_dict:
                spec_dict[key] = value

        return ReportSpec.model_validate(spec_dict)

    def gather_data(self, spec: ReportSpec) -> dict[str, Any]:
        """Gather all necessary data for the article type."""
        week = spec.time_range.week_end
        data = {}

        if spec.article_type.value == "weekly_recap":
            # Get comprehensive week data
            data["snapshot"] = self.adapter.call("get_league_snapshot", week=week)
            data["games"] = self.adapter.call("get_week_games", week=week)
            data["leaderboard"] = self.adapter.call(
                "get_week_player_leaderboard", week=week, limit=10
            )
            data["transactions"] = self.adapter.call(
                "get_transactions", week_from=week, week_to=week
            )

        elif spec.article_type.value == "power_rankings":
            data["snapshot"] = self.adapter.call("get_league_snapshot", week=week)
            # Get dossiers for all teams
            if data["snapshot"].get("standings"):
                data["team_dossiers"] = []
                for team in data["snapshot"]["standings"][:12]:  # Limit to 12 teams
                    roster_id = team.get("roster_id")
                    if roster_id:
                        dossier = self.adapter.call(
                            "get_team_dossier", roster_key=str(roster_id), week=week
                        )
                        data["team_dossiers"].append(dossier)

        elif spec.article_type.value == "team_deep_dive":
            if spec.focus_teams:
                team = spec.focus_teams[0]
                data["dossier"] = self.adapter.call(
                    "get_team_dossier", roster_key=team, week=week
                )
                data["schedule"] = self.adapter.call(
                    "get_team_schedule", roster_key=team
                )
                data["roster"] = self.adapter.call(
                    "get_roster_current", roster_key=team
                )
                data["transactions"] = self.adapter.call(
                    "get_team_transactions",
                    roster_key=team,
                    week_from=1,
                    week_to=week,
                )

        elif spec.article_type.value == "playoff_reaction":
            data["games"] = self.adapter.call("get_week_games", week=week)
            data["games_with_players"] = self.adapter.call(
                "get_week_games_with_players", week=week
            )

        return data

    def build_brief(self, spec: ReportSpec, data: dict[str, Any]) -> ReportBrief:
        """Build a ReportBrief from gathered data."""
        week = spec.time_range.week_end
        facts = []
        storylines = []
        fact_id = 0

        # Extract facts from snapshot
        snapshot = data.get("snapshot", {})
        if snapshot.get("standings"):
            for team in snapshot["standings"]:
                fact_id += 1
                facts.append(Fact(
                    id=f"fact_{fact_id:03d}",
                    claim_text=f"{team.get('team_name', 'Team')} is {team.get('wins', 0)}-{team.get('losses', 0)}",
                    data_refs=["get_league_snapshot"],
                    numbers={
                        "wins": float(team.get("wins", 0)),
                        "losses": float(team.get("losses", 0)),
                        "points_for": float(team.get("points_for", 0)),
                    },
                    category="standing",
                ))

        # Extract facts from games
        games = data.get("games", [])
        for game in games:
            fact_id += 1
            team_a = game.get("team_a", "Team A")
            team_b = game.get("team_b", "Team B")
            score_a = game.get("points_a", 0)
            score_b = game.get("points_b", 0)
            winner = game.get("winner", team_a if score_a > score_b else team_b)

            facts.append(Fact(
                id=f"fact_{fact_id:03d}",
                claim_text=f"{team_a} vs {team_b}: {score_a:.1f}-{score_b:.1f}, {winner} wins",
                data_refs=["get_week_games"],
                numbers={
                    "team_a_points": float(score_a),
                    "team_b_points": float(score_b),
                    "margin": abs(float(score_a) - float(score_b)),
                },
                category="score",
            ))

            # Create storylines for notable games
            margin = abs(score_a - score_b)
            if margin > 40:
                storylines.append(Storyline(
                    id=f"story_{len(storylines)+1:03d}",
                    headline=f"{winner} Dominates",
                    summary=f"{winner} won by {margin:.1f} points in a blowout victory.",
                    supporting_fact_ids=[f"fact_{fact_id:03d}"],
                    priority=1,
                    tags=["blowout"],
                ))
            elif margin < 5:
                storylines.append(Storyline(
                    id=f"story_{len(storylines)+1:03d}",
                    headline="Nail-Biter Alert",
                    summary=f"{winner} edges out opponent by just {margin:.1f} points.",
                    supporting_fact_ids=[f"fact_{fact_id:03d}"],
                    priority=1,
                    tags=["close_game"],
                ))

        # Extract facts from leaderboard
        leaderboard = data.get("leaderboard", [])
        for i, player in enumerate(leaderboard[:5]):
            fact_id += 1
            facts.append(Fact(
                id=f"fact_{fact_id:03d}",
                claim_text=f"{player.get('player_name', 'Player')} scored {player.get('points', 0):.1f} points",
                data_refs=["get_week_player_leaderboard"],
                numbers={"points": float(player.get("points", 0))},
                category="player",
            ))

        # Build outline based on article type
        outline = []
        if spec.article_type.value == "weekly_recap":
            outline = [
                Section(
                    title="Introduction",
                    bullet_points=["Week summary hook", "Key storylines"],
                    required_fact_ids=[],
                    storyline_ids=[s.id for s in storylines[:2]],
                ),
                Section(
                    title="Matchup Highlights",
                    bullet_points=["Cover all games", "Highlight close games and blowouts"],
                    required_fact_ids=[f.id for f in facts if f.category == "score"],
                    storyline_ids=[],
                ),
                Section(
                    title="Standings",
                    bullet_points=["Current standings", "Playoff implications"],
                    required_fact_ids=[f.id for f in facts if f.category == "standing"][:5],
                    storyline_ids=[],
                ),
                Section(
                    title="Top Performers",
                    bullet_points=["Week's best players"],
                    required_fact_ids=[f.id for f in facts if f.category == "player"],
                    storyline_ids=[],
                ),
            ]

        # Get league name from snapshot
        league_name = "Fantasy League"
        if snapshot.get("league"):
            league_name = snapshot["league"].get("name", league_name)

        return ReportBrief(
            meta=BriefMeta(
                league_name=league_name,
                league_id=self.data.league_id,
                week_start=spec.time_range.week_start,
                week_end=spec.time_range.week_end,
                article_type=spec.article_type.value,
            ),
            facts=facts,
            storylines=storylines,
            outline=outline,
            style=ResolvedStyle(
                voice=spec.genre_voice,
                pacing="moderate",
                humor_level=spec.tone_controls.snark_level,
                formality="casual" if spec.tone_controls.snark_level > 1 else "moderate",
            ),
            bias=ResolvedBias(
                favored_teams=spec.bias_profile.favored_teams if spec.bias_profile else [],
                disfavored_teams=spec.bias_profile.disfavored_teams if spec.bias_profile else [],
                intensity=spec.bias_profile.intensity if spec.bias_profile else 0,
            ),
        )

    async def draft(self, spec: ReportSpec, brief: ReportBrief) -> str:
        """Execute the draft phase to write the article."""
        system_prompt = build_system_prompt(spec)

        # Build a detailed draft prompt with all the data
        draft_prompt = f"""
Write a {spec.article_type.value.replace('_', ' ')} article for Week {spec.time_range.week_end}.

## League: {brief.meta.league_name}

## Style Guidelines
- Voice: {brief.style.voice}
- Humor level: {brief.style.humor_level}/3
- Target length: {spec.length_target} words

## Facts (USE THESE EXACTLY - do not invent statistics)
{self._format_facts(brief.facts)}

## Storylines to Weave In
{self._format_storylines(brief.storylines)}

## Article Outline
{self._format_outline(brief.outline)}

{self._format_bias_instructions(spec)}

Write the article in Markdown format. Use the exact numbers from the facts above.
Do NOT make up any statistics - only use what's provided.
"""

        # Create draft agent WITHOUT tools
        draft_agent = Agent(
            name="writer",
            instructions=system_prompt,
            model=self.model,
            tools=[],
        )

        result = await Runner.run(draft_agent, draft_prompt)
        return result.final_output

    def _format_facts(self, facts: list[Fact]) -> str:
        """Format facts for the prompt."""
        if not facts:
            return "No facts available."
        lines = []
        for f in facts:
            lines.append(f"- [{f.category}] {f.claim_text}")
        return "\n".join(lines)

    def _format_storylines(self, storylines: list[Storyline]) -> str:
        """Format storylines for the prompt."""
        if not storylines:
            return "No specific storylines identified."
        lines = []
        for s in storylines:
            lines.append(f"- **{s.headline}** (priority {s.priority}): {s.summary}")
        return "\n".join(lines)

    def _format_outline(self, outline: list[Section]) -> str:
        """Format outline for the prompt."""
        if not outline:
            return "Use standard article structure."
        lines = []
        for section in outline:
            lines.append(f"### {section.title}")
            for bullet in section.bullet_points:
                lines.append(f"  - {bullet}")
        return "\n".join(lines)

    def _format_bias_instructions(self, spec: ReportSpec) -> str:
        """Format bias instructions if configured."""
        if not spec.bias_profile:
            return ""
        if not spec.bias_profile.favored_teams and not spec.bias_profile.disfavored_teams:
            return ""

        lines = ["## Bias Instructions"]
        intensity = spec.bias_profile.intensity

        if spec.bias_profile.favored_teams:
            teams = ", ".join(spec.bias_profile.favored_teams)
            if intensity == 1:
                lines.append(f"- Use positive language when describing {teams}")
            elif intensity == 2:
                lines.append(f"- Frame {teams}'s performance enthusiastically")
                lines.append(f"- Lead with {teams}'s positive results")
            elif intensity >= 3:
                lines.append(f"- Celebrate {teams}'s successes with high energy")
                lines.append(f"- Position {teams} as championship contenders")

        if spec.bias_profile.disfavored_teams:
            teams = ", ".join(spec.bias_profile.disfavored_teams)
            if intensity == 1:
                lines.append(f"- Use neutral/brief language for {teams}")
            elif intensity == 2:
                lines.append(f"- Frame {teams}'s losses as expected")
            elif intensity >= 3:
                lines.append(f"- Apply playful roasting to {teams}'s struggles")

        lines.append("- NEVER change actual scores or statistics!")
        return "\n".join(lines)

    async def run(self, request: ArticleRequest) -> ArticleOutput:
        """Execute the full article generation pipeline."""
        # Phase 1: Synthesize spec
        spec = self.synthesize_spec(request)

        # Phase 2: Gather data directly
        self.adapter.clear_log()
        data = self.gather_data(spec)

        # Phase 3: Build brief from data
        brief = self.build_brief(spec, data)

        # Phase 4: Draft article
        article = await self.draft(spec, brief)

        return ArticleOutput(
            article=article,
            spec=spec,
            brief=brief,
            verification=None,
            trace_id=None,
        )
