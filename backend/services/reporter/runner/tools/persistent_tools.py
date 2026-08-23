"""Legacy persistent context load/save tools for reporter v2.

Search and richer write/usage tools live in memory_tools.py. This module keeps
the original load/save surface and registers both sets together.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from backend.services.reporter.runner.models import ToolDef
from backend.services.reporter.runner.tools.memory_tools import (
    MEMORY_TOOL_SPECS,
    memory_write_blocked_result,
    register_memory_tools,
)
from backend.services.reporter.runner.tools.registry import ToolRegistry


PERSISTENT_TOOL_IMPLEMENTATION_VERSION = "1"

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


LEGACY_PERSISTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_persistent_storyline",
            "description": (
                "Create or update a persistent storyline that carries across weeks. "
                "Use this for multi-week narrative arcs likely to matter in future "
                "articles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": (
                            "Stable storyline ID. Use an existing ID to update, or "
                            "a new ID like 'story_2024_w8_001' to create."
                        ),
                    },
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["active", "stale", "resolved"],
                    },
                    "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "team_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Team names or roster IDs involved in the arc.",
                    },
                },
                "required": ["id", "headline", "summary", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_team_context",
            "description": (
                "Save or update persistent narrative context for one team. This "
                "replaces that team's previous note."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {
                        "type": "string",
                        "description": "Team name or roster ID.",
                    },
                    "narrative": {
                        "type": "string",
                        "description": "Summary of the team's current situation.",
                    },
                    "outlook": {
                        "type": "string",
                        "enum": [
                            "rebuilding",
                            "contending",
                            "middling",
                            "surging",
                            "fading",
                        ],
                    },
                },
                "required": ["roster_key", "narrative"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_league_note",
            "description": (
                "Save or update a league-wide persistent note. Uses key-value pairs; "
                "the same key overwrites the previous value."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "Note key such as 'season_theme', 'trade_activity', "
                            "'rivalry_notes', or custom."
                        ),
                    },
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_persistent_storylines",
            "description": (
                "Load active and stale persistent storylines, including available "
                "history and persisted supporting facts."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_team_context",
            "description": "Load all persistent team context notes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_league_notes",
            "description": "Load all persistent league context notes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


PERSISTENT_TOOLS = LEGACY_PERSISTENT_TOOLS + MEMORY_TOOL_SPECS
PERSISTENT_TOOL_SPECS: list[ToolDef] = PERSISTENT_TOOLS


def register_persistent_tools(
    registry: ToolRegistry,
    context_store: ContextStore,
    week: int,
    resolve_roster_fn: Callable[[str], dict[str, Any]] | None = None,
    *,
    allow_memory_writes: bool = True,
) -> None:
    """Register legacy load/save tools and the agent memory tool surface."""

    def save_persistent_storyline(
        *,
        id: str,
        headline: str,
        summary: str,
        status: str,
        priority: int = 2,
        tags: list[str] | None = None,
        team_keys: list[str] | None = None,
    ) -> str:
        if not allow_memory_writes:
            return memory_write_blocked_result("save_persistent_storyline")
        # Legacy wrapper over the richer storyline memory card tool.
        handler = registry.get_handler("upsert_storyline_memory_card")
        assert handler is not None
        return handler(
            id=id,
            headline=headline,
            summary=summary,
            status=status,
            priority=priority,
            tags=tags,
            team_keys=team_keys,
        )

    def save_team_context(
        *,
        roster_key: str,
        narrative: str,
        outlook: str | None = None,
    ) -> str:
        if not allow_memory_writes:
            return memory_write_blocked_result("save_team_context")
        roster_id = _resolve_roster_id(roster_key, resolve_roster_fn)
        if roster_id is None:
            return _json(
                {
                    "ok": False,
                    "saved": False,
                    "error": f"Could not resolve team: {roster_key}",
                }
            )

        context_store.upsert_team_context(
            roster_id,
            narrative,
            outlook,
            week=week,
        )
        return _json(
            {
                "ok": True,
                "saved": True,
                "roster_id": roster_id,
                "roster_key": roster_key,
            }
        )

    def save_league_note(*, key: str, value: str) -> str:
        if not allow_memory_writes:
            return memory_write_blocked_result("save_league_note")
        context_store.upsert_league_context(key, value, week=week)
        return _json({"ok": True, "saved": True, "key": key})

    def load_persistent_storylines() -> str:
        storylines = context_store.get_storylines()
        enriched = context_store.get_enriched_storylines(
            [storyline["id"] for storyline in storylines]
        )
        return _json(enriched)

    def load_team_context() -> str:
        return _json(context_store.get_all_team_context())

    def load_league_notes() -> str:
        return _json(context_store.get_league_context())

    handlers = {
        "save_persistent_storyline": save_persistent_storyline,
        "save_team_context": save_team_context,
        "save_league_note": save_league_note,
        "load_persistent_storylines": load_persistent_storylines,
        "load_team_context": load_team_context,
        "load_league_notes": load_league_notes,
    }
    for spec in LEGACY_PERSISTENT_TOOLS:
        name = spec["function"]["name"]
        registry.register(
            name,
            handlers[name],
            spec,
            PERSISTENT_TOOL_IMPLEMENTATION_VERSION,
        )

    register_memory_tools(
        registry,
        context_store,
        week=week,
        resolve_roster_fn=resolve_roster_fn,
        allow_memory_writes=allow_memory_writes,
    )


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
