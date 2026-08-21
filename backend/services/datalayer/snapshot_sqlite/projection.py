"""Pure cutoff-safe projection of selected endpoint records."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from backend.services.datalayer.canonical_json import canonical_json_bytes
from backend.services.datalayer.contracts import CompletenessWarning
from backend.services.datalayer.snapshot_service import (
    SnapshotEndpointRecords,
    SnapshotMaterializationInput,
)
from backend.services.datalayer.sleeper.endpoints import (
    LeagueEndpointRecords,
    LeagueRostersEndpointRecords,
    LeagueUsersEndpointRecords,
    LosersBracketEndpointRecords,
    MatchupsEndpointRecords,
    PlayerCatalogEndpointRecords,
    TradedPicksEndpointRecords,
    TransactionsEndpointRecords,
    WinnersBracketEndpointRecords,
)
from backend.services.datalayer.sleeper.scope import ScopeKey


Row = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SourceRowProvenance:
    table_name: str
    row_key: tuple[str, ...]
    scope_key: ScopeKey


@dataclass(frozen=True, slots=True)
class SnapshotProjection:
    rows: Mapping[str, tuple[Row, ...]]
    warnings: tuple[CompletenessWarning, ...]
    provenance: tuple[SourceRowProvenance, ...]

    def rows_for(self, table_name: str) -> tuple[Row, ...]:
        return self.rows.get(table_name, ())


class _Builder:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.warnings: list[CompletenessWarning] = []
        self.provenance: list[SourceRowProvenance] = []

    def add(
        self,
        table_name: str,
        row: dict[str, Any],
        scope_key: ScopeKey,
        *key: object,
    ) -> None:
        self.rows.setdefault(table_name, []).append(row)
        self.provenance.append(
            SourceRowProvenance(
                table_name=table_name,
                row_key=tuple(str(value) for value in key),
                scope_key=scope_key,
            )
        )

    def warn(self, code: str, summary: str, scope_key: ScopeKey) -> None:
        self.warnings.append(
            CompletenessWarning(code=code, summary=summary, scope_key=scope_key)
        )

    def finish(self) -> SnapshotProjection:
        rows = {
            table: tuple(MappingProxyType(row) for row in sorted(values, key=_row_key))
            for table, values in self.rows.items()
        }
        warnings = tuple(
            sorted(
                set(self.warnings),
                key=lambda item: (item.code, item.scope_key.value if item.scope_key else ""),
            )
        )
        provenance = tuple(
            sorted(
                self.provenance,
                key=lambda item: (item.table_name, item.row_key, item.scope_key.value),
            )
        )
        return SnapshotProjection(MappingProxyType(rows), warnings, provenance)


def project_source_records(
    materialization: SnapshotMaterializationInput,
) -> SnapshotProjection:
    """Project source-backed rows without deriving reporter-only facts."""

    builder = _Builder()
    for endpoint in materialization.endpoint_records:
        _project_endpoint(builder, materialization, endpoint)
    _project_cutoff_membership(builder, materialization)
    return builder.finish()


def _project_endpoint(
    builder: _Builder,
    materialization: SnapshotMaterializationInput,
    endpoint: SnapshotEndpointRecords,
) -> None:
    records = endpoint.records
    scope = endpoint.manifest_entry.scope_key
    context = materialization.planning_context
    league_id = context.sleeper_league_id
    season = str(context.season_year)
    cutoff = materialization.request.through_week

    if isinstance(records, LeagueEndpointRecords):
        league = records.league
        if league.sleeper_league_id != league_id or league.season != season:
            raise ValueError("selected league record does not match planning identity")
        builder.add(
            "leagues",
            {
                "league_id": league_id,
                "season": season,
                "name": league.name,
                "sport": league.sport,
                "scoring_settings_json": _json(league.scoring_settings),
                "roster_positions_json": _json(list(league.roster_positions)),
                "playoff_week_start": league.playoff_start_week,
                "playoff_teams": league.playoff_team_count,
                "league_average_match": league.league_average_match,
            },
            scope,
            league_id,
        )
    elif isinstance(records, LeagueUsersEndpointRecords):
        for user in records.users:
            builder.add(
                "users",
                {
                    "user_id": user.sleeper_user_id,
                    "display_name": user.display_name,
                    "avatar": user.avatar,
                    "metadata_json": None,
                },
                scope,
                user.sleeper_user_id,
            )
    elif isinstance(records, PlayerCatalogEndpointRecords):
        omitted = False
        for player in records.players:
            omitted = omitted or any(
                value is not None
                for value in (
                    player.nfl_team,
                    player.active,
                    player.status,
                    player.injury_status,
                    player.age,
                    player.years_experience,
                )
            ) or bool(player.metadata)
            builder.add(
                "players",
                {
                    "player_id": player.sleeper_player_id,
                    "full_name": player.full_name,
                    "position": player.position,
                    "nfl_team": None,
                    "status": None,
                    "injury_status": None,
                    "age": None,
                    "years_exp": None,
                    "metadata_json": None,
                    "updated_at": None,
                },
                scope,
                player.sleeper_player_id,
            )
        if omitted:
            builder.warn(
                "snapshot.player_state_omitted",
                "Later-observed player state was omitted from the cutoff artifact",
                scope,
            )
    elif isinstance(records, LeagueRostersEndpointRecords):
        managers: dict[str, list[tuple[int, str, str]]] = {}
        for manager in records.managers:
            managers.setdefault(manager.sleeper_roster_id, []).append(
                (manager.source_order, manager.role, manager.sleeper_user_id)
            )
        for roster in records.rosters:
            roster_id = _roster_id(roster.sleeper_roster_id)
            ordered = sorted(managers.get(roster.sleeper_roster_id, ()))
            owner = next(
                (user_id for _, role, user_id in ordered if role == "owner"),
                ordered[0][2] if ordered else None,
            )
            display_metadata = {
                key: roster.metadata[key]
                for key in ("team_name", "name", "team_name2", "avatar")
                if key in roster.metadata
            }
            builder.add(
                "rosters",
                {
                    "league_id": league_id,
                    "roster_id": roster_id,
                    "owner_user_id": owner,
                    "settings_json": None,
                    "metadata_json": _json(display_metadata) if display_metadata else None,
                    "record_string": _safe_record_prefix(
                        roster.record_string,
                        through_week=cutoff,
                        playoff_start_week=context.playoff_start_week,
                        league_average_match=context.league_average_match,
                    ),
                },
                scope,
                league_id,
                roster_id,
            )
        builder.warn(
            "snapshot.roster_reconstruction_limited",
            "Roster membership is reconstructed as starter or bench at the cutoff",
            scope,
        )
    elif isinstance(records, MatchupsEndpointRecords):
        for matchup in records.matchups:
            if matchup.week > cutoff or matchup.sleeper_matchup_id is None:
                builder.warn(
                    "snapshot.matchup_group_omitted",
                    "A matchup without a cutoff-safe pair identity was omitted",
                    scope,
                )
                continue
            roster_id = _roster_id(matchup.sleeper_roster_id)
            builder.add(
                "matchups",
                {
                    "league_id": league_id,
                    "season": season,
                    "week": matchup.week,
                    "matchup_id": matchup.sleeper_matchup_id,
                    "roster_id": roster_id,
                    "points": _number(matchup.points),
                },
                scope,
                league_id,
                matchup.week,
                matchup.sleeper_matchup_id,
                roster_id,
            )
        for performance in records.player_performances:
            if performance.week > cutoff or performance.sleeper_matchup_id is None:
                continue
            roster_id = _roster_id(performance.sleeper_roster_id)
            builder.add(
                "player_performances",
                {
                    "league_id": league_id,
                    "season": season,
                    "week": performance.week,
                    "player_id": performance.sleeper_player_id,
                    "roster_id": roster_id,
                    "matchup_id": performance.sleeper_matchup_id,
                    "points": _number(performance.points),
                    "role": performance.role,
                },
                scope,
                league_id,
                season,
                performance.week,
                performance.sleeper_player_id,
                roster_id,
            )
    elif isinstance(records, TransactionsEndpointRecords):
        for transaction in records.transactions:
            if transaction.week > cutoff:
                raise ValueError("selected transaction exceeds snapshot cutoff")
            builder.add(
                "transactions",
                {
                    "league_id": league_id,
                    "season": season,
                    "week": transaction.week,
                    "transaction_id": transaction.sleeper_transaction_id,
                    "type": transaction.transaction_type,
                    "status": transaction.status,
                    "created_ts": transaction.provider_created_at_ms,
                    "settings_json": _json(transaction.settings),
                    "metadata_json": _json(transaction.metadata),
                },
                scope,
                transaction.sleeper_transaction_id,
            )
        for move in records.moves:
            for row in _move_rows(move):
                builder.add(
                    "transaction_moves",
                    row,
                    scope,
                    row["transaction_id"],
                    row["move_index"],
                    row["direction"],
                )
    elif isinstance(records, (WinnersBracketEndpointRecords, LosersBracketEndpointRecords)):
        if context.playoff_start_week is None:
            if records.matchups:
                builder.warn(
                    "snapshot.bracket_cutoff_unknown",
                    "Bracket nodes were omitted because their cutoff week is unknown",
                    scope,
                )
            return
        for node in records.matchups:
            effective_week = context.playoff_start_week + node.round - 1
            if effective_week > cutoff:
                continue
            builder.add(
                "playoff_matchups",
                {
                    "league_id": league_id,
                    "season": season,
                    "bracket_type": node.bracket_kind,
                    "node_key": node.node_key,
                    "round": node.round,
                    "matchup_id": _optional_int(node.node_key),
                    "t1_roster_id": _optional_roster_id(node.t1_sleeper_roster_id),
                    "t2_roster_id": _optional_roster_id(node.t2_sleeper_roster_id),
                    "t1_from_matchup_id": _optional_int(node.t1_from_node_key),
                    "t1_from_outcome": node.t1_from_outcome,
                    "t2_from_matchup_id": _optional_int(node.t2_from_node_key),
                    "t2_from_outcome": node.t2_from_outcome,
                    "winner_roster_id": _optional_roster_id(
                        node.winner_sleeper_roster_id
                    ),
                    "loser_roster_id": _optional_roster_id(
                        node.loser_sleeper_roster_id
                    ),
                    "placement": node.placement,
                },
                scope,
                league_id,
                season,
                node.bracket_kind,
                node.node_key,
            )
    elif isinstance(records, TradedPicksEndpointRecords):
        return


def _project_cutoff_membership(
    builder: _Builder,
    materialization: SnapshotMaterializationInput,
) -> None:
    cutoff = materialization.request.through_week
    league_id = materialization.planning_context.sleeper_league_id
    seen: set[tuple[int, str]] = set()
    for endpoint in materialization.endpoint_records:
        records = endpoint.records
        if not isinstance(records, MatchupsEndpointRecords):
            continue
        for performance in records.player_performances:
            if performance.week != cutoff or performance.sleeper_matchup_id is None:
                continue
            roster_id = _roster_id(performance.sleeper_roster_id)
            key = (roster_id, performance.sleeper_player_id)
            if key in seen:
                raise ValueError("cutoff roster membership contains a duplicate player")
            seen.add(key)
            builder.add(
                "roster_players",
                {
                    "league_id": league_id,
                    "roster_id": roster_id,
                    "player_id": performance.sleeper_player_id,
                    "role": performance.role,
                },
                endpoint.manifest_entry.scope_key,
                league_id,
                roster_id,
                performance.sleeper_player_id,
            )


def _move_rows(move: Any) -> tuple[dict[str, Any], ...]:
    common = {
        "transaction_id": move.sleeper_transaction_id,
        "move_index": move.move_index,
        "bid_amount": move.budget_amount,
        "from_roster_id": _optional_roster_id(move.from_sleeper_roster_id),
        "to_roster_id": _optional_roster_id(move.to_sleeper_roster_id),
    }
    rows: list[dict[str, Any]] = []
    if move.move_kind == "player":
        directions = (
            ("drop", move.from_sleeper_roster_id),
            ("add", move.to_sleeper_roster_id),
        )
        for direction, roster in directions:
            if roster is None:
                continue
            rows.append(
                {
                    **common,
                    "roster_id": _roster_id(roster),
                    "player_id": move.sleeper_player_id,
                    "asset_type": "player",
                    "direction": direction,
                    "pick_season": None,
                    "pick_round": None,
                    "pick_original_roster_id": None,
                    "pick_id": None,
                }
            )
    else:
        directions = (
            ("pick_out", move.from_sleeper_roster_id),
            ("pick_in", move.to_sleeper_roster_id),
        )
        for direction, roster in directions:
            if roster is None:
                continue
            rows.append(
                {
                    **common,
                    "roster_id": _roster_id(roster),
                    "player_id": None,
                    "asset_type": "pick",
                    "direction": direction,
                    "pick_season": str(move.draft_season_year),
                    "pick_round": move.draft_round,
                    "pick_original_roster_id": _roster_id(
                        move.original_sleeper_roster_id
                    ),
                    "pick_id": move.sleeper_pick_id,
                }
            )
    return tuple(rows)


def _safe_record_prefix(
    record: str | None,
    *,
    through_week: int,
    playoff_start_week: int | None,
    league_average_match: int | None,
) -> str | None:
    if not record:
        return None
    normalized = "".join(character for character in record.upper() if not character.isspace())
    if not normalized or any(character not in "WLT" for character in normalized):
        return None
    regular_weeks = min(
        through_week,
        playoff_start_week - 1 if playoff_start_week is not None else through_week,
    )
    chars_per_week = 2 if league_average_match == 1 else 1
    return normalized[: regular_weeks * chars_per_week] or None


def _roster_id(value: str | None) -> int:
    if value is None:
        raise ValueError("snapshot reporter schema requires a roster ID")
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError("snapshot reporter schema requires numeric roster IDs") from error
    if result < 1 or str(result) != value.strip():
        raise ValueError("snapshot reporter schema requires canonical positive roster IDs")
    return result


def _optional_roster_id(value: str | None) -> int | None:
    return None if value is None else _roster_id(value)


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _number(value: Decimal) -> float:
    return float(value)


def _json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _row_key(row: dict[str, Any]) -> str:
    return repr(sorted(row.items()))
