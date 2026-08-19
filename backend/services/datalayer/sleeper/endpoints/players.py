"""Global Sleeper player-catalog endpoint behavior."""

from __future__ import annotations

from typing import cast

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints.contracts import (
    CompletenessFinding,
    PlayerCatalogEndpointRecords,
    PlayerRecord,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


def build_player_catalog_request(sport: str = "nfl") -> EndpointRequest:
    if sport != "nfl":
        raise ValueError("only the nfl sport scope is supported")
    return EndpointRequest(
        endpoint_kind=EndpointKind.PLAYER_CATALOG,
        scope_key=ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl"),
        path="/players/nfl",
    )


def validate_player_catalog_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    _require_player_catalog_request(request)
    if not isinstance(payload, dict):
        return _incomplete("player_catalog_payload_not_object")
    if not payload:
        return _incomplete("player_catalog_payload_empty")

    for player_id, item in payload.items():
        if not _nonempty_string(player_id) or not isinstance(item, dict):
            return _incomplete("player_catalog_entry_invalid")
        embedded_id = item.get("player_id")
        if embedded_id is not None and (
            not _nonempty_string(embedded_id) or embedded_id != player_id
        ):
            return _incomplete("player_catalog_identity_mismatch")
        if not _optional_strings_are_valid(
            item,
            "player_id",
            "full_name",
            "first_name",
            "last_name",
            "position",
            "team",
            "status",
            "injury_status",
        ):
            return _incomplete("player_catalog_string_invalid")
        active = item.get("active")
        if active is not None and not isinstance(active, bool):
            return _incomplete("player_catalog_active_invalid")
        for field in ("age", "years_exp"):
            if not _optional_nonnegative_int(item.get(field)):
                return _incomplete(f"player_catalog_{field}_invalid")
    return _complete()


def normalize_player_catalog(
    payload: JsonValue,
    request: EndpointRequest,
) -> PlayerCatalogEndpointRecords:
    finding = validate_player_catalog_completeness(payload, request)
    if not finding.is_complete:
        raise EndpointPayloadRejected(
            EndpointKind.PLAYER_CATALOG,
            cast(str, finding.reason),
            "Sleeper player_catalog payload is incomplete",
        )

    raw_catalog = cast(dict[str, JsonValue], payload)
    players: list[PlayerRecord] = []
    for player_id in sorted(raw_catalog):
        item = cast(dict[str, JsonValue], raw_catalog[player_id])
        players.append(
            PlayerRecord(
                sleeper_player_id=player_id,
                full_name=_full_name(item),
                position=cast(str | None, item.get("position")),
                nfl_team=cast(str | None, item.get("team")),
                active=cast(bool | None, item.get("active")),
                status=cast(str | None, item.get("status")),
                injury_status=cast(str | None, item.get("injury_status")),
                age=cast(int | None, item.get("age")),
                years_experience=cast(int | None, item.get("years_exp")),
                metadata=dict(item),
            )
        )
    return PlayerCatalogEndpointRecords(players=tuple(players))


def _require_player_catalog_request(request: EndpointRequest) -> None:
    if (
        request.endpoint_kind is not EndpointKind.PLAYER_CATALOG
        or request.scope_key
        != ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl")
        or request.path != "/players/nfl"
        or request.parameters
        or request.week is not None
        or request.bracket_kind is not None
    ):
        raise ValueError("request is not a canonical player_catalog request")


def _complete() -> CompletenessFinding:
    return CompletenessFinding(is_complete=True)


def _incomplete(reason: str) -> CompletenessFinding:
    return CompletenessFinding(is_complete=False, reason=reason)


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional_strings_are_valid(
    value: dict[str, JsonValue],
    *fields: str,
) -> bool:
    return all(
        value.get(field) is None or isinstance(value.get(field), str)
        for field in fields
    )


def _optional_nonnegative_int(value: JsonValue | None) -> bool:
    return value is None or (
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
    )


def _full_name(raw_player: dict[str, JsonValue]) -> str | None:
    full_name = raw_player.get("full_name")
    if isinstance(full_name, str) and full_name:
        return full_name
    first_name = raw_player.get("first_name")
    last_name = raw_player.get("last_name")
    if (
        isinstance(first_name, str)
        and first_name
        and isinstance(last_name, str)
        and last_name
    ):
        return f"{first_name} {last_name}"
    return None
