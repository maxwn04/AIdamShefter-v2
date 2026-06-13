"""Context tool definitions and handlers for persistent agent memory.

Provides CONTEXT_TOOLS (OpenAI function-calling format) and
create_context_tool_handlers() to wire them up to a ContextStore.
"""

from __future__ import annotations

from typing import Any, Callable

from reporter_memory.context_store import ContextStore


CONTEXT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_storyline",
            "description": (
                "Create or update a persistent storyline that carries across weeks. "
                "Use for multi-week narrative arcs (comeback seasons, rivalry matchups, "
                "trade impacts). Set status to 'resolved' when the arc is complete."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": (
                            "Storyline ID. Use existing ID to update, or new ID "
                            "(e.g. 'story_2024_w8_001') to create."
                        ),
                    },
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["active", "resolved"],
                    },
                    "priority": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "team_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Team names or roster_ids involved.",
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
                "Save or update the running narrative context for a team. "
                "This is your memory of this team's situation — strategy, trajectory, "
                "key storylines. Replaces the previous note."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "roster_key": {"type": "string"},
                    "narrative": {
                        "type": "string",
                        "description": (
                            "Free-text summary of the team's current situation "
                            "and trajectory."
                        ),
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
                "Save a league-wide contextual note (season themes, trade deadline "
                "summary, etc). Uses key-value pairs — same key overwrites previous value."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "Note key: 'season_theme', 'trade_activity', "
                            "'rivalry_notes', or custom."
                        ),
                    },
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
    },
]


def create_context_tool_handlers(
    store: ContextStore,
    week: int,
    resolve_roster_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Callable[..., Any]]:
    """Create handler functions for context tools.

    Args:
        store: The ContextStore instance.
        week: Current week number (used for upsert timestamps).
        resolve_roster_fn: Optional function to resolve roster_key to roster_id.
            Signature: (roster_key) -> dict with 'found' and 'roster_id'.
            If not provided, roster_key is used as-is (must be int-like).
    """

    def _resolve_roster_id(roster_key: str) -> int | None:
        if resolve_roster_fn:
            result = resolve_roster_fn(roster_key)
            if result.get("found"):
                return int(result["roster_id"])
            return None
        try:
            return int(roster_key)
        except (ValueError, TypeError):
            return None

    def save_storyline(
        id: str,
        headline: str,
        summary: str,
        status: str,
        priority: int = 2,
        tags: list[str] | None = None,
        team_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        team_ids = []
        if team_keys:
            for key in team_keys:
                rid = _resolve_roster_id(key)
                if rid is not None:
                    team_ids.append(rid)

        store.upsert_storyline(
            {
                "id": id,
                "headline": headline,
                "summary": summary,
                "status": status,
                "priority": priority,
                "tags": tags or [],
                "team_ids": team_ids,
            },
            week=week,
        )
        return {"saved": True, "id": id, "status": status}

    def save_team_context(
        roster_key: str,
        narrative: str,
        outlook: str | None = None,
    ) -> dict[str, Any]:
        rid = _resolve_roster_id(roster_key)
        if rid is None:
            return {"saved": False, "error": f"Could not resolve team: {roster_key}"}
        store.upsert_team_context(rid, narrative, outlook, week=week)
        return {"saved": True, "roster_id": rid, "roster_key": roster_key}

    def save_league_note(key: str, value: str) -> dict[str, Any]:
        store.upsert_league_context(key, value, week=week)
        return {"saved": True, "key": key}

    return {
        "save_storyline": save_storyline,
        "save_team_context": save_team_context,
        "save_league_note": save_league_note,
    }
