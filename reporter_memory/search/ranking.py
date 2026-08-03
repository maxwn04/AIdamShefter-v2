"""Candidate merge, hydration, and score assembly."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from reporter_memory.search.candidates import _collect_source_refs
from reporter_memory.search.verification import _unique_entities, _verification_hints

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


def _ensure_candidate(
    candidates: dict[tuple[str, str], dict[str, Any]],
    owner_type: str,
    owner_id: str,
) -> dict[str, Any]:
    key = (owner_type, owner_id)
    if key not in candidates:
        candidates[key] = {
            "owner_type": owner_type,
            "owner_id": owner_id,
            "matched_triggers": [],
            "matched_entities": [],
            "matched_entity_details": [],
            "linked_events": [],
            "why_relevant_parts": [],
            "why_now_parts": [],
            "score_components": {
                "trigger_match": 0.0,
                "entity_overlap": 0.0,
                "event_fit": 0.0,
                "lexical_score": 0.0,
                "importance": 0.0,
                "confidence": 0.0,
                "dormant_callback_boost": 0.0,
                "light_recency_bonus": 0.0,
                "resolved_penalty": 0.0,
            },
        }
    return candidates[key]


def _hydrate_search_candidate(
    store: ContextStore,
    candidate: dict[str, Any],
    *,
    week: int,
    include_resolved: bool,
) -> dict[str, Any] | None:
    owner_type = candidate["owner_type"]
    owner_id = candidate["owner_id"]
    components = candidate["score_components"]

    headline = None
    summary = None
    status = None
    importance = 0
    confidence = "needs_verification"
    last_accessed_week = None
    week_last_updated = None
    event_type = None
    trigger_type = None

    if owner_type == "storyline":
        storyline = store.get_storyline(owner_id)
        if storyline is None:
            return None
        if storyline["status"] == "resolved" and not include_resolved:
            return None
        headline = storyline["headline"]
        summary = storyline["summary"]
        status = storyline["status"]
        importance = int(storyline.get("importance") or 0)
        last_accessed_week = storyline.get("last_accessed_week")
        week_last_updated = storyline.get("week_last_updated")
        if not candidate["linked_events"]:
            candidate["linked_events"] = [
                {
                    "id": event["id"],
                    "week": event["week"],
                    "event_type": event["event_type"],
                    "headline": event["headline"],
                    "confidence": event["confidence"],
                    "source_refs": event.get("source_refs", []),
                    "link_type": event.get("link_type"),
                }
                for event in store.get_storyline_events(owner_id)
            ]
        if not candidate["matched_triggers"]:
            candidate["matched_triggers"] = store.get_storyline_triggers(owner_id)

    elif owner_type == "event":
        event = store.get_story_event(owner_id)
        if event is None:
            return None
        headline = event["headline"]
        summary = event["summary"]
        status = event["confidence"]
        importance = int(event.get("importance") or 0)
        confidence = event.get("confidence", "needs_verification")
        last_accessed_week = event.get("last_accessed_week")
        week_last_updated = event.get("week")
        event_type = event.get("event_type")
        if all(existing.get("id") != event["id"] for existing in candidate["linked_events"]):
            candidate["linked_events"] = [event]

    elif owner_type == "trigger":
        trigger = store.get_trigger(owner_id)
        if trigger is None:
            return None
        headline = trigger["trigger_type"]
        summary = json.dumps(trigger.get("condition", {}), default=str)
        status = trigger["status"]
        trigger_type = trigger["trigger_type"]
        importance = 4
        if all(
            existing.get("id") != trigger["id"]
            for existing in candidate["matched_triggers"]
        ):
            candidate["matched_triggers"] = [trigger]
    else:
        return None

    components["importance"] = float(importance)
    confidence_scores = {
        "verified": 5.0,
        "inferred": 2.0,
        "needs_verification": 0.0,
    }
    if owner_type == "event":
        components["confidence"] = confidence_scores.get(confidence, 0.0)
    elif owner_type == "storyline" and candidate["linked_events"]:
        components["confidence"] = max(
            (
                confidence_scores.get(event.get("confidence", ""), 0.0)
                for event in candidate["linked_events"]
            ),
            default=0.0,
        )

    if last_accessed_week is None or (week - int(last_accessed_week)) >= 3:
        components["dormant_callback_boost"] = 8.0
    if week_last_updated is not None:
        age = max(0, week - int(week_last_updated))
        components["light_recency_bonus"] = max(0.0, 3.0 - (age * 0.25))
    if status == "resolved":
        components["resolved_penalty"] = 50.0

    score = (
        components["trigger_match"]
        + components["entity_overlap"]
        + components["event_fit"]
        + components["lexical_score"]
        + components["importance"]
        + components["confidence"]
        + components["dormant_callback_boost"]
        + components["light_recency_bonus"]
        - components["resolved_penalty"]
    )

    required_fact_roles, suggested_calls = _verification_hints(
        event_type=event_type
        or next(
            (
                event.get("event_type")
                for event in candidate["linked_events"]
                if event.get("event_type")
            ),
            None,
        ),
        trigger_type=trigger_type
        or next(
            (
                trigger.get("trigger_type")
                for trigger in candidate["matched_triggers"]
                if trigger.get("trigger_type")
            ),
            None,
        ),
        week=week,
    )

    why_relevant = " ".join(dict.fromkeys(candidate["why_relevant_parts"])) or (
        "Memory candidate matched current search inputs."
    )
    why_now = " ".join(dict.fromkeys(candidate["why_now_parts"])) or (
        "Candidate may change meaning of current-week events."
    )

    return {
        "owner_type": owner_type,
        "owner_id": owner_id,
        "headline": headline,
        "summary": summary,
        "status": status,
        "score": round(score, 3),
        "score_components": {
            key: round(value, 3) for key, value in components.items()
        },
        "matched_entities": _unique_entities(
            candidate["matched_entities"] + candidate.get("matched_entity_details", [])
        ),
        "matched_triggers": candidate["matched_triggers"],
        "linked_events": candidate["linked_events"],
        "source_refs": _collect_source_refs(candidate["linked_events"]),
        "why_relevant": why_relevant,
        "why_now": why_now,
        "verification_status": (
            "verified" if components["confidence"] >= 5 else "needs_verification"
        ),
        "required_fact_roles": required_fact_roles,
        "suggested_datalayer_calls": suggested_calls,
    }
