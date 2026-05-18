# Phase 4: Article Artifact Tools

**Goal:** Implement `write_section`, `read_article`, `read_section`,
`rewrite_section`, `set_section_order`, and `submit_article`.

**Files to create:**
- `reporter_v2/runner/tools/article_tools.py`
- `reporter_v2/tests/test_article_tools.py`

**Dependencies:** Phase 1 (schemas, state), Phase 2 (RunLog)

---

## `reporter_v2/runner/tools/article_tools.py`

```python
def write_section(
    ctx: ToolContext, *, name: str, content: str,
) -> str:
    """Create or overwrite a named article section."""
    # Call ctx.artifacts.article.set_section(name, content)
    # Log artifact_write with artifact="article", operation="write_section", key=name
    # Return JSON with section count

def read_article(ctx: ToolContext) -> str:
    """Return all article sections in order."""
    # Return JSON with sections list and total word count

def read_section(
    ctx: ToolContext, *, name: str,
) -> str:
    """Return a single section by name."""
    # Return section content or error if not found

def rewrite_section(
    ctx: ToolContext, *, name: str, content: str,
) -> str:
    """Replace an existing section. Error if section doesn't exist."""
    # Validate section exists
    # Replace content
    # Log artifact_write

def set_section_order(
    ctx: ToolContext, *, names: list[str],
) -> str:
    """Set the display order of sections."""
    # Validate all names exist as sections
    # Set article.section_order
    # Return success

def submit_article(ctx: ToolContext) -> str:
    """Signal article completion. Returns the final article summary."""
    # Validate article has at least one section
    # Log completion event with stats
    # Return JSON with final article markdown and stats
```

## Tests

- `test_write_section` -- write two sections, verify order
- `test_write_section_overwrite` -- write same name twice, verify content replaced
- `test_read_article` -- write sections, read, verify all present
- `test_rewrite_section_exists` -- rewrite existing, verify updated
- `test_rewrite_section_missing` -- rewrite nonexistent, verify error
- `test_set_section_order` -- write a,b,c; reorder to c,a,b; read_article verifies new order
- `test_submit_article_empty` -- verify error when no sections
- `test_submit_article` -- verify success with sections
