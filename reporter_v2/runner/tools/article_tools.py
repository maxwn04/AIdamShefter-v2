"""Article artifact tools for reporter v2."""

from __future__ import annotations

import json
import re
from typing import Any

from reporter_v2.runner.schemas import ArticleSection
from reporter_v2.runner.tools.context import ToolContext


def write_section(ctx: ToolContext, *, name: str, content: str) -> str:
    """Create or overwrite a named article section."""
    ctx.artifacts.article.set_section(name, content)
    ctx.log.add_artifact_write(
        "article",
        "write_section",
        name,
        turn=ctx.turn,
    )
    return _json(
        {
            "ok": True,
            "section_count": len(ctx.artifacts.article.sections),
            "section_order": ctx.artifacts.article.section_order,
        }
    )


def read_article(ctx: ToolContext) -> str:
    """Return all article sections in display order."""
    sections = _ordered_sections(
        ctx.artifacts.article.sections,
        ctx.artifacts.article.section_order,
    )
    markdown = ctx.artifacts.article.to_markdown()
    return _json(
        {
            "ok": True,
            "sections": [_section_payload(section) for section in sections],
            "section_count": len(ctx.artifacts.article.sections),
            "total_word_count": _word_count(markdown),
        }
    )


def read_section(ctx: ToolContext, *, name: str) -> str:
    """Return a single article section by name."""
    section = ctx.artifacts.article.get_section(name)
    if section is None:
        return _error(f"Section not found: {name}", name=name)

    return _json({"ok": True, "section": _section_payload(section)})


def rewrite_section(ctx: ToolContext, *, name: str, content: str) -> str:
    """Replace an existing section."""
    section = ctx.artifacts.article.get_section(name)
    if section is None:
        return _error(f"Section not found: {name}", name=name)

    section.content = content
    ctx.log.add_artifact_write(
        "article",
        "rewrite_section",
        name,
        turn=ctx.turn,
    )
    return _json(
        {
            "ok": True,
            "section": _section_payload(section),
            "section_count": len(ctx.artifacts.article.sections),
        }
    )


def set_section_order(ctx: ToolContext, *, names: list[str]) -> str:
    """Set the display order of article sections."""
    existing_names = [section.name for section in ctx.artifacts.article.sections]
    unknown_names = [name for name in names if name not in existing_names]
    missing_names = [name for name in existing_names if name not in names]
    duplicate_names = _duplicate_names(names)

    if unknown_names or missing_names or duplicate_names:
        return _json(
            {
                "ok": False,
                "error": "Section order must include each existing section exactly once.",
                "unknown_names": unknown_names,
                "missing_names": missing_names,
                "duplicate_names": duplicate_names,
            }
        )

    ctx.artifacts.article.section_order = list(names)
    ctx.log.add_artifact_write(
        "article",
        "set_section_order",
        "section_order",
        turn=ctx.turn,
    )
    return _json({"ok": True, "section_order": ctx.artifacts.article.section_order})


def submit_article(ctx: ToolContext) -> str:
    """Signal article completion and return the final article."""
    article = ctx.artifacts.article
    if not article.sections:
        return _error("Cannot submit an empty article.")

    markdown = article.to_markdown()
    stats = {
        "section_count": len(article.sections),
        "total_word_count": _word_count(markdown),
        "total_char_count": len(markdown),
    }
    ctx.log.add_completion(stats, turn=ctx.turn)
    return _json({"ok": True, "article": markdown, "stats": stats})


def _ordered_sections(
    sections: list[ArticleSection],
    section_order: list[str],
) -> list[ArticleSection]:
    if not section_order:
        return sections

    by_name = {section.name: section for section in sections}
    ordered = [by_name[name] for name in section_order if name in by_name]
    unordered = [section for section in sections if section.name not in section_order]
    return ordered + unordered


def _section_payload(section: ArticleSection) -> dict[str, Any]:
    return {
        "name": section.name,
        "content": section.content,
        "word_count": _word_count(section.content),
    }


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:[.'-][A-Za-z0-9]+)*", text))


def _duplicate_names(names: list[str]) -> list[str]:
    seen = set()
    duplicates = []
    for name in names:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates


def _error(message: str, **extra: Any) -> str:
    return _json({"ok": False, "error": message, **extra})


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload)
