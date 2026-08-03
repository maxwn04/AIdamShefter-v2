"""Expand a single memory owner into a hydrated candidate payload."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


def normalize_owner_type(owner_type: str) -> str:
    if owner_type in {"event", "story_event"}:
        return "event"
    return owner_type


def get_memory_candidate(
    store: ContextStore, owner_type: str, owner_id: str
) -> dict[str, Any] | None:
    """Expand one memory candidate with linked evidence and history."""
    normalized_type = normalize_owner_type(owner_type)
    if normalized_type == "storyline":
        enriched = store.get_enriched_storylines([owner_id])
        if not enriched:
            return None
        storyline = enriched[0]
        events = store.get_storyline_events(owner_id)
        return {
            "owner_type": "storyline",
            "owner_id": owner_id,
            "storyline": storyline,
            "events": events,
            "triggers": store.get_storyline_triggers(owner_id, status=None),
            "persisted_facts": storyline.get("facts", []),
            "history": storyline.get("history", []),
            "source_refs": _collect_source_refs(events),
        }

    if normalized_type == "event":
        event = store.get_story_event(owner_id)
        if event is None:
            return None
        event["entities"] = store.get_story_event_entities(owner_id)
        linked_storyline_ids = store.storyline_ids_for_event(owner_id)
        return {
            "owner_type": "event",
            "owner_id": owner_id,
            "event": event,
            "linked_storylines": store.get_enriched_storylines(linked_storyline_ids),
            "triggers": [
                trigger
                for trigger in store.get_storyline_triggers(status=None)
                if trigger.get("event_id") == owner_id
            ],
            "source_refs": event.get("source_refs", []),
        }

    if normalized_type == "trigger":
        trigger = store.get_trigger(owner_id)
        if trigger is None:
            return None
        payload: dict[str, Any] = {
            "owner_type": "trigger",
            "owner_id": owner_id,
            "trigger": trigger,
            "events": [],
            "storyline": None,
            "source_refs": [],
        }
        if trigger.get("event_id"):
            event = store.get_story_event(trigger["event_id"])
            if event is not None:
                event["entities"] = store.get_story_event_entities(trigger["event_id"])
                payload["events"] = [event]
                payload["source_refs"] = event.get("source_refs", [])
        if trigger.get("storyline_id"):
            enriched = store.get_enriched_storylines([trigger["storyline_id"]])
            payload["storyline"] = enriched[0] if enriched else None
        return payload

    return None


def _collect_source_refs(events: list[dict[str, Any]]) -> list[Any]:
    refs: list[Any] = []
    seen: set[str] = set()
    for event in events:
        for ref in event.get("source_refs", []):
            key = json.dumps(ref, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                refs.append(ref)
    return refs
