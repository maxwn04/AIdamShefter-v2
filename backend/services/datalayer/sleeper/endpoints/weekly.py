"""Sleeper weekly matchup and transaction endpoint families."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Never
from uuid import UUID

from ...canonical_json import JsonValue
from ...errors import EndpointPayloadRejected
from ..responses import CompletenessFinding, EndpointRequest
from ..scope import EndpointKind, ScopeKey

LineupRole = Literal["starter", "bench"]
MoveKind = Literal["player", "pick"]


@dataclass(frozen=True, slots=True)
class MatchupRecord:
    week: int
    sleeper_roster_id: str
    sleeper_matchup_id: int | None
    points: Decimal


@dataclass(frozen=True, slots=True)
class PlayerPerformanceRecord:
    week: int
    sleeper_roster_id: str
    sleeper_matchup_id: int | None
    sleeper_player_id: str
    points: Decimal
    role: LineupRole


@dataclass(frozen=True, slots=True)
class MatchupEndpointRecords:
    matchups: tuple[MatchupRecord, ...]
    player_performances: tuple[PlayerPerformanceRecord, ...]


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    week: int
    sleeper_transaction_id: str
    transaction_type: str
    status: str | None
    provider_created_at_ms: int | None
    settings: dict[str, JsonValue]
    metadata: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class TransactionMoveRecord:
    sleeper_transaction_id: str
    move_index: int
    move_kind: MoveKind
    from_sleeper_roster_id: str | None
    to_sleeper_roster_id: str | None
    sleeper_player_id: str | None
    draft_season_year: int | None
    draft_round: int | None
    original_sleeper_roster_id: str | None
    sleeper_pick_id: str | None
    budget_amount: int | None


@dataclass(frozen=True, slots=True)
class TransactionEndpointRecords:
    transactions: tuple[TransactionRecord, ...]
    moves: tuple[TransactionMoveRecord, ...]


def build_matchups_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
    week: int,
) -> EndpointRequest:
    """Build an authoritative weekly matchup request."""

    _validate_week(week)
    league_id = _nonempty_identifier(sleeper_league_id, field="sleeper_league_id")
    return EndpointRequest(
        endpoint_kind=EndpointKind.MATCHUPS,
        scope_key=ScopeKey.from_parts("matchups", competition_season_id, week),
        path=f"/league/{league_id}/matchups/{week}",
        week=week,
    )


def build_transactions_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
    week: int,
) -> EndpointRequest:
    """Build an authoritative weekly transaction request."""

    _validate_week(week)
    league_id = _nonempty_identifier(sleeper_league_id, field="sleeper_league_id")
    return EndpointRequest(
        endpoint_kind=EndpointKind.TRANSACTIONS,
        scope_key=ScopeKey.from_parts("transactions", competition_season_id, week),
        path=f"/league/{league_id}/transactions/{week}",
        week=week,
    )


def validate_matchups_completeness(payload: JsonValue) -> CompletenessFinding:
    """Return whether a parsed matchup response has its authoritative shape."""

    return _validate_array_records(
        payload,
        record_name="matchup",
        required_field="roster_id",
    )


def validate_transactions_completeness(payload: JsonValue) -> CompletenessFinding:
    """Treat a valid empty weekly transaction response as authoritative."""

    return _validate_array_records(
        payload,
        record_name="transaction",
        required_field="transaction_id",
    )


def normalize_matchups(payload: JsonValue, *, week: int) -> MatchupEndpointRecords:
    """Normalize weekly lineup and scoring facts using exact decimals."""

    _validate_week(week)
    finding = validate_matchups_completeness(payload)
    if not finding.is_complete:
        _reject(EndpointKind.MATCHUPS, finding.code, finding.summary)
    assert isinstance(payload, list)

    matchups: list[MatchupRecord] = []
    performances: list[PlayerPerformanceRecord] = []
    seen_rosters: set[str] = set()
    for index, value in enumerate(payload):
        assert isinstance(value, dict)
        roster_id = _identifier(value.get("roster_id"), f"matchup[{index}].roster_id")
        if roster_id in seen_rosters:
            _reject(
                EndpointKind.MATCHUPS,
                "duplicate_roster_matchup",
                f"Week {week} matchup payload repeats roster_id {roster_id}",
            )
        seen_rosters.add(roster_id)
        matchup_id = _optional_int(
            value.get("matchup_id"),
            f"matchup[{index}].matchup_id",
            endpoint_kind=EndpointKind.MATCHUPS,
        )
        points = _decimal_or_zero(
            value.get("points"),
            f"matchup[{index}].points",
            endpoint_kind=EndpointKind.MATCHUPS,
        )
        matchups.append(
            MatchupRecord(
                week=week,
                sleeper_roster_id=roster_id,
                sleeper_matchup_id=matchup_id,
                points=points,
            )
        )

        players = _identifier_list(
            value.get("players"),
            f"matchup[{index}].players",
            endpoint_kind=EndpointKind.MATCHUPS,
        )
        if len(players) != len(set(players)):
            _reject(
                EndpointKind.MATCHUPS,
                "duplicate_player_performance",
                f"Week {week} roster {roster_id} repeats a player",
            )
        starters = set(
            _identifier_list(
                value.get("starters"),
                f"matchup[{index}].starters",
                endpoint_kind=EndpointKind.MATCHUPS,
            )
        )
        unknown_starters = starters.difference(players)
        if unknown_starters:
            _reject(
                EndpointKind.MATCHUPS,
                "starter_not_in_players",
                f"Week {week} roster {roster_id} has starters absent from players",
            )
        player_points = _player_points(value.get("players_points"), index=index)
        for player_id in sorted(players):
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

    return MatchupEndpointRecords(
        matchups=tuple(sorted(matchups, key=_matchup_sort_key)),
        player_performances=tuple(
            sorted(
                performances,
                key=lambda row: (
                    _optional_number_sort_key(row.sleeper_matchup_id),
                    _identifier_sort_key(row.sleeper_roster_id),
                    row.sleeper_player_id,
                ),
            )
        ),
    )


def normalize_transactions(
    payload: JsonValue,
    *,
    week: int,
) -> TransactionEndpointRecords:
    """Normalize transactions and emit one record per semantic asset transfer."""

    _validate_week(week)
    finding = validate_transactions_completeness(payload)
    if not finding.is_complete:
        _reject(EndpointKind.TRANSACTIONS, finding.code, finding.summary)
    assert isinstance(payload, list)

    transactions: list[TransactionRecord] = []
    moves_by_transaction: list[tuple[str, tuple[_MoveCandidate, ...]]] = []
    seen_transactions: set[str] = set()
    for index, value in enumerate(payload):
        assert isinstance(value, dict)
        transaction_id = _identifier(
            value.get("transaction_id"),
            f"transaction[{index}].transaction_id",
            endpoint_kind=EndpointKind.TRANSACTIONS,
        )
        if transaction_id in seen_transactions:
            _reject(
                EndpointKind.TRANSACTIONS,
                "duplicate_transaction",
                f"Week {week} payload repeats transaction {transaction_id}",
            )
        seen_transactions.add(transaction_id)

        settings = _object_or_empty(
            value.get("settings"),
            f"transaction[{index}].settings",
            endpoint_kind=EndpointKind.TRANSACTIONS,
        )
        metadata = _object_or_empty(
            value.get("metadata"),
            f"transaction[{index}].metadata",
            endpoint_kind=EndpointKind.TRANSACTIONS,
        )
        transaction_type = _optional_text(value.get("type"), field=f"transaction[{index}].type")
        status = _optional_text(value.get("status"), field=f"transaction[{index}].status")
        transactions.append(
            TransactionRecord(
                week=week,
                sleeper_transaction_id=transaction_id,
                transaction_type=transaction_type or "",
                status=status,
                provider_created_at_ms=_optional_int(
                    value.get("created"),
                    f"transaction[{index}].created",
                    endpoint_kind=EndpointKind.TRANSACTIONS,
                ),
                settings=settings,
                metadata=metadata,
            )
        )
        moves_by_transaction.append(
            (
                transaction_id,
                _transaction_moves(
                    value,
                    transaction_id=transaction_id,
                    transaction_index=index,
                    settings=settings,
                ),
            )
        )

    transactions.sort(key=lambda row: row.sleeper_transaction_id)
    moves: list[TransactionMoveRecord] = []
    for transaction_id, candidates in sorted(moves_by_transaction):
        for move_index, candidate in enumerate(sorted(candidates, key=lambda row: row.sort_key)):
            moves.append(candidate.to_record(transaction_id=transaction_id, move_index=move_index))
    return TransactionEndpointRecords(transactions=tuple(transactions), moves=tuple(moves))


@dataclass(frozen=True, slots=True)
class _MoveCandidate:
    sort_key: tuple[str, ...]
    move_kind: MoveKind
    from_sleeper_roster_id: str | None = None
    to_sleeper_roster_id: str | None = None
    sleeper_player_id: str | None = None
    draft_season_year: int | None = None
    draft_round: int | None = None
    original_sleeper_roster_id: str | None = None
    sleeper_pick_id: str | None = None
    budget_amount: int | None = None

    def to_record(
        self,
        *,
        transaction_id: str,
        move_index: int,
    ) -> TransactionMoveRecord:
        return TransactionMoveRecord(
            sleeper_transaction_id=transaction_id,
            move_index=move_index,
            move_kind=self.move_kind,
            from_sleeper_roster_id=self.from_sleeper_roster_id,
            to_sleeper_roster_id=self.to_sleeper_roster_id,
            sleeper_player_id=self.sleeper_player_id,
            draft_season_year=self.draft_season_year,
            draft_round=self.draft_round,
            original_sleeper_roster_id=self.original_sleeper_roster_id,
            sleeper_pick_id=self.sleeper_pick_id,
            budget_amount=self.budget_amount,
        )


def _transaction_moves(
    transaction: dict[str, JsonValue],
    *,
    transaction_id: str,
    transaction_index: int,
    settings: dict[str, JsonValue],
) -> tuple[_MoveCandidate, ...]:
    budget = _transaction_budget(settings, transaction_index=transaction_index)
    candidates: list[_MoveCandidate] = []
    adds = _object_or_empty(
        transaction.get("adds"),
        f"transaction[{transaction_index}].adds",
        endpoint_kind=EndpointKind.TRANSACTIONS,
    )
    drops = _object_or_empty(
        transaction.get("drops"),
        f"transaction[{transaction_index}].drops",
        endpoint_kind=EndpointKind.TRANSACTIONS,
    )
    for player_value in sorted(adds.keys() | drops.keys()):
        player_id = _identifier(
            player_value,
            f"transaction[{transaction_index}] player move",
            endpoint_kind=EndpointKind.TRANSACTIONS,
        )
        from_roster = (
            _identifier(
                drops[player_value],
                f"transaction[{transaction_index}].drops.{player_value}",
                endpoint_kind=EndpointKind.TRANSACTIONS,
            )
            if player_value in drops
            else None
        )
        to_roster = (
            _identifier(
                adds[player_value],
                f"transaction[{transaction_index}].adds.{player_value}",
                endpoint_kind=EndpointKind.TRANSACTIONS,
            )
            if player_value in adds
            else None
        )
        candidates.append(
            _MoveCandidate(
                sort_key=(
                    "player",
                    player_id,
                    from_roster or "",
                    to_roster or "",
                ),
                move_kind="player",
                from_sleeper_roster_id=from_roster,
                to_sleeper_roster_id=to_roster,
                sleeper_player_id=player_id,
                budget_amount=budget,
            )
        )

    draft_picks = transaction.get("draft_picks")
    if draft_picks is None:
        draft_picks = []
    if not isinstance(draft_picks, list):
        _reject(
            EndpointKind.TRANSACTIONS,
            "draft_picks_not_array",
            f"transaction[{transaction_index}].draft_picks must be an array",
        )
    for pick_index, value in enumerate(draft_picks):
        if not isinstance(value, dict):
            _reject(
                EndpointKind.TRANSACTIONS,
                "draft_pick_not_object",
                f"transaction[{transaction_index}].draft_picks[{pick_index}] must be an object",
            )
        season = _optional_int(
            value.get("season"),
            f"transaction[{transaction_index}].draft_picks[{pick_index}].season",
            endpoint_kind=EndpointKind.TRANSACTIONS,
        )
        round_number = _optional_int(
            value.get("round"),
            f"transaction[{transaction_index}].draft_picks[{pick_index}].round",
            endpoint_kind=EndpointKind.TRANSACTIONS,
        )
        original_roster = _optional_identifier(
            value.get("roster_id"),
            f"transaction[{transaction_index}].draft_picks[{pick_index}].roster_id",
        )
        from_roster = _optional_identifier(
            value.get("previous_owner_id"),
            f"transaction[{transaction_index}].draft_picks[{pick_index}].previous_owner_id",
        )
        to_roster = _optional_identifier(
            value.get("owner_id"),
            f"transaction[{transaction_index}].draft_picks[{pick_index}].owner_id",
        )
        pick_id = _optional_identifier(
            value.get("draft_pick_id"),
            f"transaction[{transaction_index}].draft_picks[{pick_index}].draft_pick_id",
        )
        if season is None or round_number is None or original_roster is None:
            _reject(
                EndpointKind.TRANSACTIONS,
                "draft_pick_identity_incomplete",
                f"transaction {transaction_id} contains a draft pick without "
                "season, round, and roster_id",
            )
        candidates.append(
            _MoveCandidate(
                sort_key=(
                    "pick",
                    str(season),
                    str(round_number),
                    original_roster,
                    pick_id or "",
                    from_roster or "",
                    to_roster or "",
                ),
                move_kind="pick",
                from_sleeper_roster_id=from_roster,
                to_sleeper_roster_id=to_roster,
                draft_season_year=season,
                draft_round=round_number,
                original_sleeper_roster_id=original_roster,
                sleeper_pick_id=pick_id,
                budget_amount=budget,
            )
        )
    return tuple(candidates)


def _transaction_budget(
    settings: dict[str, JsonValue],
    *,
    transaction_index: int,
) -> int | None:
    value = settings.get("waiver_bid")
    if value is None:
        value = settings.get("price")
    return _optional_int(
        value,
        f"transaction[{transaction_index}].settings budget",
        endpoint_kind=EndpointKind.TRANSACTIONS,
    )


def _player_points(value: JsonValue | None, *, index: int) -> dict[str, Decimal]:
    mapping = _object_or_empty(
        value,
        f"matchup[{index}].players_points",
        endpoint_kind=EndpointKind.MATCHUPS,
    )
    return {
        _identifier(
            player_id,
            f"matchup[{index}].players_points player",
            endpoint_kind=EndpointKind.MATCHUPS,
        ): _decimal_or_zero(
            points,
            f"matchup[{index}].players_points.{player_id}",
            endpoint_kind=EndpointKind.MATCHUPS,
        )
        for player_id, points in mapping.items()
    }


def _validate_array_records(
    payload: JsonValue,
    *,
    record_name: str,
    required_field: str,
) -> CompletenessFinding:
    if not isinstance(payload, list):
        return CompletenessFinding(
            is_complete=False,
            code="payload_not_array",
            summary=f"Sleeper {record_name} payload must be an array",
        )
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            return CompletenessFinding(
                is_complete=False,
                code=f"{record_name}_not_object",
                summary=f"Sleeper {record_name} at index {index} must be an object",
            )
        if item.get(required_field) is None:
            return CompletenessFinding(
                is_complete=False,
                code=f"{required_field}_missing",
                summary=f"Sleeper {record_name} at index {index} has no {required_field}",
            )
    return CompletenessFinding(
        is_complete=True,
        code="complete",
        summary=f"Sleeper {record_name} payload is complete",
    )


def _matchup_sort_key(row: MatchupRecord) -> tuple[tuple[int, int], tuple[int, int | str]]:
    return (
        _optional_number_sort_key(row.sleeper_matchup_id),
        _identifier_sort_key(row.sleeper_roster_id),
    )


def _optional_number_sort_key(value: int | None) -> tuple[int, int]:
    return (0, 0) if value is None else (1, value)


def _identifier_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _identifier_list(
    value: JsonValue | None,
    field: str,
    *,
    endpoint_kind: EndpointKind,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        _reject(endpoint_kind, "identifier_list_not_array", f"{field} must be an array")
    return tuple(
        _identifier(item, f"{field}[{index}]", endpoint_kind=endpoint_kind)
        for index, item in enumerate(value)
    )


def _object_or_empty(
    value: JsonValue | None,
    field: str,
    *,
    endpoint_kind: EndpointKind,
) -> dict[str, JsonValue]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        _reject(endpoint_kind, "object_expected", f"{field} must be an object")
    return dict(value)


def _optional_int(
    value: JsonValue | None,
    field: str,
    *,
    endpoint_kind: EndpointKind,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        _reject(endpoint_kind, "integer_expected", f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    _reject(endpoint_kind, "integer_expected", f"{field} must be an integer")


def _decimal_or_zero(
    value: JsonValue | None,
    field: str,
    *,
    endpoint_kind: EndpointKind,
) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, bool) or isinstance(value, float):
        _reject(endpoint_kind, "decimal_expected", f"{field} must be an exact decimal number")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        _reject(endpoint_kind, "decimal_expected", f"{field} must be an exact decimal number")
    if not result.is_finite():
        _reject(endpoint_kind, "decimal_expected", f"{field} must be a finite decimal number")
    return result


def _identifier(
    value: JsonValue | None,
    field: str,
    *,
    endpoint_kind: EndpointKind = EndpointKind.TRANSACTIONS,
) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        _reject(endpoint_kind, "identifier_expected", f"{field} must be an identifier")
    result = str(value).strip()
    if not result:
        _reject(endpoint_kind, "identifier_expected", f"{field} must be a non-empty identifier")
    return result


def _optional_identifier(value: JsonValue | None, field: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field, endpoint_kind=EndpointKind.TRANSACTIONS)


def _optional_text(value: JsonValue | None, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _reject(EndpointKind.TRANSACTIONS, "text_expected", f"{field} must be text")
    return value


def _validate_week(week: int) -> None:
    if isinstance(week, bool) or not 1 <= week <= 18:
        raise ValueError("week must be between 1 and 18")


def _nonempty_identifier(value: str, *, field: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{field} must not be empty")
    if any(character in result for character in "/?#"):
        raise ValueError(f"{field} contains a path delimiter")
    return result


def _reject(endpoint_kind: EndpointKind, code: str, summary: str) -> Never:
    raise EndpointPayloadRejected(
        endpoint_kind=endpoint_kind,
        code=code,
        summary=summary,
    )
