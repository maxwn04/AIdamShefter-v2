"""Specialized tools for the runtime-owned structured research brief."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from pydantic import JsonValue, ValidationError

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.grounding import (
    binding_numbers, resolve_bindings, validate_fact,
)
from backend.services.reporter.runner.research_brief import (
    RESEARCH_BRIEF_PATH,
    ResearchBriefError,
)
from backend.services.reporter.runner.tools.context import ToolContext
from backend.services.reporter.runner.tools.registry import ToolRegistry


BRIEF_TOOL_IMPLEMENTATION_VERSION = "4"

BRIEF_TOOL_SPECS: list[ToolDef] = [
    {
        "type": "function",
        "function": {
            "name": "save_fact",
            "description": (
                "Add or update one evidence-bound fact in the structured research brief. "
                "Select source ref, field and value; source identity and period are derived automatically. "
                "Independent facts may be saved together in one tool-call batch."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[a-z][a-z0-9_-]{0,63}$",
                        "description": "Stable ID such as fact_taco_week_8_win.",
                    },
                    "claim_text": {
                        "type": "string",
                        "description": "Precise human-readable factual claim.",
                    },
                    "bindings": {
                        "type": "array",
                        "minItems": 1,
                        "description": "Select exact executed ref, field and value. Source subject, period and perspective are derived automatically; traceability does not prove prose entailment.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ref": {"type": "string"},
                                "field": {"type": "string"},
                                "value": {},
                            },
                            "required": ["ref", "field", "value"],
                            "additionalProperties": False,
                        },
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Category such as score, standing, player, transaction, "
                            "history, comparison (same-franchise ordered before/after only), superlative, or championship. "
                            "Use player or score for different players/teams in one week. "
                            "Transaction claims must select a sent/received asset identity or net_draft_picks, not just bid/status."
                        ),
                    },
                    "superlative_binding": {
                        "type": "object",
                        "description": "Select the asserted metric from bindings when other bindings provide context such as rank, team or score.",
                        "properties": {"ref": {"type": "string"}, "field": {"type": "string"}},
                        "required": ["ref", "field"],
                        "additionalProperties": False,
                    },
                    "superlative_direction": {"type": "string", "enum": ["min", "max"], "description": "Required for superlatives: direction of the selected numeric field (rank 1 uses min)."},
                    "superlative_unique": {"type": "boolean", "description": "Set true only when claiming the sole extreme; otherwise tied extremes are allowed."},
                },
                "required": ["id", "claim_text", "bindings"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory_callback",
            "description": (
                "Add or update a verified callback after both the old event and "
                "current payoff exist as saved facts. Use IDs returned by successful save_fact calls."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[a-z][a-z0-9_-]{0,63}$",
                    },
                    "callback_type": {"type": "string"},
                    "claim_text": {"type": "string"},
                    "old_event_fact_id": {"type": "string"},
                    "current_event_fact_id": {"type": "string"},
                    "why_now": {"type": "string"},
                    "interestingness_reason": {"type": "string"},
                    "memory_refs": {
                        "type": "array",
                        "items": {"type": "string"},
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
                "Add or update a narrative storyline supported by one or more "
                "fact IDs returned by successful save_fact calls."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[a-z][a-z0-9_-]{0,63}$",
                    },
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "supporting_fact_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "priority": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "id",
                    "headline",
                    "summary",
                    "supporting_fact_ids",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_outline",
            "description": (
                "Replace the working article outline with sections that reference "
                "facts and storylines from successful saves. The outline is optional and revisable."
            ),
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
                    }
                },
                "required": ["sections"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_brief",
            "description": (
                "Read the structured brief, readiness warnings, and managed "
                "projection status. Reading revision 0 does not create an artifact."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def register_brief_tools(registry: ToolRegistry) -> None:
    handlers: dict[str, Callable[..., str]] = {
        "save_fact": save_fact,
        "save_memory_callback": save_memory_callback,
        "save_storyline": save_storyline,
        "set_outline": set_outline,
        "read_brief": read_brief,
    }
    for spec in BRIEF_TOOL_SPECS:
        name = spec["function"]["name"]
        registry.register_context_tool(
            name,
            handlers[name],
            spec,
            BRIEF_TOOL_IMPLEMENTATION_VERSION,
        )


def save_fact(
    ctx: ToolContext,
    *,
    id: str,
    claim_text: str,
    data_refs: list[str] | None = None,
    numbers: dict[str, JsonValue] | None = None,
    category: str = "general",
    bindings: list[dict[str, Any]] | None = None,
    superlative_direction: Literal["min", "max"] | None = None,
    superlative_unique: bool = False,
    superlative_binding: dict[str, str] | None = None,
) -> str:
    # Compatibility-only legacy refs and numeric aliases are redundant inputs.
    # The selected catalog bindings own their canonical replacements.
    del data_refs, numbers

    def prepare() -> Any:
        resolved = resolve_bindings(bindings or [], ctx.evidence)
        canonical_refs = tuple(dict.fromkeys(binding.ref for binding in resolved))
        numeric_summary = binding_numbers(resolved)
        mutation = ctx.brief.prepare_fact(
            id=id,
            claim_text=claim_text,
            data_refs=canonical_refs,
            numbers=numeric_summary,
            category=category,
            bindings=resolved,
            superlative_direction=superlative_direction,
            superlative_unique=superlative_unique,
            superlative_binding=superlative_binding,
        )
        fact = mutation.candidate.get_fact(id)
        assert fact is not None
        diagnostics = validate_fact(fact, ctx.evidence)
        return ctx.brief.prepare_fact(
            id=id, claim_text=claim_text, data_refs=canonical_refs, numbers=numeric_summary,
            category=category, bindings=resolved, support_status="traceable",
            support_diagnostics=diagnostics,
            superlative_direction=superlative_direction,
            superlative_unique=superlative_unique,
            superlative_binding=superlative_binding,
        )

    return _execute_mutation(
        ctx,
        prepare,
        result_key="fact_id",
    )


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
    return _execute_mutation(
        ctx,
        lambda: ctx.brief.prepare_memory_callback(
            id=id,
            callback_type=callback_type,
            claim_text=claim_text,
            old_event_fact_id=old_event_fact_id,
            current_event_fact_id=current_event_fact_id,
            why_now=why_now,
            interestingness_reason=interestingness_reason,
            memory_refs=memory_refs or (),
            tags=tags or (),
        ),
        result_key="callback_id",
    )


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
    return _execute_mutation(
        ctx,
        lambda: ctx.brief.prepare_storyline(
            id=id,
            headline=headline,
            summary=summary,
            supporting_fact_ids=supporting_fact_ids,
            priority=priority,
            tags=tags or (),
        ),
        result_key="storyline_id",
    )


def set_outline(ctx: ToolContext, *, sections: list[dict[str, Any]]) -> str:
    return _execute_mutation(
        ctx,
        lambda: ctx.brief.prepare_outline(sections=sections),
        result_key="outline_id",
    )


def read_brief(ctx: ToolContext) -> str:
    brief = ctx.brief.brief
    projection = ctx.artifacts.artifacts.get(RESEARCH_BRIEF_PATH)
    return _success(
        {
            "brief": brief.model_dump(mode="json"),
            "readiness": brief.readiness().model_dump(mode="json"),
            "projection": (
                {
                    "path": RESEARCH_BRIEF_PATH,
                    "revision": projection.current.revision,
                    "content_hash": projection.current.content_hash,
                }
                if projection is not None
                else None
            ),
        }
    )


def _execute_mutation(
    ctx: ToolContext,
    prepare: Callable[[], Any],
    *,
    result_key: str,
) -> str:
    try:
        mutation = prepare()
    except ResearchBriefError as exc:
        return _error(exc.as_dict())
    except ValidationError as exc:
        return _error(
            {
                "code": "invalid_brief_input",
                "message": "brief input failed validation",
                "details": [
                    {
                        "loc": list(item["loc"]),
                        "msg": item["msg"],
                        "type": item["type"],
                    }
                    for item in exc.errors()
                ],
            }
        )

    brief = ctx.commit_brief_mutation(mutation)
    return _success(
        {
            result_key: mutation.entity_id,
            "brief_revision": brief.revision,
            "changed": mutation.changed,
            "readiness": brief.readiness().model_dump(mode="json"),
        }
    )


def _success(data: dict[str, Any]) -> str:
    return _json({"ok": True, **data})


def _error(error: dict[str, Any]) -> str:
    return _json({"ok": False, "error": error})


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True)


__all__ = [
    "BRIEF_TOOL_IMPLEMENTATION_VERSION",
    "BRIEF_TOOL_SPECS",
    "read_brief",
    "register_brief_tools",
    "save_fact",
    "save_memory_callback",
    "save_storyline",
    "set_outline",
]
