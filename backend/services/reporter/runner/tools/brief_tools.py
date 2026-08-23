"""Brief artifact tools for runner v2."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.schemas import (
    Fact,
    MemoryCallback,
    Outline,
    ResolvedBias,
    ResolvedStyle,
    Storyline,
)
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry


BRIEF_TOOL_SPECS: list[ToolDef] = [
    {
        "type": "function",
        "function": {
            "name": "save_fact",
            "description": (
                "Add or update a verified fact in the report brief. Every numeric "
                "or factual claim used in the article should be grounded in saved "
                "facts with data references."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Stable fact ID, such as fact_001.",
                    },
                    "claim_text": {
                        "type": "string",
                        "description": "Human-readable factual claim.",
                    },
                    "data_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Tool/data references that sourced the claim, such as "
                            "league_snapshot:week=8."
                        ),
                    },
                    "numbers": {
                        "type": "object",
                        "description": "Important numeric values extracted from the claim.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Fact category such as score, standing, player, transaction.",
                    },
                },
                "required": ["id", "claim_text", "data_refs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory_callback",
            "description": (
                "Add or update a verified memory callback in the report brief. "
                "Use this only after the old event and current payoff have both "
                "been saved as facts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Stable callback ID, such as callback_trade_regret.",
                    },
                    "callback_type": {
                        "type": "string",
                        "description": (
                            "Callback type such as trade_regret, revenge_game, "
                            "waiver_hero, or close_game_callback."
                        ),
                    },
                    "claim_text": {
                        "type": "string",
                        "description": (
                            "Verified callback claim that links the old event to "
                            "the current payoff."
                        ),
                    },
                    "old_event_fact_id": {
                        "type": "string",
                        "description": "Saved fact ID proving the older receipt.",
                    },
                    "current_event_fact_id": {
                        "type": "string",
                        "description": "Saved fact ID proving the current payoff.",
                    },
                    "why_now": {
                        "type": "string",
                        "description": (
                            "Why the current week changes the meaning of the old event."
                        ),
                    },
                    "interestingness_reason": {
                        "type": "string",
                        "description": (
                            "Why this callback is worth drafting: stakes, reversal, "
                            "comedy value, specificity, or article fit."
                        ),
                    },
                    "memory_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional persistent memory IDs or labels that led to "
                            "the callback investigation."
                        ),
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "id",
                    "callback_type",
                    "claim_text",
                    "old_event_fact_id",
                    "current_event_fact_id",
                    "why_now",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_storyline",
            "description": (
                "Add or update a narrative storyline in the brief, backed by saved "
                "fact IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Stable storyline ID, such as story_001.",
                    },
                    "headline": {"type": "string"},
                    "summary": {
                        "type": "string",
                        "description": "Short narrative summary grounded in facts.",
                    },
                    "supporting_fact_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "priority": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "1 is lead-story priority; 5 is minor.",
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "headline", "summary", "supporting_fact_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_outline",
            "description": "Replace the planned article outline in the brief.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "bullet_points": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "required_fact_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "storyline_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["title"],
                        },
                    },
                },
                "required": ["sections"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_brief",
            "description": "Read the current report brief and staleness metadata.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_style",
            "description": "Set the resolved article voice and style controls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "voice": {"type": "string"},
                    "pacing": {"type": "string"},
                    "humor_level": {"type": "integer", "minimum": 0, "maximum": 3},
                    "formality": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_bias",
            "description": (
                "Set bias framing rules. Bias affects word choice and emphasis only, "
                "never scores, records, statistics, or other facts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "favored_teams": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "disfavored_teams": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "intensity": {"type": "integer", "minimum": 0, "maximum": 3},
                    "framing_rules": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
]


def register_brief_tools(registry: ToolRegistry) -> None:
    """Register all brief artifact tools against a ToolRegistry."""
    handlers = {
        "save_fact": save_fact,
        "save_memory_callback": save_memory_callback,
        "save_storyline": save_storyline,
        "set_outline": set_outline,
        "read_brief": read_brief,
        "set_style": set_style,
        "set_bias": set_bias,
    }
    for spec in BRIEF_TOOL_SPECS:
        name = spec["function"]["name"]
        registry.register_context_tool(name, handlers[name], spec)


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


def save_memory_callback(
    ctx: ToolContext,
    *,
    id: str,
    callback_type: str,
    claim_text: str,
    old_event_fact_id: str,
    current_event_fact_id: str,
    why_now: str,
    interestingness_reason: str = "",
    memory_refs: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    """Add or update a verified memory callback in the brief."""
    for field_name, value in {
        "callback_type": callback_type,
        "claim_text": claim_text,
        "old_event_fact_id": old_event_fact_id,
        "current_event_fact_id": current_event_fact_id,
        "why_now": why_now,
    }.items():
        if not value.strip():
            return _error(f"{field_name} must be non-empty")

    brief = ctx.artifacts.brief
    missing_fact_ids = [
        fact_id
        for fact_id in [old_event_fact_id, current_event_fact_id]
        if brief.get_fact(fact_id) is None
    ]
    if missing_fact_ids:
        return _error(
            "memory callbacks require verified fact ids",
            {"missing_fact_ids": missing_fact_ids},
        )

    callback = MemoryCallback(
        id=id,
        callback_type=callback_type,
        claim_text=claim_text,
        old_event_fact_id=old_event_fact_id,
        current_event_fact_id=current_event_fact_id,
        why_now=why_now,
        interestingness_reason=interestingness_reason,
        memory_refs=memory_refs or [],
        tags=tags or [],
    )
    operation = (
        "update_memory_callback"
        if brief.get_memory_callback(id) is not None
        else "save_memory_callback"
    )
    _upsert_by_id(brief.memory_callbacks, callback)
    revision = brief.bump_revision()
    ctx.log.add_artifact_write("brief", operation, id, revision, turn=ctx.turn)
    return _success({"callback_id": id, "brief_revision": revision})


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
