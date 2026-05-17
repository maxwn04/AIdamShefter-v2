---
name: aida-season-simulator
description: Simulate running AIda report writing week-by-week across a season, rebuilding persistent context naturally from an empty database.
argument-hint: "<week range, e.g. weeks 1-14>"
---

# AIda Season Simulator

Simulate a season of weekly AIda reports. The goal is to rebuild `.data/context.db` naturally as if the reporter had been run every week.

Each week must be handled by a subagent, and weeks must run sequentially. Do not parallelize weeks. The whole point is that Week N+1 reads the context created by Week N.

## Core Rules

- Start by wiping the persistent context database.
- Run one weekly report per week.
- Use `SLEEPER_WEEK_OVERRIDE=<week>` when creating each week’s snapshot.
- Each weekly report must use `aida-report-writer`.
- Each weekly report should be a weekly summary that ties the week into the larger state of the league.
- Vary the editorial focus across weeks: rivalries, best teams, worst teams, standings movement, fraud watch, contender watch, collapse watch, waiver/trade fallout.
- Vary the tone across weeks: hype, snarky, informative, measured, playful.
- Wait for each subagent to finish before starting the next week.
- The context database is the main audit trail. Reports should update storylines, team context, league notes, and persisted facts.

## Setup

Wipe the context database before starting:

```bash
rm -f .data/context.db
```

Create a parent run directory:

```bash
season_run_id="$(date +%Y%m%d-%H%M%S)"
season_run_dir=".output/season-sims/$season_run_id"
mkdir -p "$season_run_dir"
```

## Determine Weeks

If the user gave a range, use it exactly.

If no range was given, infer a sensible regular-season range from the league data. You can inspect current data with:

```bash
sleeperdl load --output "$season_run_dir/current.sqlite" --refresh
sleeperdl query run_sql query="SELECT effective_week FROM season_context LIMIT 1" --snapshot "$season_run_dir/current.sqlite"
```

Default to weeks `1..effective_week` unless the user asks for playoffs or a smaller range.

## Weekly Subagent Prompt

For each week, launch exactly one subagent and wait for it to complete before launching the next. Give the subagent a prompt like this:

```text
Use aida-report-writer to write Week <N>'s weekly summary.

This is part of a sequential season simulation. Use:
- SLEEPER_WEEK_OVERRIDE=<N> for the snapshot load command.
- Run directory: <season_run_dir>/week-<N>
- Article request: "Write a weekly summary for Week <N> that ties this week into the larger state of the league. Focus on <FOCUS>. Use a <TONE> tone. Continue or resolve any relevant persistent storylines from prior weeks, and update the context database after writing."

Important:
- Read persistent context first.
- Use current-week snapshot facts for all numbers.
- Treat context as continuity, not factual proof.
- Update storylines/team context/league notes/persisted facts before finishing.
- Return the article path and a concise list of context updates.
```

## Focus And Tone Rotation

Use this rotation as a default. Adjust if the data clearly suggests a better angle.

| Week pattern | Focus | Tone |
| --- | --- | --- |
| `week % 6 == 1` | league-wide landscape, early contenders, standings movement | informative |
| `week % 6 == 2` | rivalries, revenge games, close matchups | hype |
| `week % 6 == 3` | best teams, dominant wins, title cases | informative |
| `week % 6 == 4` | worst teams, collapses, bench regrets | snarky |
| `week % 6 == 5` | fraud watch, streaks, panic meter | playful/snarky |
| `week % 6 == 0` | playoff race, trade/waiver fallout, league hierarchy | hype/informative |

The weekly prompt should always mention the larger state of the league so the writer builds continuity instead of producing isolated recaps.

## Sequential Workflow

For each week:

1. Compute the week focus and tone.
2. Spawn one subagent with the weekly prompt.
3. Wait for that subagent to finish.
4. Record its article path and context-update summary in a season index file.
5. Only then move to the next week.

Write a season index:

```text
$season_run_dir/index.md
```

Include:

- week number
- focus
- tone
- article path
- reported context updates
- any failures or follow-up notes

## Failure Handling

If a week fails:

- Stop the simulation.
- Do not skip ahead; that would corrupt the natural context-building sequence.
- Record the failure in `index.md`.
- Report the failed week and the subagent’s last useful output.

## Final Response

Return:

- season run directory
- weeks completed
- article paths
- a short summary of how the context database evolved
- any failed week, if applicable

