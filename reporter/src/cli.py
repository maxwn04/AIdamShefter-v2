#!/usr/bin/env python3
"""Interactive CLI for the fantasy football reporter agent."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

from datalayer.sleeper_data import SleeperLeagueData

from agent.config import ReportConfig, TimeRange, ToneControls, BiasProfile
from agent.clarify import ClarificationAgent
from agent.reporter_agent import ReporterAgent


def print_header():
    """Print the CLI header."""
    print()
    print("=" * 60)
    print("  Fantasy Football Reporter Agent")
    print("  Iterative research-driven article generation")
    print("=" * 60)
    print()


def print_section(title: str):
    """Print a section header."""
    print()
    print(f"--- {title} ---")
    print()


async def run_interactive(prompt: str, week: Optional[int] = None):
    """Run the interactive reporter flow."""
    print_header()

    # Load data
    print("Loading league data...")
    data = SleeperLeagueData()
    data.load()

    # Get current week if not specified
    if week is None:
        week = data.effective_week

    print(f"League: {data.league_id}")
    print(f"Current week: {week}")

    # Phase 1: Clarification
    print_section("Clarification")
    print(f"Your request: {prompt}")
    print()

    clarify_agent = ClarificationAgent(data, default_week=week)
    config = await clarify_agent.clarify(prompt)

    # Show the resolved config
    print_section("Resolved Configuration")
    print(f"  Week(s): {config.time_range.week_start}", end="")
    if config.time_range.week_start != config.time_range.week_end:
        print(f"-{config.time_range.week_end}")
    else:
        print()
    print(f"  Voice: {config.voice}")
    print(f"  Tone: snark={config.tone.snark_level}, hype={config.tone.hype_level}")
    print(f"  Length: ~{config.length_target} words")
    if config.focus_hints:
        print(f"  Focus: {', '.join(config.focus_hints)}")
    if config.focus_teams:
        print(f"  Teams: {', '.join(config.focus_teams)}")
    if config.bias_profile:
        if config.bias_profile.favored_teams:
            print(f"  Favor: {', '.join(config.bias_profile.favored_teams)}")
        if config.bias_profile.disfavored_teams:
            print(f"  Roast: {', '.join(config.bias_profile.disfavored_teams)}")

    # Confirm before proceeding
    print()
    confirm = input("Proceed with research? [Y/n] ").strip().lower()
    if confirm and confirm not in ("y", "yes"):
        print("Aborted.")
        return

    # Phase 2: Research
    print_section("Research Phase")

    # Set up streaming log file
    output_dir = Path(".output")
    output_dir.mkdir(exist_ok=True)

    week_str = f"week{config.time_range.week_start}"
    if config.time_range.week_start != config.time_range.week_end:
        week_str = f"weeks{config.time_range.week_start}-{config.time_range.week_end}"

    log_path = output_dir / f"research_{week_str}.stream.log"

    print("The agent is now researching your league data...")
    print()
    print(f"Streaming research log to: {log_path}")
    print(f"  Run in another terminal: tail -f {log_path}")
    print()

    reporter = ReporterAgent(data)
    output = await reporter.run_with_config(config, log_path=log_path)

    # Show research summary
    if output.research_log:
        print(f"Research complete:")
        print(f"  - Tool calls: {output.research_log.tool_calls}")
        print(f"  - Reasoning entries: {output.research_log.reasoning_entries}")

    # Phase 3: Show article
    print_section("Generated Article")
    print(output.article)

    # Save outputs
    print_section("Saving Outputs")

    article_path = output_dir / f"article_{week_str}.md"
    article_path.write_text(output.article)
    print(f"  Article: {article_path}")

    brief_path = output_dir / f"article_{week_str}.brief.json"
    brief_path.write_text(output.brief.model_dump_json(indent=2))
    print(f"  Brief: {brief_path}")

    if output.research_log:
        final_log_path = output_dir / f"article_{week_str}.research_log.md"
        final_log_path.write_text(output.research_log.to_markdown())
        print(f"  Research log: {final_log_path}")
        print(f"  Stream log: {log_path}")

    print()
    print("Done!")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fantasy Football Reporter - AI-powered article generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "weekly recap"
  %(prog)s "snarky recap, roast Team Taco" --week 8
  %(prog)s "power rankings with analysis"
  %(prog)s "deep dive on the playoff race" --week 12
        """,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="What kind of article do you want? (will prompt if not provided)",
    )
    parser.add_argument(
        "--week",
        "-w",
        type=int,
        help="Week number (defaults to current week)",
    )
    parser.add_argument(
        "--non-interactive",
        "-n",
        action="store_true",
        help="Skip clarifying questions, use defaults",
    )

    args = parser.parse_args()

    # Get prompt if not provided
    prompt = args.prompt
    if not prompt:
        print_header()
        print("What kind of article would you like?")
        print()
        print("Examples:")
        print("  - weekly recap")
        print("  - snarky recap of week 8")
        print("  - power rankings with hot takes")
        print("  - deep dive on Team Taco's season")
        print()
        prompt = input("> ").strip()
        if not prompt:
            print("No prompt provided. Exiting.")
            sys.exit(1)

    # Run the interactive flow
    asyncio.run(run_interactive(prompt, args.week))


if __name__ == "__main__":
    main()
