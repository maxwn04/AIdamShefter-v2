"""Ranked story-memory search orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reporter_memory.search.discovery import (
    _entity_keys,
    _entity_keys_from_events,
    _events_matching_entities,
    _fts_matches,
    _matching_triggers,
    _owner_for_trigger,
    _owners_for_event,
    _storylines_matching_teams,
)
from reporter_memory.search.ranking import _ensure_candidate, _hydrate_search_candidate
from reporter_memory.search.verification import _unique_entities

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


def search_story_memory(
    store: ContextStore,
    *,
    week: int,
    query: str | None = None,
    article_request: str | None = None,
    current_entities: list[dict[str, Any]] | None = None,
    current_events: list[dict[str, Any]] | None = None,
    trigger_types: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    include_resolved: bool = False,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return ranked memory leads for the current article week.

    Ranking prioritizes attention; it does not select what to write.
    """
    filters = filters or {}
    entity_keys = _entity_keys(current_entities or [])
    entity_keys.update(_entity_keys_from_events(current_events or []))
    event_type_hints = {
        str(event.get("event_type"))
        for event in (current_events or [])
        if event.get("event_type")
    }
    transaction_ids = {
        str(event["transaction_id"])
        for event in (current_events or [])
        if event.get("transaction_id")
    }
    matchup_ids = {
        str(event["matchup_id"])
        for event in (current_events or [])
        if event.get("matchup_id")
    }

    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    for trigger, match_reason in _matching_triggers(
        store,
        week=week,
        entity_keys=entity_keys,
        trigger_types=trigger_types,
    ):
        owner_type, owner_id = _owner_for_trigger(trigger)
        candidate = _ensure_candidate(candidates, owner_type, owner_id)
        candidate["matched_triggers"].append(trigger)
        candidate["score_components"]["trigger_match"] = max(
            candidate["score_components"]["trigger_match"],
            30 if match_reason == "target_week" else 20,
        )
        if match_reason == "target_week":
            candidate["why_now_parts"].append(
                f"Open {trigger['trigger_type']} trigger targets week {week}."
            )
        else:
            candidate["why_now_parts"].append(
                f"Open {trigger['trigger_type']} trigger overlaps current entities."
            )
        candidate["why_relevant_parts"].append(
            f"Trigger {trigger['id']} matched via {match_reason}."
        )

    for event_id, matched in _events_matching_entities(
        store,
        entity_keys=entity_keys,
        transaction_ids=transaction_ids,
        matchup_ids=matchup_ids,
    ):
        event = store.get_story_event(event_id)
        if event is None:
            continue
        event_entities = store.get_story_event_entities(event_id)
        for owner_type, owner_id in _owners_for_event(store, event_id):
            candidate = _ensure_candidate(candidates, owner_type, owner_id)
            if all(existing.get("id") != event["id"] for existing in candidate["linked_events"]):
                candidate["linked_events"].append(event)
            candidate["matched_entities"].extend(matched)
            overlap = len({(e["entity_type"], e["entity_id"]) for e in matched})
            candidate["score_components"]["entity_overlap"] = max(
                candidate["score_components"]["entity_overlap"],
                min(25, overlap * 5),
            )
            if event.get("event_type") in event_type_hints:
                candidate["score_components"]["event_fit"] = max(
                    candidate["score_components"]["event_fit"], 10
                )
            candidate["why_relevant_parts"].append(
                f"Event {event_id} shares entities with the current week."
            )
            candidate["matched_entity_details"] = _unique_entities(
                candidate.get("matched_entity_details", []) + event_entities
            )

    for storyline_id, matched in _storylines_matching_teams(store, entity_keys):
        candidate = _ensure_candidate(candidates, "storyline", storyline_id)
        candidate["matched_entities"].extend(matched)
        overlap = len({(e["entity_type"], e["entity_id"]) for e in matched})
        candidate["score_components"]["entity_overlap"] = max(
            candidate["score_components"]["entity_overlap"],
            min(25, overlap * 5),
        )
        candidate["why_relevant_parts"].append(
            f"Storyline {storyline_id} shares team entities with the current week."
        )

    search_text = " ".join(
        part for part in [query, article_request] if part and part.strip()
    ).strip()
    if search_text:
        for owner_type, owner_id, lexical_score in _fts_matches(store, search_text):
            candidate = _ensure_candidate(candidates, owner_type, owner_id)
            candidate["score_components"]["lexical_score"] = max(
                candidate["score_components"]["lexical_score"],
                lexical_score,
            )
            candidate["why_relevant_parts"].append(
                f"Lexical match for {search_text!r}."
            )

    if filters.get("arc_type"):
        allowed = (
            set(filters["arc_type"])
            if isinstance(filters["arc_type"], list)
            else {filters["arc_type"]}
        )
        filtered: dict[tuple[str, str], dict[str, Any]] = {}
        for key, value in candidates.items():
            if key[0] != "storyline":
                filtered[key] = value
                continue
            storyline = store.get_storyline(key[1])
            if storyline and storyline.get("arc_type") in allowed:
                filtered[key] = value
        candidates = filtered

    results: list[dict[str, Any]] = []
    for candidate in candidates.values():
        hydrated = _hydrate_search_candidate(
            store,
            candidate,
            week=week,
            include_resolved=include_resolved,
        )
        if hydrated is not None:
            results.append(hydrated)

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(1, limit)]
