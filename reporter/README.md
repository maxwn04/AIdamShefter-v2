# AI Fantasy Football Reporter

An AI-powered reporter agent that generates engaging, factually grounded articles about your Sleeper fantasy football league.

## Features

- **Weekly Recaps**: Comprehensive summaries of each week's action
- **Power Rankings**: Ordered team rankings with analysis
- **Team Deep Dives**: In-depth profiles of individual teams
- **Custom Articles**: Natural language requests for any article type

### Style Options

- **Straight**: Professional sports journalism
- **Hype**: High-energy, celebratory coverage
- **Snarky**: Witty, irreverent commentary
- **Savage**: Full roast mode (use responsibly)

### Bias System

Optionally favor or roast specific teams. Bias affects framing only—facts always remain accurate.

## Installation

```bash
# From the reporter directory
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and fill in:

```bash
SLEEPER_LEAGUE_ID=your_league_id
OPENAI_API_KEY=your_openai_key
```

## Usage

### CLI Commands

```bash
# Weekly recap
reporter recap 8

# Snarky weekly recap
reporter recap 8 --style snarky

# Weekly recap favoring a team
reporter recap 8 --favor "Team Taco" --bias-intensity 2

# Power rankings
reporter rankings 8

# Team deep dive
reporter team "Team Taco" 8

# Custom request
reporter custom "Write a noir detective style recap of week 8"
```

### Programmatic Usage

```python
from reporter import run_article_request, ArticleRequest

# Simple request
request = ArticleRequest(
    raw_request="Weekly recap for week 8",
    preset="weekly_recap",
    week=8,
)
output = run_article_request(request)
print(output.article)

# With customization
from reporter.agent.workflows import generate_weekly_recap

output = await generate_weekly_recap(
    week=8,
    snark_level=2,
    favored_teams=["Team Taco"],
    bias_intensity=2,
)
```

## Architecture

The reporter uses a multi-phase workflow:

1. **Spec Synthesis**: Convert user request → `ReportSpec`
2. **Research**: Use datalayer tools → `ReportBrief`
3. **Draft**: Write from brief → Article
4. **Verify** (optional): Cross-check claims

### Key Concepts

- **ReportSpec**: Configuration contract (article type, style, bias)
- **ReportBrief**: Research artifact (facts, storylines, outline)
- **ArticleOutput**: Final output (article + metadata)

## Output Files

Generated articles are saved to `.output/` by default:
- `recap_week8.md` - The article
- `recap_week8.brief.json` - The research brief
- `recap_week8.spec.json` - The resolved spec

## Development

```bash
# Run tests
pytest

# Run a specific test
pytest tests/test_specs.py -v
```

## Design Document

See `docs/design.md` for the full design document.
