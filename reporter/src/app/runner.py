"""CLI runner for the reporter agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from datalayer.sleeper_data import SleeperLeagueData

from agent.specs import ArticleRequest
from agent.workflows import run_article_request_async
from app.config import load_config, STYLE_PRESETS


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="AI Fantasy Football Reporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate weekly recap for week 8
  reporter recap 8

  # Generate with snarky style
  reporter recap 8 --style snarky

  # Generate with bias
  reporter recap 8 --favor "Team Taco" --roast "The Waiver Wire"

  # Generate power rankings
  reporter rankings 8

  # Custom request
  reporter custom "Write a noir detective style recap of week 8"
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Recap command
    recap = subparsers.add_parser("recap", help="Generate weekly recap")
    recap.add_argument("week", type=int, help="Week number")
    recap.add_argument(
        "--style",
        choices=list(STYLE_PRESETS.keys()),
        default="straight",
        help="Writing style preset",
    )
    recap.add_argument(
        "--favor",
        action="append",
        dest="favored_teams",
        help="Teams to favor (can specify multiple)",
    )
    recap.add_argument(
        "--roast",
        action="append",
        dest="disfavored_teams",
        help="Teams to roast (can specify multiple)",
    )
    recap.add_argument(
        "--bias-intensity",
        type=int,
        choices=[0, 1, 2, 3],
        default=2,
        help="Bias intensity (0=none, 3=heavy)",
    )
    recap.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file path (default: .output/recap_weekN.md)",
    )

    # Rankings command
    rankings = subparsers.add_parser("rankings", help="Generate power rankings")
    rankings.add_argument("week", type=int, help="Week number")
    rankings.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file path",
    )

    # Team deep dive command
    team = subparsers.add_parser("team", help="Generate team deep dive")
    team.add_argument("team_name", help="Team name to focus on")
    team.add_argument("week", type=int, help="Current week for context")
    team.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file path",
    )

    # Custom command
    custom = subparsers.add_parser("custom", help="Custom article request")
    custom.add_argument("request", help="Natural language request")
    custom.add_argument("--week", type=int, help="Target week")
    custom.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file path",
    )

    # Global options
    parser.add_argument(
        "--model",
        default=None,
        help="Model to use (default: from config or gpt-4o)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save output files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full ArticleOutput as JSON",
    )

    return parser.parse_args()


def save_output(
    article: str,
    brief_json: str,
    spec_json: str,
    output_path: Path,
) -> None:
    """Save article and metadata to files."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save article
    output_path.write_text(article)
    print(f"Article saved to: {output_path}")

    # Save brief
    brief_path = output_path.with_suffix(".brief.json")
    brief_path.write_text(brief_json)
    print(f"Brief saved to: {brief_path}")

    # Save spec
    spec_path = output_path.with_suffix(".spec.json")
    spec_path.write_text(spec_json)
    print(f"Spec saved to: {spec_path}")


async def run_recap(args: argparse.Namespace, config) -> None:
    """Run the weekly recap command."""
    print(f"Generating weekly recap for week {args.week}...")

    # Build overrides from style preset
    style = STYLE_PRESETS[args.style]
    overrides = {"tone_controls": style}

    # Add bias if specified
    if args.favored_teams or args.disfavored_teams:
        overrides["bias_profile"] = {
            "favored_teams": args.favored_teams or [],
            "disfavored_teams": args.disfavored_teams or [],
            "intensity": args.bias_intensity,
        }

    request = ArticleRequest(
        raw_request=f"Weekly recap for week {args.week}",
        preset="weekly_recap",
        week=args.week,
        overrides=overrides,
    )

    # Load data
    print("Loading league data...")
    data = SleeperLeagueData()
    data.load()

    # Run the workflow
    model = args.model or config.model
    output = await run_article_request_async(request, data, model=model)

    # Output results
    if args.json:
        print(output.model_dump_json(indent=2))
    else:
        print("\n" + "=" * 60)
        print(output.article)
        print("=" * 60 + "\n")

    # Save if requested
    if not args.no_save:
        output_path = args.output or config.output_dir / f"recap_week{args.week}.md"
        save_output(
            output.article,
            output.brief.model_dump_json(indent=2),
            output.spec.model_dump_json(indent=2),
            output_path,
        )


async def run_rankings(args: argparse.Namespace, config) -> None:
    """Run the power rankings command."""
    print(f"Generating power rankings after week {args.week}...")

    request = ArticleRequest(
        raw_request=f"Power rankings after week {args.week}",
        preset="power_rankings",
        week=args.week,
    )

    # Load data
    print("Loading league data...")
    data = SleeperLeagueData()
    data.load()

    # Run the workflow
    model = args.model or config.model
    output = await run_article_request_async(request, data, model=model)

    # Output results
    if args.json:
        print(output.model_dump_json(indent=2))
    else:
        print("\n" + "=" * 60)
        print(output.article)
        print("=" * 60 + "\n")

    # Save if requested
    if not args.no_save:
        output_path = args.output or config.output_dir / f"rankings_week{args.week}.md"
        save_output(
            output.article,
            output.brief.model_dump_json(indent=2),
            output.spec.model_dump_json(indent=2),
            output_path,
        )


async def run_team_dive(args: argparse.Namespace, config) -> None:
    """Run the team deep dive command."""
    print(f"Generating deep dive for {args.team_name}...")

    request = ArticleRequest(
        raw_request=f"Deep dive on {args.team_name}",
        preset="team_deep_dive",
        week=args.week,
        overrides={"focus_teams": [args.team_name]},
    )

    # Load data
    print("Loading league data...")
    data = SleeperLeagueData()
    data.load()

    # Run the workflow
    model = args.model or config.model
    output = await run_article_request_async(request, data, model=model)

    # Output results
    if args.json:
        print(output.model_dump_json(indent=2))
    else:
        print("\n" + "=" * 60)
        print(output.article)
        print("=" * 60 + "\n")

    # Save if requested
    if not args.no_save:
        safe_name = args.team_name.lower().replace(" ", "_")
        output_path = args.output or config.output_dir / f"team_{safe_name}.md"
        save_output(
            output.article,
            output.brief.model_dump_json(indent=2),
            output.spec.model_dump_json(indent=2),
            output_path,
        )


async def run_custom(args: argparse.Namespace, config) -> None:
    """Run a custom article request."""
    print(f"Processing custom request...")

    request = ArticleRequest(
        raw_request=args.request,
        week=args.week,
    )

    # Load data
    print("Loading league data...")
    data = SleeperLeagueData()
    data.load()

    # Run the workflow
    model = args.model or config.model
    output = await run_article_request_async(request, data, model=model)

    # Output results
    if args.json:
        print(output.model_dump_json(indent=2))
    else:
        print("\n" + "=" * 60)
        print(output.article)
        print("=" * 60 + "\n")

    # Save if requested
    if not args.no_save:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = args.output or config.output_dir / f"custom_{timestamp}.md"
        save_output(
            output.article,
            output.brief.model_dump_json(indent=2),
            output.spec.model_dump_json(indent=2),
            output_path,
        )


def main() -> None:
    """Main entry point."""
    args = parse_args()

    if not args.command:
        print("Error: No command specified. Use --help for usage.")
        sys.exit(1)

    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    # Route to appropriate handler
    if args.command == "recap":
        asyncio.run(run_recap(args, config))
    elif args.command == "rankings":
        asyncio.run(run_rankings(args, config))
    elif args.command == "team":
        asyncio.run(run_team_dive(args, config))
    elif args.command == "custom":
        asyncio.run(run_custom(args, config))
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
