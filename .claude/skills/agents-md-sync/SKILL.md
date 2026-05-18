---
name: agents-md-sync
description: Manage AGENTS.md files and their CLAUDE.md symlinks. Use when verifying, creating, or fixing symlinks for AI assistant guidance files.
---

# AGENTS.md Symlink Sync

This repo uses `AGENTS.md` as the source of truth for AI assistant guidance. `CLAUDE.md` symlinks exist for Claude Code compatibility (which auto-loads `CLAUDE.md`).

## When This Skill is Invoked

1. **Find all AGENTS.md files** in the repo
2. **Check each one** for a corresponding `CLAUDE.md` symlink
3. **Report status** and fix any issues:
   - Missing symlink → create it
   - Broken symlink → recreate it
   - Regular file instead of symlink → warn user (may need manual resolution)
   - Valid symlink → report as OK

## Execution Steps

Run from the repo root:

```bash
# Find all AGENTS.md files and ensure CLAUDE.md symlinks exist
find . -name "AGENTS.md" -type f | while read f; do
  dir=$(dirname "$f")
  claude_md="$dir/CLAUDE.md"

  if [ -L "$claude_md" ]; then
    # It's a symlink - check if it points to AGENTS.md
    target=$(readlink "$claude_md")
    if [ "$target" = "AGENTS.md" ]; then
      echo "✓ $claude_md -> AGENTS.md"
    else
      echo "⚠ $claude_md points to '$target', fixing..."
      rm -f "$claude_md"
      ln -s AGENTS.md "$claude_md"
      echo "✓ Fixed: $claude_md -> AGENTS.md"
    fi
  elif [ -f "$claude_md" ]; then
    echo "⚠ $claude_md is a regular file (not a symlink) - manual review needed"
  else
    echo "Creating: $claude_md -> AGENTS.md"
    ln -s AGENTS.md "$claude_md"
    echo "✓ Created: $claude_md -> AGENTS.md"
  fi
done
```

After running, report a summary of what was checked and any actions taken.

## Notes

- Always edit `AGENTS.md` files, never `CLAUDE.md` (they're symlinks)
- Symlinks are relative (`AGENTS.md`, not full paths) so they work across clones
- Symlinks work on Mac/Linux; Windows users need Developer Mode
