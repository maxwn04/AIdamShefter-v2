"""Weekly matchup and transaction endpoint behavior."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast
from uuid import UUID

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints._shared import (
    complete,
    exact_decimal,
    identifier,
    identifier_list,
    identifier_sort_key,
    incomplete,
    integer,
    optional_identifier,
    optional_integer,
    optional_text,
    payload_list,
    payload_object,
    reject,
    validated_league_id,
    validated_season_id,
    validated_week,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    CompletenessFinding,
    MatchupRecord,
    MatchupsEndpointRecords,
    PlayerPerformanceRecord,
    TransactionMoveRecord,
    TransactionRecord,
    TransactionsEndpointRecords,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


def build_matchups_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
    week: int,
) -> EndpointRequest:
    return _weekly_request(
        EndpointKind.MATCHUPS,
        competition_season_id,
        sleeper_league_id,
        week,
    )


def build_transactions_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
    week: int,
) -> EndpointRequest:
    return _weekly_request(
        EndpointKind.TRANSACTIONS,
        competition_season_id,
        sleeper_league_id,
        week,
    )


def validate_matchups_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    _require_weekly_request(request, EndpointKind.MATCHUPS)
    try:
        _parse_matchups(payload, cast(int, request.week))
    except EndpointPayloadRejected as error:
        return incomplete(error.code)
    return complete()


def validate_transactions_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    _require_weekly_request(request, EndpointKind.TRANSACTIONS)
    try:
        _parse_transactions(payload, cast(int, request.week))
    except EndpointPayloadRejected as error:
        return incomplete(error.code)
    return complete()


def normalize_matchups(
    payload: JsonValue,
    request: EndpointRequest,
) -> MatchupsEndpointRecords:
    _require_weekly_request(request, EndpointKind.MATCHUPS)
    return _parse_matchups(payload, cast(int, request.week))


def normalize_transactions(
    payload: JsonValue,
    request: EndpointRequest,
) -> TransactionsEndpointRecords:
    _require_weekly_request(request, EndpointKind.TRANSACTIONS)
    return _parse_transactions(payload, cast(int, request.week))


def _parse_matchups(payload: JsonValue, week: int) -> MatchupsEndpointRecords:
    kind = EndpointKind.MATCHUPS
    raw_matchups = payload_list(payload, kind, "matchups_payload_not_list")
    matchups: list[MatchupRecord] = []
    performances: list[PlayerPerformanceRecord] = []
    seen_rosters: set[str] = set()

    for raw_value in raw_matchups:
        raw = payload_object(raw_value, kind, "matchup_not_object")
        roster_id = identifier(raw.get("roster_id"), kind, "matchup_roster_id_missing")
        if roster_id in seen_rosters:
            reject(kind, "matchup_roster_id_duplicate")
        seen_rosters.add(roster_id)
        matchup_id = optional_integer(
            raw.get("matchup_id"), kind, "matchup_id_invalid", minimum=0
        )
        points = exact_decimal(
            raw.get("points"),
            kind,
            "matchup_points_invalid",
            default=Decimal(0),
        )
        matchups.append(
            MatchupRecord(
                week=week,
                sleeper_roster_id=roster_id,
                sleeper_matchup_id=matchup_id,
                points=points,
            )
        )

        player_ids = identifier_list(
            raw.get("players"), kind, "matchup_players_invalid"
        )
        if len(player_ids) != len(set(player_ids)):
            reject(kind, "matchup_player_id_duplicate")
        starters = identifier_list(
            raw.get("starters"), kind, "matchup_starters_invalid"
        )
        if len(starters) != len(set(starters)):
            reject(kind, "matchup_starter_id_duplicate")
        if not set(starters).issubset(player_ids):
            reject(kind, "matchup_starter_not_player")
        player_points = _player_points(raw.get("players_points"))
        if not set(player_points).issubset(player_ids):
            reject(kind, "matchup_points_player_unknown")
        for player_id in sorted(player_ids):
            performances.append(
                PlayerPerformanceRecord(
                    week=week,
                    sleeper_roster_id=roster_id,
                    sleeper_matchup_id=matchup_id,
                    sleeper_player_id=player_id,
                    points=player_points.get(player_id, Decimal(0)),
                    role="starter" if player_id in starters else "bench",
                )
            )

    matchups.sort(
        key=lambda row: (
            _optional_number_sort_key(row.sleeper_matchup_id),
            identifier_sort_key(row.sleeper_roster_id),
        )
    )
    performances.sort(
        key=lambda row: (
            _optional_number_sort_key(row.sleeper_matchup_id),
            identifier_sort_key(row.sleeper_roster_id),
            row.sleeper_player_id,
        )
    )
    return MatchupsEndpointRecords(
        matchups=tuple(matchups),
        player_performances=tuple(performances),
    )


def _parse_transactions(
    payload: JsonValue,
    week: int,
) -> TransactionsEndpointRecords:
    kind = EndpointKind.TRANSACTIONS
    raw_transactions = payload_list(payload, kind, "transactions_payload_not_list")
    transactions: list[TransactionRecord] = []
    move_groups: list[tuple[str, tuple[_MoveCandidate, ...]]] = []
    seen_transactions: set[str] = set()

    for raw_value in raw_transactions:
        raw = payload_object(raw_value, kind, "transaction_not_object")
        transaction_id = identifier(
            raw.get("transaction_id"), kind, "transaction_id_missing"
        )
        if transaction_id in seen_transactions:
            reject(kind, "transaction_id_duplicate")
        seen_transactions.add(transaction_id)
        settings = payload_object(
            raw.get("settings"),
            kind,
            "transaction_settings_invalid",
            default_empty=True,
        )
        metadata = payload_object(
            raw.get("metadata"),
            kind,
            "transaction_metadata_invalid",
            default_empty=True,
        )
        transactions.append(
            TransactionRecord(
                week=week,
                sleeper_transaction_id=transaction_id,
                transaction_type=optional_text(
                    raw.get("type"), kind, "transaction_type_invalid"
                )
                or "",
                status=optional_text(
                    raw.get("status"), kind, "transaction_status_invalid"
                ),
                provider_created_at_ms=optional_integer(
                    raw.get("created"), kind, "transaction_created_invalid", minimum=0
                ),
                settings=settings,
                metadata=metadata,
            )
        )
        move_groups.append(
            (transaction_id, _transaction_moves(raw, settings=settings))
        )

    transactions.sort(key=lambda row: row.sleeper_transaction_id)
    moves: list[TransactionMoveRecord] = []
    for transaction_id, candidates in sorted(move_groups):
        for move_index, candidate in enumerate(
            sorted(candidates, key=lambda row: row.sort_key)
        ):
            moves.append(candidate.to_record(transaction_id, move_index))
    return TransactionsEndpointRecords(
        transactions=tuple(transactions),
        moves=tuple(moves),
    )


@dataclass(frozen=True, slots=True)
class _MoveCandidate:
    sort_key: tuple[str, ...]
    move_kind: str
    from_roster: str | None = None
    to_roster: str | None = None
    player_id: str | None = None
    draft_season_year: int | None = None
    draft_round: int | None = None
    original_roster: str | None = None
    sleeper_pick_id: str | None = None
    budget_amount: int | None = None

    def to_record(
        self,
        transaction_id: str,
        move_index: int,
    ) -> TransactionMoveRecord:
        return TransactionMoveRecord(
            sleeper_transaction_id=transaction_id,
            move_index=move_index,
            move_kind=cast(str, self.move_kind),
            from_sleeper_roster_id=self.from_roster,
            to_sleeper_roster_id=self.to_roster,
            sleeper_player_id=self.player_id,
            draft_season_year=self.draft_season_year,
            draft_round=self.draft_round,
            original_sleeper_roster_id=self.original_roster,
            sleeper_pick_id=self.sleeper_pick_id,
            budget_amount=self.budget_amount,
        )


def _transaction_moves(
    raw: dict[str, JsonValue],
    *,
    settings: dict[str, JsonValue],
) -> tuple[_MoveCandidate, ...]:
    kind = EndpointKind.TRANSACTIONS
    budget_value = (
        settings.get("waiver_bid")
        if settings.get("waiver_bid") is not None
        else settings.get("price")
    )
    budget = optional_integer(
        budget_value, kind, "transaction_budget_invalid", minimum=0
    )
    adds = payload_object(
        raw.get("adds"), kind, "transaction_adds_invalid", default_empty=True
    )
    drops = payload_object(
        raw.get("drops"), kind, "transaction_drops_invalid", default_empty=True
    )
    result: list[_MoveCandidate] = []
    for raw_player_id in sorted(adds.keys() | drops.keys()):
        player_id = identifier(
            raw_player_id, kind, "transaction_player_id_invalid"
        )
        from_roster = (
            identifier(drops[raw_player_id], kind, "transaction_drop_roster_invalid")
            if raw_player_id in drops
            else None
        )
        to_roster = (
            identifier(adds[raw_player_id], kind, "transaction_add_roster_invalid")
            if raw_player_id in adds
            else None
        )
        result.append(
            _MoveCandidate(
                sort_key=("player", player_id, from_roster or "", to_roster or ""),
                move_kind="player",
                from_roster=from_roster,
                to_roster=to_roster,
                player_id=player_id,
                budget_amount=budget,
            )
        )

    raw_picks = raw.get("draft_picks")
    if raw_picks is None:
        raw_picks = []
    for raw_pick_value in payload_list(
        raw_picks, kind, "transaction_draft_picks_invalid"
    ):
        raw_pick = payload_object(
            raw_pick_value, kind, "transaction_draft_pick_not_object"
        )
        season = integer(
            raw_pick.get("season"), kind, "transaction_pick_season_invalid", minimum=1
        )
        round_number = integer(
            raw_pick.get("round"), kind, "transaction_pick_round_invalid", minimum=1
        )
        original_roster = identifier(
            raw_pick.get("roster_id"), kind, "transaction_pick_roster_invalid"
        )
        from_roster = optional_identifier(
            raw_pick.get("previous_owner_id"),
            kind,
            "transaction_pick_previous_owner_invalid",
        )
        to_roster = optional_identifier(
            raw_pick.get("owner_id"), kind, "transaction_pick_owner_invalid"
        )
        pick_id = optional_identifier(
            raw_pick.get("draft_pick_id"), kind, "transaction_pick_id_invalid"
        )
        result.append(
            _MoveCandidate(
                sort_key=(
                    "pick",
                    f"{season:010d}",
                    f"{round_number:010d}",
                    original_roster,
                    pick_id or "",
                    from_roster or "",
                    to_roster or "",
                ),
                move_kind="pick",
                from_roster=from_roster,
                to_roster=to_roster,
                draft_season_year=season,
                draft_round=round_number,
                original_roster=original_roster,
                sleeper_pick_id=pick_id,
                budget_amount=budget,
            )
        )
    return tuple(result)


def _player_points(value: JsonValue | None) -> dict[str, Decimal]:
    kind = EndpointKind.MATCHUPS
    raw = payload_object(
        value, kind, "matchup_players_points_invalid", default_empty=True
    )
    return {
        identifier(player_id, kind, "matchup_points_player_id_invalid"): exact_decimal(
            points, kind, "matchup_player_points_invalid"
        )
        for player_id, points in raw.items()
    }


def _weekly_request(
    endpoint_kind: EndpointKind,
    competition_season_id: UUID,
    sleeper_league_id: str,
    week: int,
) -> EndpointRequest:
    season_id = validated_season_id(competition_season_id)
    league_id = validated_league_id(sleeper_league_id)
    validated = validated_week(week)
    return EndpointRequest(
        endpoint_kind=endpoint_kind,
        scope_key=ScopeKey.from_parts(endpoint_kind, season_id, validated),
        path=f"/league/{league_id}/{endpoint_kind.value}/{validated}",
        week=validated,
    )


def _require_weekly_request(
    request: EndpointRequest,
    endpoint_kind: EndpointKind,
) -> None:
    week = request.week
    if week is None:
        raise ValueError(f"request is not a canonical {endpoint_kind.value} request")
    validated_week(week)
    suffix = f"/{endpoint_kind.value}/{week}"
    prefix = "/league/"
    if (
        request.endpoint_kind is not endpoint_kind
        or request.parameters
        or request.bracket_kind is not None
        or not request.path.startswith(prefix)
        or not request.path.endswith(suffix)
    ):
        raise ValueError(f"request is not a canonical {endpoint_kind.value} request")
    validated_league_id(request.path[len(prefix) : -len(suffix)])
    parts = request.scope_key.value.split(":")
    if len(parts) != 3 or parts[0] != endpoint_kind.value or parts[2] != str(week):
        raise ValueError(f"request is not a canonical {endpoint_kind.value} request")
    try:
        UUID(parts[1])
    except ValueError as error:
        raise ValueError(
            f"request is not a canonical {endpoint_kind.value} request"
        ) from error


def _optional_number_sort_key(value: int | None) -> tuple[int, int]:
    return (0, 0) if value is None else (1, value)
