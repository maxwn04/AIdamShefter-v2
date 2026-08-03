"""Agent-facing memory search and candidate expansion.

Uses ContextStore for SQL/CRUD; this module owns ranking, lead shaping, and
verification hints for reporter tools.
"""

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


def _owners_for_event(
    store: ContextStore, event_id: str
) -> list[tuple[str, str]]:
    storyline_ids = store.storyline_ids_for_event(event_id)
    if storyline_ids:
        return [("storyline", storyline_id) for storyline_id in storyline_ids]
    return [("event", event_id)]


def _owner_for_trigger(trigger: dict[str, Any]) -> tuple[str, str]:
    if trigger.get("storyline_id"):
        return "storyline", trigger["storyline_id"]
    if trigger.get("event_id"):
        return "event", trigger["event_id"]
    return "trigger", trigger["id"]


def _entity_keys(entities: list[dict[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for entity in entities:
        entity_type = entity.get("entity_type", entity.get("type"))
        entity_id = entity.get("entity_id", entity.get("id"))
        if entity_type is None or entity_id is None:
            continue
        keys.add((str(entity_type), str(entity_id).strip()))
    return keys


def _entity_keys_from_events(events: list[dict[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for event in events:
        keys.update(_entity_keys(event.get("entities", [])))
        if event.get("transaction_id"):
            keys.add(("transaction", str(event["transaction_id"])))
        if event.get("matchup_id"):
            keys.add(("matchup", str(event["matchup_id"])))
    return keys


def _condition_entity_values(condition: dict[str, Any]) -> set[str]:
    values: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_l = str(key).lower()
                if any(
                    token in key_l
                    for token in (
                        "id",
                        "roster",
                        "team",
                        "player",
                        "manager",
                        "transaction",
                        "matchup",
                    )
                ):
                    if value is not None and not isinstance(value, (dict, list)):
                        values.add(str(value))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(condition)
    return values


def _matching_triggers(
    store: ContextStore,
    *,
    week: int,
    entity_keys: set[tuple[str, str]],
    trigger_types: list[str] | None,
) -> list[tuple[dict[str, Any], str]]:
    allowed_types = set(trigger_types) if trigger_types else None
    entity_values = {entity_id for _, entity_id in entity_keys}
    matches: list[tuple[dict[str, Any], str]] = []
    for trigger in store.get_storyline_triggers(status="open"):
        if allowed_types is not None and trigger["trigger_type"] not in allowed_types:
            continue
        if trigger.get("target_week") == week:
            matches.append((trigger, "target_week"))
            continue
        condition_values = _condition_entity_values(trigger.get("condition", {}))
        if condition_values & entity_values:
            matches.append((trigger, "entity_overlap"))
    return matches


def _events_matching_entities(
    store: ContextStore,
    *,
    entity_keys: set[tuple[str, str]],
    transaction_ids: set[str],
    matchup_ids: set[str],
) -> list[tuple[str, list[dict[str, Any]]]]:
    matched: dict[str, list[dict[str, Any]]] = {}

    for entity_type, entity_id in entity_keys:
        for row in store.find_event_entities(entity_type, entity_id):
            matched.setdefault(row["event_id"], []).append(row)

    for event_id in store.find_event_ids_by_transaction_ids(transaction_ids):
        matched.setdefault(event_id, []).append(
            {
                "entity_type": "transaction",
                "entity_id": event_id,
                "display_name": None,
                "role": "transaction",
            }
        )

    for event_id in store.find_event_ids_by_matchup_ids(matchup_ids):
        matched.setdefault(event_id, []).append(
            {
                "entity_type": "matchup",
                "entity_id": event_id,
                "display_name": None,
                "role": "matchup",
            }
        )

    return [
        (event_id, _unique_entities(entities))
        for event_id, entities in matched.items()
    ]


def _storylines_matching_teams(
    store: ContextStore, entity_keys: set[tuple[str, str]]
) -> list[tuple[str, list[dict[str, Any]]]]:
    results: list[tuple[str, list[dict[str, Any]]]] = []
    for entity_type, entity_id in entity_keys:
        if entity_type != "team":
            continue
        try:
            team_id = int(entity_id)
        except (TypeError, ValueError):
            continue
        for storyline_id in store.find_storyline_ids_by_team_id(team_id):
            results.append(
                (
                    storyline_id,
                    [
                        {
                            "entity_type": "team",
                            "entity_id": str(team_id),
                            "display_name": None,
                            "role": "team",
                        }
                    ],
                )
            )
    return results


def _fts_matches(
    store: ContextStore, search_text: str
) -> list[tuple[str, str, float]]:
    match_query = _fts_match_query(search_text)
    if not match_query:
        return []

    results: list[tuple[str, str, float]] = []
    for row in store.search_memory_fts(match_query, limit=50):
        raw = float(row["rank"])
        lexical_score = max(1.0, min(20.0, 10.0 - raw))
        owner_type = normalize_owner_type(row["owner_type"])
        if owner_type == "trigger":
            trigger = store.get_trigger(row["owner_id"])
            if trigger is None:
                continue
            owner_type, owner_id = _owner_for_trigger(trigger)
        else:
            owner_id = row["owner_id"]
        results.append((owner_type, owner_id, lexical_score))
    return results


def _fts_match_query(search_text: str) -> str:
    tokens = [
        token.strip().strip('"').replace('"', "")
        for token in search_text.replace(",", " ").split()
        if token.strip()
    ]
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens if token)


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


REQUIRED_VERIFICATION_ROLES = ("origin_receipt", "current_payoff")


def plan_memory_verification(
    store: ContextStore,
    *,
    candidate_id: str,
    owner_type: str = "storyline",
    current_week: int,
    callback_id: str | None = None,
    intended_callback_claim: str | None = None,
) -> dict[str, Any] | None:
    """Build required fact roles and suggested datalayer calls for a candidate."""
    candidate = get_memory_candidate(store, owner_type, candidate_id)
    if candidate is None:
        return None

    events = _candidate_events(candidate)
    triggers = _candidate_triggers(candidate)
    entities = _candidate_entities(candidate, events)

    event_type = next(
        (event.get("event_type") for event in events if event.get("event_type")),
        None,
    )
    trigger_type = next(
        (
            trigger.get("trigger_type")
            for trigger in triggers
            if trigger.get("trigger_type")
        ),
        None,
    )
    origin_week = next(
        (int(event["week"]) for event in events if event.get("week") is not None),
        None,
    )

    required_fact_roles, suggested_calls = _verification_hints(
        event_type=event_type,
        trigger_type=trigger_type,
        week=current_week,
        origin_week=origin_week,
        entities=entities,
    )

    persisted_facts: list[dict[str, Any]] = []
    if candidate.get("owner_type") == "storyline":
        persisted_facts = list(candidate.get("persisted_facts") or [])
    elif candidate.get("storyline") and isinstance(candidate["storyline"], dict):
        persisted_facts = list(candidate["storyline"].get("facts") or [])

    return {
        "found": True,
        "owner_type": normalize_owner_type(owner_type),
        "owner_id": candidate_id,
        "callback_id": callback_id,
        "intended_callback_claim": intended_callback_claim,
        "current_week": current_week,
        "origin_week": origin_week,
        "event_type": event_type,
        "trigger_type": trigger_type,
        "entities": _unique_entities(entities),
        "linked_events": events,
        "matched_triggers": triggers,
        "persisted_facts": persisted_facts,
        "source_refs": candidate.get("source_refs", []),
        "required_fact_roles": required_fact_roles,
        "suggested_datalayer_calls": suggested_calls,
        "verification_policy": {
            "minimum_roles_for_verified": list(REQUIRED_VERIFICATION_ROLES),
            "note": (
                "Save old-event and current-event facts before "
                "save_memory_callback. record_memory_verification(status="
                "'verified') requires origin_receipt and current_payoff."
            ),
        },
    }


def normalize_verification_fact_links(
    fact_links: list[Any] | None,
) -> list[dict[str, str]]:
    """Normalize fact_links into [{role, fact_id}, ...]."""
    normalized: list[dict[str, str]] = []
    for item in fact_links or []:
        if isinstance(item, str):
            fact_id = item.strip()
            if fact_id:
                normalized.append({"role": "", "fact_id": fact_id})
            continue
        if not isinstance(item, dict):
            continue
        fact_id = str(item.get("fact_id") or item.get("id") or "").strip()
        if not fact_id:
            continue
        role = str(item.get("role") or item.get("fact_role") or "").strip()
        normalized.append({"role": role, "fact_id": fact_id})
    return normalized


def validate_verified_fact_links(
    fact_links: list[dict[str, str]],
) -> list[str]:
    """Return missing required roles when marking a callback verified."""
    roles = {link["role"] for link in fact_links if link.get("role")}
    return [
        role for role in REQUIRED_VERIFICATION_ROLES if role not in roles
    ]


def _candidate_events(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    if candidate.get("owner_type") == "event" and candidate.get("event"):
        return [candidate["event"]]
    events = candidate.get("events") or candidate.get("linked_events") or []
    return list(events)


def _candidate_triggers(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    if candidate.get("owner_type") == "trigger" and candidate.get("trigger"):
        return [candidate["trigger"]]
    return list(candidate.get("triggers") or candidate.get("matched_triggers") or [])


def _candidate_entities(
    candidate: dict[str, Any], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for event in events:
        entities.extend(event.get("entities") or [])
    storyline = candidate.get("storyline")
    if isinstance(storyline, dict):
        for team_id in storyline.get("team_ids") or []:
            entities.append(
                {
                    "entity_type": "team",
                    "entity_id": str(team_id),
                    "role": "storyline_team",
                }
            )
    return entities


def _verification_hints(
    *,
    event_type: str | None,
    trigger_type: str | None,
    week: int,
    origin_week: int | None = None,
    entities: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    roles = list(REQUIRED_VERIFICATION_ROLES)
    calls: list[str] = []
    kind = trigger_type or event_type
    entity_list = entities or []
    team_keys = _entity_call_values(entity_list, "team")
    player_keys = _entity_call_values(entity_list, "player")
    team_key = team_keys[0] if team_keys else "?"
    player_key = player_keys[0] if player_keys else "?"
    origin = origin_week if origin_week is not None else "?"

    if kind in {"trade", "trade_evaluation"}:
        calls.append(f"transactions(week_from={origin}, week_to={origin})")
        calls.append(f"team_game(roster_key={team_key}, week={week})")
        if player_key != "?":
            calls.append(
                f"player_weekly_log(player_key={player_key}, "
                f"week_from={origin}, week_to={week})"
            )
    elif kind in {"rematch", "matchup"}:
        calls.append(f"team_game(roster_key={team_key}, week={week})")
        if origin_week is not None:
            calls.append(f"team_game(roster_key={team_key}, week={origin})")
        calls.append(f"team_dossier(roster_key={team_key}, week={week})")
    elif kind in {"playoff_path", "playoff"}:
        calls.append("playoff_bracket()")
        calls.append(f"team_playoff_path(roster_key={team_key})")
    elif kind in {"player_against_former_team", "waiver_player_started", "waiver"}:
        calls.append(
            f"player_weekly_log(player_key={player_key}, "
            f"week_from={origin}, week_to={week})"
        )
        calls.append(f"team_game(roster_key={team_key}, week={week})")
    elif kind == "standings_swing":
        calls.append(f"league_snapshot(week={week})")
        calls.append(f"team_dossier(roster_key={team_key}, week={week})")
    else:
        calls.append(f"league_snapshot(week={week})")
        calls.append(f"team_game(roster_key={team_key}, week={week})")
    return roles, calls


def _entity_call_values(
    entities: list[dict[str, Any]], entity_type: str
) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        if str(entity.get("entity_type", entity.get("type", ""))) != entity_type:
            continue
        raw = entity.get("display_name") or entity.get("entity_id") or entity.get("id")
        if raw is None:
            continue
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _unique_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for entity in entities:
        entity_type = str(entity.get("entity_type", entity.get("type", "")))
        entity_id = str(entity.get("entity_id", entity.get("id", "")))
        role = str(entity.get("role", ""))
        key = (entity_type, entity_id, role)
        if not entity_type or not entity_id or key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "display_name": entity.get("display_name", entity.get("name")),
                "role": role,
            }
        )
    return unique
