---
name: handoff-doc-writer
description: Generate a compact handoff document for transferring the current coding task between agents. Use when the user asks for a handoff, status transfer, continuation note, or agent-to-agent context doc.
argument-hint: "[handoff focus or destination]"
---

# Handoff Doc Writer

You write a handoff document that lets another coding agent continue the current work without rediscovering context. The handoff should be factual, compact, and specific to the current chat and workspace state.

## Goal

Capture:

- the primary goals from the current chat
- the current state of the feature or fix
- what has already been tried
- what did not work and why
- open questions, risks, and exact next steps

The document is a transfer artifact, not a narrative summary. Optimize for the next agent's first 10 minutes.

## Output Location

Write the handoff to `.context/handoffs/`:

```bash
mkdir -p .context/handoffs
handoff_path=".context/handoffs/$(date +%Y%m%d-%H%M%S)-handoff.md"
```

If the user provides a filename or destination, use it. Otherwise use the timestamped path above.

## Gather Context

Before writing, inspect the current workspace enough to make the document accurate:

```bash
git status --short
git branch --show-current
git diff --stat origin/main...
git diff --name-only origin/main...
```

Read only files that are relevant to the work being handed off. Prefer `rg` for discovery and targeted `sed -n` reads for details.

If tests, linters, servers, migrations, or scripts were run in the chat, capture the exact commands and outcomes from conversation context. If the outcome is unknown, say so explicitly.

## Required Structure

Use this Markdown structure:

```markdown
# Handoff: <short task name>

## Primary Goals

- <goal the user asked for>
- <important constraints or acceptance criteria>

## Current State

- <what exists now>
- <files changed or relevant>
- <branch/worktree status>

## What Has Been Tried

- <attempt, command, edit, or investigation>
- <observed result>

## What Has Not Worked

- <failed approach>
- <why it failed, if known>

## Remaining Work

- <next concrete step>
- <verification still needed>

## Key References

- `<path>`: <why it matters>
- `<command>`: <when to run it>
```

Omit a section only if it truly does not apply. Do not leave placeholder bullets.

## Writing Rules

- Keep the handoff concise: usually 1-2 pages.
- Use exact file paths, command names, branch names, ticket IDs, issue URLs, and test names.
- Distinguish confirmed facts from inference.
- State blockers plainly.
- Do not include long pasted diffs or full command logs. Summarize the important result and point to the command.
- Do not claim work is verified unless the verification command actually ran and passed.
- Include user preferences or instructions only when they affect continuing this task.

## Final Response

After writing the handoff, tell the user:

- the handoff path
- the most important next step
- whether verification was captured or still missing
