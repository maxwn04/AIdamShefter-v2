"""Verification planning and fact-link helpers for memory callbacks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reporter_memory.search.candidates import get_memory_candidate, normalize_owner_type

if TYPE_CHECKING:
    from reporter_memory.context_store import ContextStore


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
