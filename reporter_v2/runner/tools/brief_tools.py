"""Brief artifact tools for runner v2."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from reporter_v2.runner.schemas import (
    Fact,
    Outline,
    ResolvedBias,
    ResolvedStyle,
    Storyline,
)
from reporter_v2.runner.tools.context import ToolContext


def save_fact(
    ctx: ToolContext,
    *,
    id: str,
    claim_text: str,
    data_refs: list[str],
    numbers: dict[str, Any] | None = None,
    category: str = "general",
) -> str:
    """Add or update a verified fact in the brief."""
    if not claim_text.strip():
        return _error("claim_text must be non-empty")
    if not data_refs:
        return _error("data_refs must contain at least one reference")

    fact = Fact(
        id=id,
        claim_text=claim_text,
        data_refs=data_refs,
        numbers=numbers or {},
        category=category,
    )
    brief = ctx.artifacts.brief
    operation = "update_fact" if brief.get_fact(id) is not None else "save_fact"
    _upsert_by_id(brief.facts, fact)
    revision = brief.bump_revision()
    ctx.log.add_artifact_write("brief", operation, id, revision, turn=ctx.turn)
    return _success({"fact_id": id, "brief_revision": revision})


def save_storyline(
    ctx: ToolContext,
    *,
    id: str,
    headline: str,
    summary: str,
    supporting_fact_ids: list[str],
    priority: int = 2,
    tags: list[str] | None = None,
) -> str:
    """Add or update a storyline in the brief."""
    brief = ctx.artifacts.brief
    fact_ids = {fact.id for fact in brief.facts}
    missing_fact_ids = [
        fact_id for fact_id in supporting_fact_ids if fact_id not in fact_ids
    ]
    if missing_fact_ids:
        return _error(
            "supporting_fact_ids contains unknown fact ids",
            {"missing_fact_ids": missing_fact_ids},
        )

    revision = brief.bump_revision()
    try:
        storyline = Storyline(
            id=id,
            headline=headline,
            summary=summary,
            supporting_fact_ids=supporting_fact_ids,
            priority=priority,
            tags=tags or [],
            revision_at_set=revision,
        )
    except ValidationError as exc:
        brief.revision -= 1
        return _error("invalid storyline", {"details": _validation_details(exc)})

    operation = (
        "update_storyline"
        if any(existing.id == id for existing in brief.storylines)
        else "save_storyline"
    )
    _upsert_by_id(brief.storylines, storyline)
    ctx.log.add_artifact_write("brief", operation, id, revision, turn=ctx.turn)
    return _success({"storyline_id": id, "brief_revision": revision})


def set_outline(ctx: ToolContext, *, sections: list[dict[str, Any]]) -> str:
    """Replace the article outline."""
    brief = ctx.artifacts.brief
    revision = brief.bump_revision()
    try:
        brief.outline = Outline(sections=sections, revision_at_set=revision)
    except ValidationError as exc:
        brief.revision -= 1
        return _error("invalid outline", {"details": _validation_details(exc)})

    ctx.log.add_artifact_write(
        "brief", "set_outline", "outline", revision, turn=ctx.turn
    )
    return _success({"brief_revision": revision})


def set_style(
    ctx: ToolContext,
    *,
    voice: str = "sports columnist",
    pacing: str = "moderate",
    humor_level: int = 1,
    formality: str = "casual",
) -> str:
    """Set resolved article style."""
    try:
        style = ResolvedStyle(
            voice=voice,
            pacing=pacing,
            humor_level=humor_level,
            formality=formality,
        )
    except ValidationError as exc:
        return _error("invalid style", {"details": _validation_details(exc)})

    ctx.artifacts.brief.style = style
    revision = ctx.artifacts.brief.bump_revision()
    ctx.log.add_artifact_write(
        "brief", "set_style", "style", revision, turn=ctx.turn
    )
    return _success({"brief_revision": revision})


def set_bias(
    ctx: ToolContext,
    *,
    favored_teams: list[str] | None = None,
    disfavored_teams: list[str] | None = None,
    intensity: int = 0,
    framing_rules: list[str] | None = None,
) -> str:
    """Set resolved article bias."""
    try:
        bias = ResolvedBias(
            favored_teams=favored_teams or [],
            disfavored_teams=disfavored_teams or [],
            intensity=intensity,
            framing_rules=framing_rules or [],
        )
    except ValidationError as exc:
        return _error("invalid bias", {"details": _validation_details(exc)})

    ctx.artifacts.brief.bias = bias
    revision = ctx.artifacts.brief.bump_revision()
    ctx.log.add_artifact_write(
        "brief", "set_bias", "bias", revision, turn=ctx.turn
    )
    return _success({"brief_revision": revision})


def read_brief(ctx: ToolContext) -> str:
    """Return the current brief and staleness metadata."""
    brief_dict = ctx.artifacts.brief.model_dump()
    brief_dict["staleness_info"] = ctx.artifacts.brief.staleness_info()
    return _json(brief_dict)


def _upsert_by_id(items: list[Any], item: Any) -> None:
    for index, existing in enumerate(items):
        if existing.id == item.id:
            items[index] = item
            return
    items.append(item)


def _success(data: dict[str, Any]) -> str:
    return _json({"ok": True, **data})


def _error(message: str, extra: dict[str, Any] | None = None) -> str:
    payload = {"ok": False, "error": message}
    if extra:
        payload.update(extra)
    return _json(payload)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True)


def _validation_details(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "loc": list(error["loc"]),
            "msg": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
