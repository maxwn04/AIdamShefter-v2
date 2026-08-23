"""Tests for reporter v2 article artifact tools."""

from __future__ import annotations

import json

from backend.services.reporter.runner.run_log import RunLog
from backend.services.reporter.runner.state import ArtifactStore, ProcedureState
from backend.services.reporter.runner.tools.article_tools import (
    read_article,
    read_section,
    rewrite_section,
    set_section_order,
    submit_article,
    write_section,
)
from backend.services.reporter.runner.tools.context import ToolContext


def make_ctx() -> ToolContext:
    return ToolContext(
        artifacts=ArtifactStore(),
        procedures=ProcedureState(),
        log=RunLog(session_id="testlog"),
        turn=3,
    )


def decode(result: str) -> dict:
    return json.loads(result)


def test_write_section() -> None:
    ctx = make_ctx()

    first = decode(write_section(ctx, name="opening", content="# Opening\n\nHello."))
    second = decode(write_section(ctx, name="closing", content="# Closing\n\nBye."))

    assert first["ok"] is True
    assert second["section_count"] == 2
    assert ctx.artifacts.article.section_order == ["opening", "closing"]
    assert ctx.artifacts.article.to_markdown() == "# Opening\n\nHello.\n\n# Closing\n\nBye."
    assert [entry.data["operation"] for entry in ctx.log.entries] == [
        "write_section",
        "write_section",
    ]


def test_write_section_overwrite() -> None:
    ctx = make_ctx()

    write_section(ctx, name="opening", content="First draft")
    result = decode(write_section(ctx, name="opening", content="Second draft"))

    assert result["section_count"] == 1
    assert ctx.artifacts.article.get_section("opening").content == "Second draft"
    assert ctx.artifacts.article.section_order == ["opening"]


def test_read_article() -> None:
    ctx = make_ctx()
    write_section(ctx, name="opening", content="# Opening\n\nHello league.")
    write_section(ctx, name="closing", content="# Closing\n\nGood night.")

    result = decode(read_article(ctx))

    assert result["ok"] is True
    assert result["section_count"] == 2
    assert result["total_word_count"] == 6
    assert [section["name"] for section in result["sections"]] == ["opening", "closing"]
    assert result["sections"][0]["content"] == "# Opening\n\nHello league."


def test_read_section() -> None:
    ctx = make_ctx()
    write_section(ctx, name="opening", content="# Opening\n\nHello.")

    result = decode(read_section(ctx, name="opening"))

    assert result == {
        "ok": True,
        "section": {
            "name": "opening",
            "content": "# Opening\n\nHello.",
            "word_count": 2,
        },
    }


def test_read_section_missing() -> None:
    ctx = make_ctx()

    result = decode(read_section(ctx, name="missing"))

    assert result["ok"] is False
    assert result["name"] == "missing"
    assert "not found" in result["error"]


def test_rewrite_section_exists() -> None:
    ctx = make_ctx()
    write_section(ctx, name="opening", content="First draft")

    result = decode(rewrite_section(ctx, name="opening", content="Final draft"))

    assert result["ok"] is True
    assert result["section"]["content"] == "Final draft"
    assert ctx.artifacts.article.get_section("opening").content == "Final draft"
    assert ctx.log.entries[-1].data == {
        "artifact": "article",
        "operation": "rewrite_section",
        "key": "opening",
        "brief_revision": None,
    }


def test_rewrite_section_missing() -> None:
    ctx = make_ctx()

    result = decode(rewrite_section(ctx, name="missing", content="Nope."))

    assert result["ok"] is False
    assert result["name"] == "missing"
    assert ctx.log.entries == []


def test_set_section_order() -> None:
    ctx = make_ctx()
    write_section(ctx, name="a", content="# A")
    write_section(ctx, name="b", content="# B")
    write_section(ctx, name="c", content="# C")

    result = decode(set_section_order(ctx, names=["c", "a", "b"]))
    article = decode(read_article(ctx))

    assert result == {"ok": True, "section_order": ["c", "a", "b"]}
    assert [section["name"] for section in article["sections"]] == ["c", "a", "b"]
    assert ctx.artifacts.article.to_markdown() == "# C\n\n# A\n\n# B"


def test_set_section_order_rejects_unknown_or_missing_names() -> None:
    ctx = make_ctx()
    write_section(ctx, name="a", content="# A")
    write_section(ctx, name="b", content="# B")

    result = decode(set_section_order(ctx, names=["b", "c"]))

    assert result["ok"] is False
    assert result["unknown_names"] == ["c"]
    assert result["missing_names"] == ["a"]
    assert result["duplicate_names"] == []
    assert ctx.artifacts.article.section_order == ["a", "b"]


def test_set_section_order_rejects_duplicate_names() -> None:
    ctx = make_ctx()
    write_section(ctx, name="a", content="# A")
    write_section(ctx, name="b", content="# B")

    result = decode(set_section_order(ctx, names=["a", "a", "b"]))

    assert result["ok"] is False
    assert result["unknown_names"] == []
    assert result["missing_names"] == []
    assert result["duplicate_names"] == ["a"]
    assert ctx.artifacts.article.section_order == ["a", "b"]


def test_submit_article_empty() -> None:
    ctx = make_ctx()

    result = decode(submit_article(ctx))

    assert result["ok"] is False
    assert "empty article" in result["error"]
    assert ctx.log.entries == []


def test_submit_article() -> None:
    ctx = make_ctx()
    write_section(ctx, name="opening", content="# Opening\n\nHello league.")
    write_section(ctx, name="closing", content="# Closing\n\nGood night.")

    result = decode(submit_article(ctx))

    assert result == {
        "ok": True,
        "article": "# Opening\n\nHello league.\n\n# Closing\n\nGood night.",
        "stats": {
            "section_count": 2,
            "total_word_count": 6,
            "total_char_count": 48,
        },
    }
    assert ctx.log.entries[-1].event_type == "completion"
    assert ctx.log.entries[-1].data == result["stats"]
