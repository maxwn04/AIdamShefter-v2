"""Candidate discovery helpers for story memory search."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reporter_memory.search.candidates import normalize_owner_type
from reporter_memory.search.verification import _unique_entities

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


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
