#!/usr/bin/env python3
"""Quick script to generate a weekly recap using iterative research."""

import asyncio
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datalayer.sleeper_data import SleeperLeagueData
from agent.workflows import generate_report_async


async def main():
    """Generate a weekly recap."""
    # Get week from command line or default to current
    week = int(sys.argv[1]) if len(sys.argv) > 1 else None

    # Get optional style from command line
    snarky = "--snarky" in sys.argv or "-s" in sys.argv

    print("Loading league data...")
    data = SleeperLeagueData()
    data.load()

    # Get effective week if not specified
    if week is None:
        week = data.effective_week
        print(f"Using current week: {week}")

    print(f"Generating {'snarky ' if snarky else ''}weekly recap for week {week}...")
    print("(The agent will research iteratively and build its own brief)")
    print()

    # Use the new generate_report API
    if snarky:
        output = await generate_report_async(
            f"Write a snarky, entertaining recap of week {week}. "
            "Be witty and roast teams that underperformed.",
            week=week,
            data=data,
            voice="snarky columnist",
            snark_level=3,
            hype_level=1,
        )
    else:
        output = await generate_report_async(
            f"Write a comprehensive weekly recap for week {week}. "
            "Cover the major storylines, notable games, top performers, "
            "and any important transactions.",
            week=week,
            data=data,
            snark_level=1,
            hype_level=2,
        )

    print("\n" + "=" * 60)
    print(output.article)
    print("=" * 60)

    # Save output
    output_dir = Path(".output")
    output_dir.mkdir(exist_ok=True)

    article_path = output_dir / f"recap_week{week}.md"
    article_path.write_text(output.article)
    print(f"\nArticle saved to: {article_path}")

    brief_path = output_dir / f"recap_week{week}.brief.json"
    brief_path.write_text(output.brief.model_dump_json(indent=2))
    print(f"Brief saved to: {brief_path}")

    # Save research log
    if output.research_log:
        log_path = output_dir / f"recap_week{week}.research_log.md"
        log_path.write_text(output.research_log.to_markdown())
        print(f"Research log saved to: {log_path}")

        # Print summary
        print(f"\nResearch Summary:")
        print(f"  - Tool calls: {output.research_log.tool_calls}")
        print(f"  - Findings recorded: {output.research_log.findings_recorded}")
        print(f"  - Storylines noted: {output.research_log.storylines_noted}")


if __name__ == "__main__":
    asyncio.run(main())
