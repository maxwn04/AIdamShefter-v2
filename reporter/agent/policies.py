"""Policies for tool use, bias constraints, and evidence checking."""

from __future__ import annotations

from typing import Any

from reporter.agent.specs import EvidencePolicy, ReportSpec
from reporter.agent.schemas import ReportBrief, Fact


def check_fact_grounding(
    claim: str,
    numbers: dict[str, float],
    brief: ReportBrief,
    policy: EvidencePolicy,
) -> tuple[bool, str | None]:
    """Check if a claim is properly grounded in the brief.

    Args:
        claim: The claim text from the article.
        numbers: Extracted numbers from the claim.
        brief: The ReportBrief to check against.
        policy: The evidence policy to apply.

    Returns:
        Tuple of (is_grounded, error_message or None).
    """
    if policy == EvidencePolicy.RELAXED:
        # Only check major numbers
        major_keys = {"score", "points", "wins", "losses", "record"}
        numbers_to_check = {k: v for k, v in numbers.items() if k in major_keys}
    else:
        numbers_to_check = numbers

    for key, value in numbers_to_check.items():
        found = False
        for fact in brief.facts:
            if key in fact.numbers and abs(fact.numbers[key] - value) < 0.01:
                found = True
                break
        if not found and policy == EvidencePolicy.STRICT:
            return False, f"Number {key}={value} not found in brief facts"

    return True, None


def get_bias_framing_rules(spec: ReportSpec) -> list[str]:
    """Generate framing rules based on bias configuration.

    Args:
        spec: The ReportSpec with bias settings.

    Returns:
        List of framing rules to include in prompts.
    """
    rules = []

    if not spec.bias_profile:
        return rules

    intensity = spec.bias_profile.intensity
    if intensity == 0:
        return rules

    # Favored teams
    for team in spec.bias_profile.favored_teams:
        if intensity == 1:
            rules.append(f"Use positive word choices when describing {team}'s performance")
        elif intensity == 2:
            rules.append(
                f"Frame {team}'s wins enthusiastically and their losses sympathetically"
            )
            rules.append(f"Lead sections with {team}'s positive results when relevant")
        elif intensity == 3:
            rules.append(f"Celebrate {team}'s successes with high energy")
            rules.append(f"Frame any {team} struggles as temporary setbacks")
            rules.append(f"Position {team} as a championship contender")

    # Disfavored teams
    for team in spec.bias_profile.disfavored_teams:
        if intensity == 1:
            rules.append(f"Use neutral language for {team}'s performance")
        elif intensity == 2:
            rules.append(f"Be brief when covering {team}'s wins")
            rules.append(f"Frame {team}'s losses as expected outcomes")
        elif intensity == 3:
            rules.append(f"Apply playful roasting to {team}'s struggles")
            rules.append(f"Question {team}'s long-term prospects")
            rules.append(f"Use dismissive language for {team}'s victories")

    # Always add the boundary rule
    rules.append(
        "NEVER change actual scores, statistics, or records regardless of bias"
    )

    return rules


def validate_tool_call_phase(
    tool_name: str,
    phase: str,
) -> tuple[bool, str | None]:
    """Validate that a tool call is allowed in the current phase.

    Args:
        tool_name: Name of the tool being called.
        phase: Current workflow phase (research, draft, verify).

    Returns:
        Tuple of (is_allowed, error_message or None).
    """
    if phase == "draft":
        return False, f"Tool calls not allowed during drafting phase: {tool_name}"

    if phase == "verify":
        # Only allow limited verification tools
        allowed = {"get_team_game", "get_week_games", "run_sql"}
        if tool_name not in allowed:
            return False, f"Tool {tool_name} not allowed during verification"

    return True, None


def extract_numbers_from_text(text: str) -> dict[str, float]:
    """Extract numeric values from article text.

    This is a simple extraction for verification purposes.
    """
    import re

    numbers = {}

    # Score patterns (e.g., "142.3-98.7", "142.3 points")
    score_pattern = r"(\d+\.?\d*)\s*[-to]+\s*(\d+\.?\d*)"
    for match in re.finditer(score_pattern, text):
        numbers[f"score_a_{len(numbers)}"] = float(match.group(1))
        numbers[f"score_b_{len(numbers)}"] = float(match.group(2))

    # Point patterns (e.g., "142.3 points")
    point_pattern = r"(\d+\.?\d*)\s*points?"
    for match in re.finditer(point_pattern, text, re.IGNORECASE):
        numbers[f"points_{len(numbers)}"] = float(match.group(1))

    # Record patterns (e.g., "7-1", "5-3-1")
    record_pattern = r"\((\d+)-(\d+)(?:-(\d+))?\)"
    for match in re.finditer(record_pattern, text):
        idx = len(numbers)
        numbers[f"wins_{idx}"] = float(match.group(1))
        numbers[f"losses_{idx}"] = float(match.group(2))
        if match.group(3):
            numbers[f"ties_{idx}"] = float(match.group(3))

    return numbers
