---
name: learn-from-chat
description: Analyze the current chat history to extract lessons — both from user corrections/interventions AND from best practices discovered collaboratively during the session. Propose targeted updates to the appropriate AGENTS.md files so knowledge is preserved. Use when the user asks to learn from the session, improve AGENTS.md, or create a feedback loop.
disable-model-invocation: true
---

# Learn from Chat

Analyze the current conversation to extract lessons from two sources: (1) every point where the user had to intervene — corrections, takeovers, refactors, or overrides — and (2) best practices, patterns, or insights that were discovered collaboratively during the session. Propose concrete updates to the relevant `AGENTS.md` files.

## When to Use

- At the end of a coding session to capture lessons learned
- When the user says "learn from this", "update AGENTS.md", or "don't make this mistake again"
- When the user explicitly invokes `/learn-from-chat`

## Instructions

### Step 1: Audit the conversation

Carefully re-read the full chat history and identify lessons from **both** categories:

#### Category A: User interventions (corrections, overrides)

Instances where the user had to step in:

1. **Correction** — The user told you something was wrong, or you produced output the user had to fix (e.g., "no, use X instead of Y", "that's not how we do it here")
2. **Takeover** — The user did the work themselves after you failed or produced unsatisfactory output (e.g., they pasted corrected code, made the edit manually)
3. **Refactor** — The user accepted your output but then refactored or restyled it (e.g., renamed variables, restructured logic, changed patterns)
4. **Explicit guidance** — The user gave you a rule or preference you didn't already know (e.g., "we always use X for this", "never do Y in this codebase")
5. **Repeated mistakes** — You made the same type of error more than once in the conversation

For each instance, record:
- **What happened**: A brief description of the intervention
- **Root cause**: Why you got it wrong (missing context, wrong assumption, ignored existing pattern, etc.)
- **The lesson**: The rule or convention that would have prevented the mistake

#### Category B: Collaborative discoveries (best practices found together)

Insights that emerged from the conversation through joint analysis, debugging, or code review — even when neither party "corrected" the other:

1. **Anti-pattern identified** — You and the user together identified a problematic pattern in the codebase (e.g., "this logging inside retries creates Sentry noise")
2. **Best practice established** — A discussion led to a clear best practice worth codifying (e.g., "use `before_sleep_log` for retry observability + caller-level Sentry for final failures")
3. **Architectural insight** — The session revealed an important design principle or convention that isn't documented yet

For each instance, record:
- **What happened**: A brief description of the discovery
- **The lesson**: The best practice or pattern worth preserving

### Step 2: Deduplicate and generalize

- Merge instances that stem from the same root cause into a single lesson
- Generalize from specific corrections to broader rules where appropriate (e.g., if the user corrected one import path, check if it implies a general import convention)
- Discard anything that is already covered by an existing `AGENTS.md` rule — only surface *net-new* guidance
- Discard one-off project-specific decisions that don't generalize (e.g., "name this variable `foo`")

### Step 3: Determine target files

Map each lesson to the most specific `AGENTS.md` file it belongs in.

**First, discover all `AGENTS.md` files in the project:**

Use glob to find all `AGENTS.md` files across nested directories:

```bash
# Find all AGENTS.md files in the project
find . -name "AGENTS.md" -type f | sort
```

This ensures you work with the current set of files rather than a potentially stale list.

**Common locations include (but are not limited to):**

| Scope | File |
|-------|------|
| Project-wide conventions | `./AGENTS.md` |
| All backend code | `./backend/AGENTS.md` |
| Backend routes | `./backend/server_cs/routes/AGENTS.md` |
| Database patterns | `./backend/database/AGENTS.md` |
| Services layer | `./backend/services/AGENTS.md` |
| Background jobs | `./backend/jobs_server/jobs/AGENTS.md` |
| Backend tests | `./backend/tests/AGENTS.md` |
| All frontend code | `./frontend/AGENTS.md` |

**Note:** The table above is just a reference. Always use the discovered files from the glob search, as new `AGENTS.md` files may exist in subdirectories not listed here.

**Prefer the most specific file.** A rule about database session usage belongs in `backend/AGENTS.md`, not the root `AGENTS.md`. A rule about React component patterns belongs in `frontend/AGENTS.md`.

If a lesson doesn't fit any existing file, note that it may warrant a new `AGENTS.md` in the relevant subdirectory.

### Step 4: Read target files

Before proposing changes, read each target `AGENTS.md` file to:
- Confirm the lesson isn't already covered (skip if it is)
- Find the right section to insert the new rule
- Match the existing tone, formatting, and level of detail

### Step 5: Present findings for approval

Present a structured report to the user **before making any changes**:

```
## Lessons from This Session

### From user interventions:

#### 1. [Short title]
- **What happened**: [Brief description of the intervention]
- **Lesson**: [The generalized rule]
- **Target file**: `[path/to/AGENTS.md]`
- **Section**: [Existing section name, or "New section: X"]
- **Proposed addition**:
  > [The exact text to add, matching the file's style]

### From collaborative discoveries:

#### 2. [Short title]
- **What happened**: [Brief description of the discovery]
- **Lesson**: [The best practice or pattern]
- **Target file**: `[path/to/AGENTS.md]`
- **Section**: [Existing section name, or "New section: X"]
- **Proposed addition**:
  > [The exact text to add, matching the file's style]

---

**No changes found**: [List any items you reviewed but excluded, with brief reasons]
```

Note: Either category may be empty for a given session. Only include sections that have entries.

### Step 6: Apply approved changes

After the user reviews and approves (they may modify, accept, or reject individual items):

1. Edit each approved `AGENTS.md` file using the edit tool
2. Place new rules in the identified section, maintaining alphabetical or logical ordering
3. Match the existing formatting exactly (heading levels, code block style, emoji usage)
4. If adding a new section, follow the naming conventions of existing sections
5. Run the `agents-md-sync` skill to ensure `CLAUDE.md` symlinks are up to date

### Important Guidelines

- **Be conservative**: Only propose rules that would genuinely prevent future mistakes. Don't pad the list.
- **Be specific**: "Use `async_read_only_session()` for read-only queries" is better than "use the right session type."
- **Include examples**: If the existing `AGENTS.md` uses `✅ CORRECT` / `❌ WRONG` example patterns, follow that format.
- **Don't duplicate**: If a rule already exists but you missed it during the session, note that in the report but don't re-add it.
- **Respect scope**: Don't add frontend rules to backend files or vice versa.
- **Never auto-apply**: Always present findings for user approval first.
