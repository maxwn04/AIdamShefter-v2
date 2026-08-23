#!/usr/bin/env python3
"""Initialize durable feature docs and gitignored local workflow state."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path


FEATURE_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create missing docs/<feature> and .context/<feature> workflow files "
            "without overwriting existing work."
        )
    )
    parser.add_argument("feature", help="Lowercase hyphenated feature key")
    parser.add_argument("--title", help="Human-readable feature title")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current directory)",
    )
    return parser.parse_args()


def write_new(path: Path, content: str, created: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    created.append(path)


def relative_paths(paths: list[Path], root: Path) -> list[str]:
    return [path.relative_to(root).as_posix() for path in paths]


def main() -> int:
    args = parse_args()
    if not FEATURE_KEY_PATTERN.fullmatch(args.feature):
        raise SystemExit(
            "feature must use lowercase letters, digits, and single hyphens "
            "(example: generation-audit)"
        )

    root = args.root.resolve()
    title = args.title or args.feature.replace("-", " ").title()
    feature = args.feature
    docs_dir = root / "docs" / feature
    context_dir = root / ".context" / feature
    now = datetime.now().astimezone().isoformat(timespec="minutes")
    created: list[Path] = []
    skipped: list[Path] = []
    document_rows = (
        "| [`architecture.md`](architecture.md) | Component boundaries, dependencies, "
        "lifecycle, and failure behavior |\n"
        "| [`application-contracts.md`](application-contracts.md) | Public contracts, "
        "invariants, errors, and acceptance coverage |"
    )
    milestone_row = (
        f"| `{feature}-1` | planned | Design accepted | "
        "<!-- First coherent boundary --> | "
        "<!-- Observable completion condition --> |"
    )

    files = {
        docs_dir / "README.md": f"""
# {title} Design

**Status:** Proposed

## Purpose

<!-- State the product or engineering outcome this feature owns. -->

## Scope

<!-- Name the components and workflows inside this design boundary. -->

## Documents

| Document | Owns |
| --- | --- |
{document_rows}

## Settled Direction

<!-- Record durable decisions future implementers must preserve. -->

## Non-Goals

<!-- List adjacent work this feature deliberately does not own. -->

## Open Questions

<!-- Resolve, defer with an owner, or remove every question before
implementation depends on it. -->
""",
        docs_dir / "architecture.md": f"""
# {title} Architecture

## Context and Goals

<!-- Describe the current system seam and the target behavior. -->

## System Boundary

<!-- Define owners, dependencies, callers, and forbidden coupling. -->

## Component Model

<!-- Describe responsibilities and collaboration between components. -->

## Data and Control Flow

<!-- Describe important reads, writes, state transitions, and transaction boundaries. -->

## Failure and Recovery Semantics

<!-- Define typed failures, retry/idempotency rules, and partial-failure behavior. -->

## Observability

<!-- Define logs, metrics, traces, audit data, and operator-visible state. -->

## Security and Privacy

<!-- Define trust boundaries, authorization, validation, and sensitive-data handling. -->

## Architecture Decisions

<!-- Record decisions and their rationale. -->

## Open Questions

<!-- Keep only unresolved architecture questions. -->
""",
        docs_dir / "application-contracts.md": f"""
# {title} Application Contracts

## Vocabulary and Ownership

<!-- Define stable terms and the component that owns each concept. -->

## Public Contracts

<!-- Specify caller-facing types, commands, queries, events, or routes. -->

## Lifecycle and State Transitions

<!-- Define valid states, transitions, concurrency, and idempotency. -->

## Invariants

<!-- State rules that must remain true across implementations. -->

## Error Semantics

<!-- Define typed failures, masking, retryability, and boundary translation. -->

## Compatibility and Transition

<!-- Define migration, coexistence, deprecation, or cutover behavior. -->

## Acceptance Coverage

<!-- Map contract behavior to focused tests and operational checks. -->
""",
        context_dir / "README.md": f"""
# {title} Local Workflow

This directory is mutable, gitignored execution state. Durable feature authority
lives in [`docs/{feature}/`](../../docs/{feature}/).

## Files

- `implementation-plan.md`: dependency-ordered milestones and exit gates;
- `status.md`: current snapshot for resuming or handing off work;
- `log.md`: append-only chronology of work and verification.

Do not stage or commit this directory. Promote durable decisions into the design
docs instead of treating this workspace as architectural authority.
""",
        context_dir / "implementation-plan.md": f"""
# {title} Implementation Plan

Last updated: {now}

## Objective

<!-- Restate the concrete implementation outcome. -->

## Design Baseline

- `docs/{feature}/README.md`
- `docs/{feature}/architecture.md`
- `docs/{feature}/application-contracts.md`

## Implementation Rules

<!-- Record feature-specific sequencing, compatibility, and verification rules. -->

## Milestones

| ID | Status | Depends on | Deliverable | Exit gate |
| --- | --- | --- | --- | --- |
{milestone_row}

## `{feature}-1` — <!-- Milestone title -->

**Owns**

- <!-- One deep implementation boundary. -->

**Tasks**

- <!-- Concrete change. -->

**Targeted verification**

- <!-- Exact test or check command. -->

**Exit gate:** <!-- Evidence required before status becomes complete. -->
""",
        context_dir / "status.md": f"""
# {title} Status

Last updated: {now}

- **Overall state:** designing
- **Branch:** <!-- current branch -->
- **Intended base:** <!-- base branch or commit -->
- **Active milestone:** none
- **Immediate focus:** complete the durable design and implementation plan

## Completed

- Workflow workspace initialized.

## In Progress

- Durable design and milestone definition.

## Blockers

- None recorded.

## Next Actions

1. Replace design prompts with repository-grounded decisions.
2. Define dependency-ordered milestones and targeted verification.
3. Start the first dependency-ready milestone.

## Verification

- Not run; implementation has not started.

## Working Tree and Review State

<!-- Record relevant dirty files, commits, PRs, or review state. -->
""",
        context_dir / "log.md": f"""
# {title} Implementation Log

Append entries in chronological order. Keep exact commands and concise outcomes;
never include secrets or rewrite earlier history.

## {now} — Workflow initialized

- Created the durable design workspace at `docs/{feature}/`.
- Created local implementation controls at `.context/{feature}/`.
- No implementation verification has run yet.
""",
    }

    for path, content in files.items():
        write_new(path, content, created, skipped)

    print("Created:")
    for path in relative_paths(created, root):
        print(f"  {path}")
    if not created:
        print("  (none)")

    print("Skipped existing:")
    for path in relative_paths(skipped, root):
        print(f"  {path}")
    if not skipped:
        print("  (none)")

    print("Next: replace every HTML comment with feature-specific content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
