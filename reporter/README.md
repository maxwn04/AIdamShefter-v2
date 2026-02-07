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

Optionally favor or roast specific teams. Bias affects framing only -- facts always remain accurate.

## Installation

```bash
pip install -e .
```

## Configuration

Create a `.env` file in the project root:

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
from reporter.agent.workflows import generate_report

output = generate_report(
    "Write a weekly recap",
    week=8,
    voice="snarky columnist",
    snark_level=2,
    favored_teams=["Team Taco"],
)
print(output.article)
```

## Architecture

The reporter uses a two-phase pipeline:

1. **Research** (`ResearchAgent`): Has full tool access. Iteratively queries the datalayer, builds a `ReportBrief` containing verified `Fact` objects and `Storyline` narratives.
2. **Draft** (`DraftAgent`): No tool access. Writes the article purely from the `ReportBrief`, applying configured voice and style.

### Key Types

- **ReportConfig** (`reporter/agent/config.py`): What to write (time range, voice, tone, bias)
- **ReportBrief** (`reporter/agent/schemas.py`): Research artifact (facts, storylines, outline)
- **ArticleOutput** (`reporter/agent/schemas.py`): Final output (article + metadata)

## Output Files

Generated articles are saved to `.output/` by default:
- `article_week8.md` - The article
- `article_week8.brief.json` - The research brief
- `article_week8.research_log.md` - Research log

## Tests

```bash
pytest reporter/tests/              # All reporter tests
pytest reporter/tests/ -v           # Verbose
```

## Design Documents

- `docs/design.md` - Reporter agent architecture
- `docs/redesign_iterative_research.md` - Iterative research design
