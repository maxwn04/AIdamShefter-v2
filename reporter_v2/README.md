# Reporter V2

Reporter V2 is the single-loop fantasy football reporter. It researches Sleeper
league data, builds a verified brief, writes article sections, self-verifies,
and submits the final article from one tool-using model loop.

Persistent narrative memory is provided by `reporter_memory`, not `datalayer`.

## Install

From the project root:

```bash
pip install -e .
```

This installs the `reporter-v2` CLI.

## Required Environment

Create a `.env` file in the project root:

```bash
SLEEPER_LEAGUE_ID=<your_sleeper_league_id>
OPENAI_API_KEY=<key_if_using_openai_models>
```

Optional:

```bash
SLEEPER_WEEK_OVERRIDE=8
REPORTER_V2_MODEL=gpt-5-mini
REPORTER_OUTPUT_DIR=.output
REPORTER_DATA_DIR=.data
REPORTER_V2_MAX_TURNS=60
REPORTER_V2_PROCEDURE_MODE=replace
```

`reporter-v2` uses LiteLLM model IDs, so provider-specific API keys should be
set according to LiteLLM's conventions. For example, DeepSeek models typically
need a DeepSeek API key in the environment and a model ID accepted by your
LiteLLM setup.

## Basic Usage

```bash
reporter-v2 "weekly recap" --week 8
```

Use a specific model:

```bash
reporter-v2 "weekly recap" --week 8 --model deepseek-v4-pro
```

If your LiteLLM setup expects a provider-prefixed model string, pass that
directly:

```bash
reporter-v2 "weekly recap" --week 8 --model deepseek/deepseek-chat
```

Model selection precedence:

1. `--model`
2. `REPORTER_V2_MODEL`
3. `REPORTER_MODEL`
4. `gpt-5-mini`

## Common Commands

Snarky recap:

```bash
reporter-v2 "snarky recap, roast Team Taco" --week 8 --voice "snarky columnist" --snark 3 --roast "Team Taco"
```

Power rankings:

```bash
reporter-v2 "power rankings with playoff implications" --week 8 --focus standings --focus "playoff race" --length 1400
```

Multi-week article:

```bash
reporter-v2 "midseason narrative check-in" --week-start 5 --week-end 8
```

Disable persistent context:

```bash
reporter-v2 "weekly recap" --week 8 --no-context
```

Use a different output directory:

```bash
reporter-v2 "weekly recap" --week 8 --output-dir .output/v2-runs
```

## Useful Flags

- `--week`: single week to cover
- `--week-start` / `--week-end`: range of weeks to cover
- `--week-override`: pin the Sleeper effective week during data load; overrides
  `SLEEPER_WEEK_OVERRIDE`
- `--league`: override `SLEEPER_LEAGUE_ID`
- `--model`: LiteLLM model ID
- `--voice`: writing persona
- `--snark`, `--hype`, `--seriousness`: tone controls from `0` to `3`
- `--length`: target word count
- `--focus`: topic to emphasize, repeatable or comma-separated
- `--focus-team`: team to emphasize, repeatable or comma-separated
- `--avoid`: topic to skip or minimize
- `--favor`: team to frame positively
- `--roast`: team to frame negatively
- `--bias-intensity`: framing intensity from `0` to `3`
- `--evidence-policy`: `strict`, `standard`, or `relaxed`
- `--max-turns`: maximum model turns before stopping; defaults to `60`
- `--procedure-mode`: `replace` keeps only the latest full procedure in
  conversation history; `append` keeps every loaded procedure result
- `--no-context`: skip persistent context reads/writes

## Outputs

By default, outputs are written to `.output/`:

- `v2_article_week8.md`: final article
- `v2_article_week8.brief.json`: verified brief
- `v2_article_week8.run_log_summary.json`: run summary
- `v2_article_week8.run_log.json`: structured run log with full tool arguments
- `v2_week8.stream.log`: streaming run log

Persistent narrative context is stored in `.data/context.db` unless overridden
with `REPORTER_DATA_DIR` or `--data-dir`.

The memory database uses `reporter_memory` schema `2.1`. Storyline IDs, history,
and persisted facts are scoped by league and season. Old context DB schemas are
not migrated; delete or recreate `.data/context.db` if you see an unsupported
schema-version error.

There is no `sleeperdl context` or `sleeperdl memory` surface. Reporter v2 reads
and writes memory through its persistent tools backed by
`reporter_memory.ContextStore`.

## Troubleshooting

If `reporter-v2` is not found, reinstall the package:

```bash
pip install -e .
```

If a non-OpenAI model fails immediately, verify that LiteLLM recognizes the
model string and that the provider API key is set in your shell or `.env`.

To inspect available CLI options:

```bash
reporter-v2 --help
```
