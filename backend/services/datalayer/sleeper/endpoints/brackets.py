"""Sleeper playoff-bracket requests and pure payload normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, NoReturn
from uuid import UUID

from ...canonical_json import JsonValue
from ...errors import EndpointPayloadRejected
from ..responses import CompletenessFinding, EndpointRequest
from ..scope import EndpointKind, ScopeKey

BracketKind = Literal["winners", "losers"]
ProgressionOutcome = Literal["w", "l"]


@dataclass(frozen=True, slots=True)
class BracketMatchupRecord:
    """One playoff matchup, including how each side advances into it."""

    bracket_kind: BracketKind
    round: int
    matchup_id: int
    t1_roster_id: int | None
    t2_roster_id: int | None
    t1_from_matchup_id: int | None
    t1_from_outcome: ProgressionOutcome | None
    t2_from_matchup_id: int | None
    t2_from_outcome: ProgressionOutcome | None
    winner_roster_id: int | None
    loser_roster_id: int | None
    placement: int | None


def build_winners_bracket_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    """Construct the canonical winners-bracket request for one season."""

    return _bracket_request(
        competition_season_id,
        sleeper_league_id,
        bracket_kind="winners",
    )


def build_losers_bracket_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    """Construct the canonical losers-bracket request for one season."""

    return _bracket_request(
        competition_season_id,
        sleeper_league_id,
        bracket_kind="losers",
    )


def validate_bracket_completeness(payload: JsonValue) -> CompletenessFinding:
    """Treat any list, including an authoritative empty list, as complete."""

    if not isinstance(payload, list):
        return CompletenessFinding(
            is_complete=False,
            code="bracket_payload_not_list",
            summary="Sleeper bracket payload must be a list",
        )
    return CompletenessFinding(
        is_complete=True,
        code="bracket_payload_complete",
        summary="Sleeper bracket payload is complete",
    )


def normalize_bracket(
    payload: JsonValue,
    *,
    bracket_kind: BracketKind,
) -> tuple[BracketMatchupRecord, ...]:
    """Normalize a complete bracket payload into a stable record ordering.

    Completeness validation owns the outer response shape. This function owns
    node-level mapping and rejects malformed nodes rather than silently losing
    a matchup or inventing progression facts.
    """

    endpoint_kind = _endpoint_kind(bracket_kind)
    if not isinstance(payload, list):
        raise EndpointPayloadRejected(
            endpoint_kind=endpoint_kind,
            code="bracket_payload_not_list",
            summary="Sleeper bracket payload must be a list",
        )

    records: list[BracketMatchupRecord] = []
    seen_matchups: set[int] = set()
    for index, node in enumerate(payload):
        if not isinstance(node, dict):
            _reject_node(endpoint_kind, index, "must be an object")

        round_number = _required_positive_int(node, "r", endpoint_kind, index)
        matchup_id = _required_positive_int(node, "m", endpoint_kind, index)
        if matchup_id in seen_matchups:
            raise EndpointPayloadRejected(
                endpoint_kind=endpoint_kind,
                code="duplicate_bracket_matchup",
                summary=(
                    f"Sleeper {bracket_kind} bracket repeats round "
                    f"{round_number} matchup {matchup_id}"
                ),
            )
        seen_matchups.add(matchup_id)

        t1_from_matchup_id, t1_from_outcome = _progression_reference(
            node.get("t1_from"),
            field="t1_from",
            endpoint_kind=endpoint_kind,
            index=index,
        )
        t2_from_matchup_id, t2_from_outcome = _progression_reference(
            node.get("t2_from"),
            field="t2_from",
            endpoint_kind=endpoint_kind,
            index=index,
        )

        records.append(
            BracketMatchupRecord(
                bracket_kind=bracket_kind,
                round=round_number,
                matchup_id=matchup_id,
                t1_roster_id=_optional_positive_int(
                    node.get("t1"), "t1", endpoint_kind, index
                ),
                t2_roster_id=_optional_positive_int(
                    node.get("t2"), "t2", endpoint_kind, index
                ),
                t1_from_matchup_id=t1_from_matchup_id,
                t1_from_outcome=t1_from_outcome,
                t2_from_matchup_id=t2_from_matchup_id,
                t2_from_outcome=t2_from_outcome,
                winner_roster_id=_optional_positive_int(
                    node.get("w"), "w", endpoint_kind, index
                ),
                loser_roster_id=_optional_positive_int(
                    node.get("l"), "l", endpoint_kind, index
                ),
                placement=_optional_positive_int(
                    node.get("p"), "p", endpoint_kind, index
                ),
            )
        )

    return tuple(sorted(records, key=lambda record: (record.round, record.matchup_id)))


def _bracket_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
    *,
    bracket_kind: BracketKind,
) -> EndpointRequest:
    if not sleeper_league_id or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in sleeper_league_id
    ):
        raise ValueError("sleeper_league_id must be a safe non-empty path segment")

    endpoint_kind = _endpoint_kind(bracket_kind)
    return EndpointRequest(
        endpoint_kind=endpoint_kind,
        scope_key=ScopeKey.from_parts(
            "bracket", competition_season_id, bracket_kind
        ),
        path=f"/league/{sleeper_league_id}/{bracket_kind}_bracket",
        bracket_kind=bracket_kind,
    )


def _endpoint_kind(bracket_kind: BracketKind) -> EndpointKind:
    if bracket_kind == "winners":
        return EndpointKind.WINNERS_BRACKET
    return EndpointKind.LOSERS_BRACKET


def _required_positive_int(
    node: dict[str, JsonValue],
    field: str,
    endpoint_kind: EndpointKind,
    index: int,
) -> int:
    if field not in node or node[field] is None:
        _reject_node(endpoint_kind, index, f"is missing required field {field!r}")
    value = node[field]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _reject_node(endpoint_kind, index, f"field {field!r} must be a positive integer")
    return value


def _optional_positive_int(
    value: JsonValue,
    field: str,
    endpoint_kind: EndpointKind,
    index: int,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _reject_node(endpoint_kind, index, f"field {field!r} must be null or a positive integer")
    return value


def _progression_reference(
    value: JsonValue,
    *,
    field: str,
    endpoint_kind: EndpointKind,
    index: int,
) -> tuple[int | None, ProgressionOutcome | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict) or len(value) != 1:
        _reject_node(
            endpoint_kind,
            index,
            f"field {field!r} must be null or one winner/loser reference",
        )
    if "w" in value:
        outcome: ProgressionOutcome = "w"
    elif "l" in value:
        outcome = "l"
    else:
        _reject_node(
            endpoint_kind,
            index,
            f"field {field!r} must contain 'w' or 'l'",
        )
    matchup_id = _optional_positive_int(
        value[outcome], field, endpoint_kind, index
    )
    if matchup_id is None:
        _reject_node(
            endpoint_kind,
            index,
            f"field {field!r} must reference a matchup",
        )
    return matchup_id, outcome


def _reject_node(
    endpoint_kind: EndpointKind,
    index: int,
    reason: str,
) -> NoReturn:
    raise EndpointPayloadRejected(
        endpoint_kind=endpoint_kind,
        code="malformed_bracket_node",
        summary=f"Sleeper bracket node {index} {reason}",
    )
