"""CLI runner for the reporter agent."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from datalayer.sleeper_data import SleeperLeagueData

from reporter.agent.clarify import ClarificationAgent
from reporter.agent.reporter_agent import ReporterAgent
from reporter.app.config import load_config


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="AI Fantasy Football Reporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  reporter "weekly recap"
  reporter "snarky recap, roast Team Taco" --week 8
  reporter "power rankings with analysis"
  reporter "deep dive on Team Taco's season"
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
        "--model",
        default=None,
        help="Model to use (default: from config or gpt-5-mini)",
    )

    return parser.parse_args()


async def run(prompt: str, week: Optional[int] = None, config=None) -> None:
    """Run the reporter agent flow."""
    print()
    print("=" * 60)
    print("  Fantasy Football Reporter Agent")
    print("=" * 60)
    print()

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
    print()
    print("--- Clarification ---")
    print()
    print(f"Your request: {prompt}")
    print()

    model = config.model if config else "gpt-5-mini"
    clarify_agent = ClarificationAgent(data, default_week=week, model=model)
    report_config = await clarify_agent.clarify(prompt)

    # Show the resolved config
    print()
    print("--- Resolved Configuration ---")
    print()
    print(f"  Week(s): {report_config.time_range.week_start}", end="")
    if report_config.time_range.week_start != report_config.time_range.week_end:
        print(f"-{report_config.time_range.week_end}")
    else:
        print()
    print(f"  Voice: {report_config.voice}")
    print(f"  Tone: snark={report_config.tone.snark_level}, hype={report_config.tone.hype_level}")
    print(f"  Length: ~{report_config.length_target} words")
    if report_config.focus_hints:
        print(f"  Focus: {', '.join(report_config.focus_hints)}")
    if report_config.focus_teams:
        print(f"  Teams: {', '.join(report_config.focus_teams)}")
    if report_config.bias_profile:
        if report_config.bias_profile.favored_teams:
            print(f"  Favor: {', '.join(report_config.bias_profile.favored_teams)}")
        if report_config.bias_profile.disfavored_teams:
            print(f"  Roast: {', '.join(report_config.bias_profile.disfavored_teams)}")

    # Confirm before proceeding
    print()
    confirm = input("Proceed with research? [Y/n] ").strip().lower()
    if confirm and confirm not in ("y", "yes"):
        print("Aborted.")
        return

    # Phase 2: Research + Draft
    print()
    print("--- Research Phase ---")
    print()

    # Set up streaming log file
    output_dir = config.output_dir if config else Path(".output")
    output_dir.mkdir(exist_ok=True)

    week_str = f"week{report_config.time_range.week_start}"
    if report_config.time_range.week_start != report_config.time_range.week_end:
        week_str = f"weeks{report_config.time_range.week_start}-{report_config.time_range.week_end}"

    log_path = output_dir / f"research_{week_str}.stream.log"

    print("The agent is now researching your league data...")
    print()
    print(f"Streaming research log to: {log_path}")
    print(f"  Run in another terminal: tail -f {log_path}")
    print()

    reporter = ReporterAgent(data, model=model)
    output = await reporter.run_with_config(report_config, log_path=log_path)

    # Show research summary
    if output.research_log:
        print(f"Research complete:")
        print(f"  - Tool calls: {output.research_log.tool_calls}")
        print(f"  - Reasoning entries: {output.research_log.reasoning_entries}")

    # Phase 3: Show article
    print()
    print("--- Generated Article ---")
    print()
    print(output.article)

    # Save outputs
    print()
    print("--- Saving Outputs ---")
    print()

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


def main() -> None:
    """Main entry point."""
    args = parse_args()

    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    # Get prompt interactively if not provided
    prompt = args.prompt
    if not prompt:
        print()
        print("=" * 60)
        print("  Fantasy Football Reporter Agent")
        print("=" * 60)
        print()
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

    asyncio.run(run(prompt, args.week, config))


if __name__ == "__main__":
    main()
