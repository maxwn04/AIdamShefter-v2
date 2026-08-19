"""Winners- and losers-bracket endpoint behavior."""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints._shared import (
    complete,
    incomplete,
    integer,
    optional_integer,
    payload_list,
    payload_object,
    reject,
    validated_league_id,
    validated_season_id,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    BracketMatchupRecord,
    CompletenessFinding,
    LosersBracketEndpointRecords,
    WinnersBracketEndpointRecords,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


BracketKind = Literal["winners", "losers"]


def build_winners_bracket_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    return _build_bracket_request(
        EndpointKind.WINNERS_BRACKET,
        competition_season_id,
        sleeper_league_id,
        "winners",
    )


def build_losers_bracket_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    return _build_bracket_request(
        EndpointKind.LOSERS_BRACKET,
        competition_season_id,
        sleeper_league_id,
        "losers",
    )


def validate_winners_bracket_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    return _validate_bracket(payload, request, "winners")


def validate_losers_bracket_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    return _validate_bracket(payload, request, "losers")


def normalize_winners_bracket(
    payload: JsonValue,
    request: EndpointRequest,
) -> WinnersBracketEndpointRecords:
    _require_bracket_request(request, "winners")
    return WinnersBracketEndpointRecords(
        matchups=_parse_bracket(payload, "winners")
    )


def normalize_losers_bracket(
    payload: JsonValue,
    request: EndpointRequest,
) -> LosersBracketEndpointRecords:
    _require_bracket_request(request, "losers")
    return LosersBracketEndpointRecords(matchups=_parse_bracket(payload, "losers"))


def _validate_bracket(
    payload: JsonValue,
    request: EndpointRequest,
    bracket_kind: BracketKind,
) -> CompletenessFinding:
    _require_bracket_request(request, bracket_kind)
    try:
        _parse_bracket(payload, bracket_kind)
    except EndpointPayloadRejected as error:
        return incomplete(error.code)
    return complete()


def _parse_bracket(
    payload: JsonValue,
    bracket_kind: BracketKind,
) -> tuple[BracketMatchupRecord, ...]:
    endpoint_kind = _endpoint_kind(bracket_kind)
    raw_nodes = payload_list(payload, endpoint_kind, "bracket_payload_not_list")
    records: list[tuple[int | None, int, BracketMatchupRecord]] = []
    seen_node_keys: set[str] = set()

    for index, raw_value in enumerate(raw_nodes):
        raw = payload_object(raw_value, endpoint_kind, "bracket_node_not_object")
        round_number = integer(
            raw.get("r"), endpoint_kind, "bracket_round_invalid", minimum=1
        )
        matchup_id = optional_integer(
            raw.get("m"), endpoint_kind, "bracket_matchup_id_invalid", minimum=1
        )
        node_key = str(matchup_id) if matchup_id is not None else f"index:{index}"
        if node_key in seen_node_keys:
            reject(endpoint_kind, "bracket_node_key_duplicate")
        seen_node_keys.add(node_key)
        t1_key, t1_outcome = _progression(
            raw.get("t1_from"), endpoint_kind, "bracket_t1_from_invalid"
        )
        t2_key, t2_outcome = _progression(
            raw.get("t2_from"), endpoint_kind, "bracket_t2_from_invalid"
        )
        record = BracketMatchupRecord(
            bracket_kind=bracket_kind,
            node_key=node_key,
            round=round_number,
            t1_sleeper_roster_id=_optional_roster(raw.get("t1"), endpoint_kind),
            t2_sleeper_roster_id=_optional_roster(raw.get("t2"), endpoint_kind),
            t1_from_node_key=t1_key,
            t1_from_outcome=cast(str | None, t1_outcome),
            t2_from_node_key=t2_key,
            t2_from_outcome=cast(str | None, t2_outcome),
            winner_sleeper_roster_id=_optional_roster(
                raw.get("w"), endpoint_kind
            ),
            loser_sleeper_roster_id=_optional_roster(raw.get("l"), endpoint_kind),
            placement=optional_integer(
                raw.get("p"), endpoint_kind, "bracket_placement_invalid", minimum=1
            ),
        )
        records.append((matchup_id, index, record))

    records.sort(
        key=lambda item: (
            item[2].round,
            0 if item[0] is not None else 1,
            item[0] if item[0] is not None else item[1],
        )
    )
    return tuple(record for _, _, record in records)


def _progression(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    raw = payload_object(value, endpoint_kind, code)
    if len(raw) != 1 or not ({"w", "l"} & raw.keys()):
        reject(endpoint_kind, code)
    outcome = "w" if "w" in raw else "l"
    matchup_id = integer(raw[outcome], endpoint_kind, code, minimum=1)
    return str(matchup_id), outcome


def _optional_roster(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
) -> str | None:
    roster_id = optional_integer(
        value, endpoint_kind, "bracket_roster_id_invalid", minimum=1
    )
    return str(roster_id) if roster_id is not None else None


def _build_bracket_request(
    endpoint_kind: EndpointKind,
    competition_season_id: UUID,
    sleeper_league_id: str,
    bracket_kind: BracketKind,
) -> EndpointRequest:
    season_id = validated_season_id(competition_season_id)
    league_id = validated_league_id(sleeper_league_id)
    return EndpointRequest(
        endpoint_kind=endpoint_kind,
        scope_key=ScopeKey.from_parts(endpoint_kind, season_id, bracket_kind),
        path=f"/league/{league_id}/{bracket_kind}_bracket",
        bracket_kind=bracket_kind,
    )


def _require_bracket_request(
    request: EndpointRequest,
    bracket_kind: BracketKind,
) -> None:
    endpoint_kind = _endpoint_kind(bracket_kind)
    suffix = f"/{bracket_kind}_bracket"
    prefix = "/league/"
    if (
        request.endpoint_kind is not endpoint_kind
        or request.parameters
        or request.week is not None
        or request.bracket_kind != bracket_kind
        or not request.path.startswith(prefix)
        or not request.path.endswith(suffix)
    ):
        raise ValueError(f"request is not a canonical {endpoint_kind.value} request")
    validated_league_id(request.path[len(prefix) : -len(suffix)])
    parts = request.scope_key.value.split(":")
    if (
        len(parts) != 3
        or parts[0] != endpoint_kind.value
        or parts[2] != bracket_kind
    ):
        raise ValueError(f"request is not a canonical {endpoint_kind.value} request")
    try:
        UUID(parts[1])
    except ValueError as error:
        raise ValueError(
            f"request is not a canonical {endpoint_kind.value} request"
        ) from error


def _endpoint_kind(bracket_kind: BracketKind) -> EndpointKind:
    if bracket_kind == "winners":
        return EndpointKind.WINNERS_BRACKET
    return EndpointKind.LOSERS_BRACKET
