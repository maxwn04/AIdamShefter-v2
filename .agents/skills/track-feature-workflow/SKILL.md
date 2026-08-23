---
name: track-feature-workflow
description: Manage large, multi-stage AIdamShefter-v2 features by keeping durable design contracts in a feature-specific docs subdirectory and gitignored execution state in the matching .context subdirectory. Use when asked to design, plan, implement, resume, track, hand off, or report progress on a major feature, especially when work spans multiple milestones, branches, or pull requests and needs an implementation plan, current status, and append-only work log.
---

# Track Feature Workflow

Run a feature from design through verified implementation without mixing durable
architecture with temporary execution state.

## Preserve the artifact boundary

| Location | Purpose | Content |
| --- | --- | --- |
| `docs/<feature>/` | Tracked design authority | Architecture, application contracts, invariants, accepted decisions, non-goals, transition policy |
| `.context/<feature>/` | Gitignored working state | Implementation plan, current status, append-only log, branch/PR notes |
| Source and tests | Product behavior | The implementation and its targeted verification |

Keep dates, branch names, changing milestone states, command output, and PR notes
out of design docs. Promote a discovery from `.context/` into `docs/` only when
future implementers need it as part of the feature contract.

Before writing local state, confirm `.context/` is ignored. Never stage or
commit `.context/` files. Do not place secrets, tokens, private payloads, or
unredacted production data in either location.

## Initialize or resume

1. Read the repository `AGENTS.md`, relevant design docs, nearby code and tests,
   and current Git state.
2. Choose one stable lowercase hyphenated feature key. Reuse an established key
   rather than creating a synonym.
3. If the workspace is missing, run:

   ```bash
   python .agents/skills/track-feature-workflow/scripts/init_feature_workflow.py \
     <feature-key> --title "<Feature Title>" --root .
   ```

   The script creates only missing files and never overwrites existing work.
4. Replace every generated prompt with feature-specific content before calling
   the design or plan complete.
5. When resuming, read `docs/<feature>/README.md`, the other linked design docs,
   `.context/<feature>/implementation-plan.md`,
   `.context/<feature>/status.md`, and the useful tail of
   `.context/<feature>/log.md`. Reconcile them with the actual branch, diff,
   commits, and test state. Treat observable repository state as authoritative
   and record any correction in the log.

If `.context/` is absent in a fresh worktree, reconstruct a truthful current
plan and status from tracked docs and Git history. Do not invent missing work
history.

## Establish the durable design

Use the smallest document set that makes the feature unambiguous. The default
set is:

- `README.md`: purpose, scope, document map, settled direction, non-goals, and
  open contract questions;
- `architecture.md`: ownership, boundaries, dependencies, data/control flow,
  lifecycle, failure semantics, and observability;
- `application-contracts.md`: public types and operations, invariants, error
  behavior, compatibility, and acceptance coverage.

Add focused documents such as `transition.md`, schema notes, or user journeys
only when they own a distinct durable concern. Link every design document from
the feature README. Inspect existing implementation before settling contracts;
do not write aspirational interfaces that ignore current seams.

Resolve or explicitly defer material questions. Do not begin a milestone whose
boundary or exit gate depends on an unanswered decision, unless the user asks
for a disposable spike.

For older features that already keep an implementation plan in `docs/`, leave
that tracked history in place unless the user asks to migrate it. Put all new
mutable progress tracking in `.context/<feature>/`.

## Maintain the local control files

### `implementation-plan.md`

Keep a dependency-ordered plan with:

- objective and links to the durable design baseline;
- implementation rules and accepted assumptions;
- stable milestone IDs;
- status for each milestone: `planned`, `in-progress`, `blocked`, `complete`, or
  `deferred`;
- ownership/scope, dependencies, concrete tasks, exit gate, and targeted
  verification for every milestone.

Allow at most one `in-progress` milestone. Mark a milestone `complete` only
after its exit gate and verification are satisfied. Split work when one
milestone crosses several deep boundaries or cannot leave the repository
runnable.

### `status.md`

Keep this as a compact present-tense snapshot, not a second plan or log. Record:

- last update time, overall state, current branch, and intended base;
- active milestone and immediate focus;
- completed work, blockers, and next actions;
- verification actually run, including failures or skipped dependencies;
- important dirty-worktree or review state.

Refresh it before implementation, after meaningful progress, before a handoff,
and at the end of the turn.

### `log.md`

Append timestamped entries in chronological order. Each entry should capture
the goal, material files or decisions, exact verification commands and concise
outcomes, milestone/status transitions, commit or PR identifiers when relevant,
and remaining risks. Never rewrite old entries to make the history cleaner;
append a correction when an earlier entry is wrong.

## Execute the implementation loop

1. Reconcile the plan and status with Git and test evidence.
2. Select the first dependency-ready milestone and mark it `in-progress`.
3. Write the immediate focus and intended verification to `status.md`; append a
   start entry to `log.md` when beginning a substantial milestone.
4. Implement the smallest coherent slice that advances its exit gate. Respect
   repository instructions and preserve unrelated user changes.
5. If implementation reveals a contract change, update the durable design first,
   then revise the local plan and record the reason in the log.
6. Run only the targeted tests and checks required by the affected behavior,
   unless the user explicitly requests broader verification.
7. Append results to the log, update the status snapshot, and change milestone
   state only when supported by evidence.
8. Inspect the final diff and Git status. Do not commit, push, open a PR, merge,
   or publish unless the user authorizes that action.

Continue through ready work when the user asked to build or implement the
feature. Planning artifacts are controls for doing the work, not a substitute
for it.

## Finish or hand off

Before declaring the feature complete:

- make the durable docs describe the implemented reality;
- satisfy every non-deferred exit gate;
- record the final targeted verification and any known unverified surface;
- set the local status to complete and append a final log entry;
- confirm `.context/` remains untracked.

For a handoff, provide the active milestone, exact next action, relevant design
links, current branch/base, verification state, blockers, and the local control
file paths. Never claim verification that did not run.
