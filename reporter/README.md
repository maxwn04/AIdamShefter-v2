# AI Fantasy Football Reporter

An AI-powered reporter agent that generates engaging, factually grounded articles about your Sleeper fantasy football league.

## Features

- **Natural language requests**: Describe the article you want in plain English
- **Iterative research**: Agent explores league data, identifies storylines, and builds a verified brief before writing
- **Configurable voice and tone**: Snarky columnist, hype broadcaster, noir detective, or anything you describe
- **Bias system**: Optionally favor or roast specific teams. Bias affects framing only -- facts always remain accurate.

## Installation

```bash
pip install -e .
```

## Configuration

Create a `.env` file in the project root:

```bash
SLEEPER_LEAGUE_ID=your_league_id
OPENAI_API_KEY=your_openai_key
REPORTER_MODEL=gpt-5-mini          # Optional: default model
REPORTER_OUTPUT_DIR=.output         # Optional: where articles are saved
```

## Usage

### CLI

```bash
# Pass a natural language request
reporter "weekly recap"
reporter "snarky recap, roast Team Taco" --week 8
reporter "power rankings with analysis"
reporter "deep dive on Team Taco's season"

# Interactive mode (prompts for input)
reporter

# Specify model
reporter "weekly recap" --model gpt-5
```

The CLI flow:
1. **Clarification**: A clarification agent interprets your request and asks targeted questions if needed
2. **Confirmation**: You review the resolved config (week, voice, tone, bias) and confirm
3. **Research**: The research agent iteratively queries league data and builds a verified brief
4. **Draft**: The draft agent writes the article from the brief (no tool access, no hallucination)
5. **Output**: Article is displayed and saved to `.output/`

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

1. **Research** (`ResearchAgent`): Has full tool access. Iteratively queries the datalayer, builds a `ReportBrief` containing verified `Fact` objects and `Storyline` narratives. All tool calls and reasoning logged in `ResearchLog`.
2. **Draft** (`DraftAgent`): No tool access. Writes the article purely from the `ReportBrief`, applying configured voice and style.

### Key Types

- **ReportConfig** (`reporter/agent/config.py`): What to write (time range, voice, tone, bias, focus hints)
- **ReportBrief** (`reporter/agent/schemas.py`): Research artifact (facts, storylines, outline)
- **ArticleOutput** (`reporter/agent/schemas.py`): Final output (article + config + brief + research log)

## Output Files

Generated articles are saved to `.output/` by default:
- `article_week8.md` - The article
- `article_week8.brief.json` - The research brief
- `article_week8.research_log.md` - Research log
- `research_week8.stream.log` - Streaming research log (tail -f while running)

## Tests

```bash
pytest reporter/tests/              # All reporter tests
pytest reporter/tests/ -v           # Verbose
```

## Design Documents

- `docs/design.md` - Reporter agent architecture
- `docs/redesign_iterative_research.md` - Iterative research design
