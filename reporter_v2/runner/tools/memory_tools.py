"""Agent-facing storyline memory search and write tools."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from reporter_memory.search import get_memory_candidate, search_story_memory
from reporter_v2.runner.models import ToolDef
from reporter_v2.runner.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_story_memory",
            "description": (
                "Search persistent story memory for ranked leads relevant to the "
                "current article. Returns candidates with score components, matched "
                "triggers/entities, and verification hints. Leads are not article-"
                "ready facts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "week": {
                        "type": "integer",
                        "description": "Article week. Defaults to the current run week.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Free-text memory search query.",
                    },
                    "article_request": {
                        "type": "string",
                        "description": "Optional article request text for lexical hints.",
                    },
                    "current_entities": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": (
                            "Entities involved this week. Prefer "
                            "{entity_type, entity_id, display_name?}."
                        ),
                    },
                    "current_events": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": (
                            "Current-week events with optional event_type, "
                            "transaction_id, matchup_id, and entities."
                        ),
                    },
                    "trigger_types": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "filters": {"type": "object"},
                    "include_resolved": {"type": "boolean", "default": False},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 25,
                        "default": 10,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory_candidate",
            "description": (
                "Expand one memory candidate with linked events, persisted facts, "
                "history, triggers, and source refs. Use after search_story_memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner_type": {
                        "type": "string",
                        "enum": ["storyline", "event", "trigger", "story_event"],
                    },
                    "owner_id": {"type": "string"},
                },
                "required": ["owner_type", "owner_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory_event",
            "description": (
                "Save source-backed event evidence for later callbacks. "
                "confidence=verified requires at least one source_ref."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "event_type": {"type": "string"},
                    "week": {"type": "integer"},
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "importance": {"type": "integer"},
                    "confidence": {
                        "type": "string",
                        "enum": ["verified", "inferred", "needs_verification"],
                    },
                    "source_refs": {
                        "type": "array",
                        "items": {},
                    },
                    "numbers": {"type": "object"},
                    "entities": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "transaction_id": {"type": "string"},
                    "matchup_id": {"type": "string"},
                },
                "required": ["id", "event_type", "week", "headline", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upsert_storyline_memory_card",
            "description": (
                "Create or update a storyline memory card with optional evidence "
                "event links and trigger specs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["active", "stale", "resolved"],
                    },
                    "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                    "importance": {"type": "integer"},
                    "arc_type": {"type": "string"},
                    "origin_week": {"type": "integer"},
                    "future_callback_condition": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "team_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Optional entities; team entities become team_ids.",
                    },
                    "evidence_event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "trigger_specs": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["id", "headline", "summary", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_storyline_trigger",
            "description": "Save or update a dormant callback trigger.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "storyline_id": {"type": "string"},
                    "event_id": {"type": "string"},
                    "trigger_type": {"type": "string"},
                    "target_week": {"type": "integer"},
                    "condition": {"type": "object"},
                    "fire_policy": {
                        "type": "string",
                        "enum": ["one_shot", "recurring", "until_resolved"],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "fired", "expired", "resolved"],
                    },
                },
                "required": ["trigger_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_memory_used",
            "description": (
                "Record how a memory candidate was used this week. For one-shot "
                "triggers, article_callback marks fired and discarded marks resolved."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "owner_type": {
                        "type": "string",
                        "enum": ["storyline", "event", "trigger", "story_event"],
                        "default": "storyline",
                    },
                    "week": {"type": "integer"},
                    "usage": {
                        "type": "string",
                        "enum": [
                            "article_callback",
                            "research_context",
                            "discarded",
                        ],
                    },
                    "linked_storyline_id": {"type": "string"},
                    "fact_links": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "reason": {"type": "string"},
                },
                "required": ["candidate_id", "usage"],
            },
        },
    },
]


MEMORY_TOOL_SPECS: list[ToolDef] = MEMORY_TOOLS


def register_memory_tools(
    registry: ToolRegistry,
    context_store: ContextStore,
    week: int,
    resolve_roster_fn: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    """Register search and write/usage memory tools."""
    week_default = week

    def search_story_memory_tool(
        *,
        week: int | None = None,
        query: str | None = None,
        article_request: str | None = None,
        current_entities: list[dict[str, Any]] | None = None,
        current_events: list[dict[str, Any]] | None = None,
        trigger_types: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        include_resolved: bool = False,
        limit: int = 10,
    ) -> str:
        results = search_story_memory(
            context_store,
            week=week if week is not None else week_default,
            query=query,
            article_request=article_request,
            current_entities=current_entities,
            current_events=current_events,
            trigger_types=trigger_types,
            filters=filters,
            include_resolved=include_resolved,
            limit=limit,
        )
        return _json({"ok": True, "candidates": results, "count": len(results)})

    def get_memory_candidate_tool(*, owner_type: str, owner_id: str) -> str:
        candidate = get_memory_candidate(context_store, owner_type, owner_id)
        if candidate is None:
            return _json(
                {
                    "ok": False,
                    "found": False,
                    "error": f"No candidate for {owner_type}:{owner_id}",
                }
            )
        return _json({"ok": True, "found": True, "candidate": candidate})

    def save_memory_event(
        *,
        id: str,
        event_type: str,
        week: int,
        headline: str,
        summary: str,
        importance: int = 1,
        confidence: str = "needs_verification",
        source_refs: list[Any] | None = None,
        numbers: dict[str, Any] | None = None,
        entities: list[dict[str, Any]] | None = None,
        transaction_id: str | None = None,
        matchup_id: str | None = None,
    ) -> str:
        try:
            context_store.upsert_story_event(
                {
                    "id": id,
                    "event_type": event_type,
                    "week": week,
                    "headline": headline,
                    "summary": summary,
                    "importance": importance,
                    "confidence": confidence,
                    "source_refs": source_refs or [],
                    "numbers": numbers or {},
                    "transaction_id": transaction_id,
                    "matchup_id": matchup_id,
                }
            )
        except ValueError as exc:
            return _json({"ok": False, "saved": False, "error": str(exc)})

        if entities is not None:
            context_store.replace_story_event_entities(id, entities)
        return _json({"ok": True, "saved": True, "id": id, "confidence": confidence})

    def upsert_storyline_memory_card(
        *,
        id: str,
        headline: str,
        summary: str,
        status: str,
        priority: int = 2,
        importance: int | None = None,
        arc_type: str | None = None,
        origin_week: int | None = None,
        future_callback_condition: str | None = None,
        tags: list[str] | None = None,
        team_keys: list[str] | None = None,
        entities: list[dict[str, Any]] | None = None,
        evidence_event_ids: list[str] | None = None,
        trigger_specs: list[dict[str, Any]] | None = None,
    ) -> str:
        team_ids, unresolved_team_keys = _resolve_team_keys(
            team_keys or [], resolve_roster_fn
        )
        for entity in entities or []:
            entity_type = entity.get("entity_type", entity.get("type"))
            if entity_type != "team":
                continue
            entity_id = entity.get("entity_id", entity.get("id"))
            try:
                team_ids.append(int(entity_id))
            except (TypeError, ValueError):
                unresolved_team_keys.append(str(entity_id))

        # Deduplicate while preserving order.
        deduped_team_ids = list(dict.fromkeys(team_ids))

        storyline: dict[str, Any] = {
            "id": id,
            "headline": headline,
            "summary": summary,
            "status": status,
            "priority": priority,
            "tags": tags or [],
            "team_ids": deduped_team_ids,
        }
        if importance is not None:
            storyline["importance"] = importance
        if arc_type is not None:
            storyline["arc_type"] = arc_type
        if origin_week is not None:
            storyline["origin_week"] = origin_week
        if future_callback_condition is not None:
            storyline["future_callback_condition"] = future_callback_condition

        context_store.upsert_storyline(storyline, week=week_default)

        linked_events: list[str] = []
        for event_id in evidence_event_ids or []:
            context_store.link_storyline_event(id, event_id, "evidence")
            linked_events.append(event_id)

        saved_triggers: list[str] = []
        for spec in trigger_specs or []:
            trigger_id = spec.get("id") or f"trigger_{id}_{uuid.uuid4().hex[:8]}"
            context_store.upsert_storyline_trigger(
                {
                    "id": trigger_id,
                    "storyline_id": id,
                    "event_id": spec.get("event_id"),
                    "trigger_type": spec["trigger_type"],
                    "target_week": spec.get("target_week"),
                    "condition": spec.get("condition", {}),
                    "fire_policy": spec.get("fire_policy", "one_shot"),
                    "status": spec.get("status", "open"),
                }
            )
            saved_triggers.append(trigger_id)

        payload: dict[str, Any] = {
            "ok": True,
            "saved": True,
            "id": id,
            "status": status,
            "team_ids": deduped_team_ids,
            "linked_events": linked_events,
            "triggers": saved_triggers,
        }
        if unresolved_team_keys:
            payload["unresolved_team_keys"] = unresolved_team_keys
        return _json(payload)

    def save_storyline_trigger(
        *,
        trigger_type: str,
        id: str | None = None,
        storyline_id: str | None = None,
        event_id: str | None = None,
        target_week: int | None = None,
        condition: dict[str, Any] | None = None,
        fire_policy: str = "one_shot",
        status: str = "open",
    ) -> str:
        trigger_id = id or f"trigger_{uuid.uuid4().hex[:12]}"
        context_store.upsert_storyline_trigger(
            {
                "id": trigger_id,
                "storyline_id": storyline_id,
                "event_id": event_id,
                "trigger_type": trigger_type,
                "target_week": target_week,
                "condition": condition or {},
                "fire_policy": fire_policy,
                "status": status,
            }
        )
        return _json(
            {
                "ok": True,
                "saved": True,
                "id": trigger_id,
                "trigger_type": trigger_type,
                "status": status,
            }
        )

    def mark_memory_used(
        *,
        candidate_id: str,
        usage: str,
        owner_type: str = "storyline",
        week: int | None = None,
        linked_storyline_id: str | None = None,
        fact_links: list[str] | None = None,
        reason: str | None = None,
    ) -> str:
        used_week = week if week is not None else week_default
        normalized_type = (
            "event" if owner_type == "story_event" else owner_type
        )
        access_id = context_store.record_memory_access(
            owner_type=normalized_type,
            owner_id=candidate_id,
            week=used_week,
            usage=usage,
            linked_storyline_id=linked_storyline_id,
            fact_links=fact_links,
            reason=reason,
        )

        trigger_update = None
        if normalized_type == "trigger":
            trigger = context_store.get_trigger(candidate_id)
            if trigger and trigger.get("fire_policy", "one_shot") == "one_shot":
                if usage == "article_callback":
                    context_store.update_trigger_status(
                        candidate_id, status="fired", fired_week=used_week
                    )
                    trigger_update = "fired"
                elif usage == "discarded":
                    context_store.update_trigger_status(
                        candidate_id, status="resolved", fired_week=used_week
                    )
                    trigger_update = "resolved"

        return _json(
            {
                "ok": True,
                "recorded": True,
                "access_id": access_id,
                "candidate_id": candidate_id,
                "owner_type": normalized_type,
                "usage": usage,
                "trigger_update": trigger_update,
            }
        )

    handlers = {
        "search_story_memory": search_story_memory_tool,
        "get_memory_candidate": get_memory_candidate_tool,
        "save_memory_event": save_memory_event,
        "upsert_storyline_memory_card": upsert_storyline_memory_card,
        "save_storyline_trigger": save_storyline_trigger,
        "mark_memory_used": mark_memory_used,
    }
    for spec in MEMORY_TOOL_SPECS:
        name = spec["function"]["name"]
        registry.register(name, handlers[name], spec)


def _resolve_team_keys(
    team_keys: list[str],
    resolve_roster_fn: Callable[[str], dict[str, Any]] | None,
) -> tuple[list[int], list[str]]:
    team_ids: list[int] = []
    unresolved_team_keys: list[str] = []
    for key in team_keys:
        roster_id = _resolve_roster_id(key, resolve_roster_fn)
        if roster_id is None:
            unresolved_team_keys.append(key)
        else:
            team_ids.append(roster_id)
    return team_ids, unresolved_team_keys


def _resolve_roster_id(
    roster_key: str,
    resolve_roster_fn: Callable[[str], dict[str, Any]] | None,
) -> int | None:
    if resolve_roster_fn is not None:
        result = resolve_roster_fn(roster_key)
        if result.get("found"):
            return int(result["roster_id"])
        return None

    try:
        return int(roster_key)
    except (TypeError, ValueError):
        return None


def _json(payload: Any) -> str:
    return json.dumps(payload, default=str)
