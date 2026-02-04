#!/usr/bin/env python3
"""Quick script to generate a weekly recap."""

import asyncio
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datalayer.sleeper_data import SleeperLeagueData
from reporter.agent.specs import ArticleRequest
from reporter.agent.workflows import run_article_request_async


async def main():
    """Generate a weekly recap."""
    # Get week from command line or default to current
    week = int(sys.argv[1]) if len(sys.argv) > 1 else None

    print("Loading league data...")
    data = SleeperLeagueData()
    data.load()

    # Get effective week if not specified
    if week is None:
        context = data.conn.execute(
            "SELECT effective_week FROM season_context LIMIT 1"
        ).fetchone()
        week = context[0] if context else 1
        print(f"Using current week: {week}")

    print(f"Generating weekly recap for week {week}...")

    request = ArticleRequest(
        raw_request=f"Weekly recap for week {week}",
        preset="weekly_recap",
        week=week,
        overrides={
            "tone_controls": {
                "snark_level": 1,
                "hype_level": 2,
                "seriousness": 1,
            }
        },
    )

    output = await run_article_request_async(request, data)

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


if __name__ == "__main__":
    asyncio.run(main())
