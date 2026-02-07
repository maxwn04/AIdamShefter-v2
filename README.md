# AIdamShefter-v2

AI-powered fantasy football reporter. Fetches Sleeper league data, loads it into an in-memory SQLite database, and uses an AI agent pipeline to write data-grounded articles.

## Setup

```bash
pip install -e .
```

Create a `.env` file in the project root:

```
SLEEPER_LEAGUE_ID=<league_id>
OPENAI_API_KEY=<key>
```

## Quick Start

```bash
# Datalayer CLI
sleeperdl app                                          # Interactive query shell
sleeperdl load-export --output out.sqlite

# Reporter CLI
reporter "weekly recap"                                # Natural language request
reporter "snarky recap, roast Team Taco" --week 8      # With week and style hints
reporter "power rankings with analysis"                # Any article type
reporter "deep dive on Team Taco's season"             # Team-focused
reporter                                               # Interactive prompt
```

## Tests

```bash
pytest                                  # All tests
pytest datalayer/tests/                 # Datalayer tests only
pytest reporter/tests/                  # Reporter tests only
pytest datalayer/tests/unit/            # Datalayer unit tests
pytest datalayer/tests/integration/     # Datalayer integration tests
```

## Project Structure

```
datalayer/          # Sleeper API data layer
  sleeper_data/     # Core: fetch, normalize, store, query
  tools.py          # OpenAI function-calling tool definitions
  tests/            # Datalayer tests + fixtures
  cli/              # sleeperdl CLI

reporter/           # AI reporter agent
  agent/            # ReporterAgent, ResearchAgent, DraftAgent, ClarificationAgent
  app/              # CLI runner and config
  tools/            # Tool adapters for OpenAI Agents SDK
  prompts/          # Prompt templates (system, research, draft, bias)
  tests/            # Reporter tests
```

See `CLAUDE.md` for detailed architecture documentation.
