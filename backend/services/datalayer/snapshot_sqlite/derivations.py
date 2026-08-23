"""Pure reporter-facing derivations for one cutoff-safe snapshot."""

from __future__ import annotations

from collections import defaultdict
from types import MappingProxyType
from typing import Any, Mapping

from backend.services.datalayer.canonical_json import parse_json_bytes
from backend.services.datalayer.contracts import CompletenessWarning
from backend.services.datalayer.snapshot_service import SnapshotMaterializationInput
from backend.services.datalayer.snapshot_sqlite.projection import (
    Row,
    SnapshotProjection,
)
from backend.services.datalayer.sleeper.endpoints import (
    LeagueRostersEndpointRecords,
    LeagueUsersEndpointRecords,
    MatchupsEndpointRecords,
    TradedPicksEndpointRecords,
)
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


_DERIVED_TABLES = {
    "games",
    "standings",
    "team_profiles",
    "draft_picks",
    "season_context",
    "roster_identities",
}


def derive_snapshot_rows(
    materialization: SnapshotMaterializationInput,
    source: SnapshotProjection,
) -> SnapshotProjection:
    """Add deterministic games, standings, profiles, picks, and context."""

    if _DERIVED_TABLES & source.rows.keys():
        raise ValueError("source projection already contains derived tables")
    rows = {table: list(values) for table, values in source.rows.items()}
    warnings = list(source.warnings)
    games, game_warnings = _derive_games(materialization, source)
    rows["games"] = games
    warnings.extend(game_warnings)
    standings, standing_warnings = _derive_standings(
        materialization,
        source,
        games,
    )
    rows["standings"] = standings
    warnings.extend(standing_warnings)
    rows["team_profiles"] = _derive_profiles(materialization, source)
    rows["roster_identities"] = _derive_roster_identities(materialization)
    rows["draft_picks"] = _derive_draft_picks(materialization, source)
    rows["season_context"] = [
        {
            "league_id": materialization.planning_context.sleeper_league_id,
            "computed_week": materialization.request.through_week,
            "override_week": materialization.request.through_week,
            "effective_week": materialization.request.through_week,
            "generated_at": None,
        }
    ]
    frozen_rows = MappingProxyType(
        {
            table: tuple(MappingProxyType(dict(row)) for row in values)
            for table, values in rows.items()
        }
    )
    ordered_warnings = tuple(
        sorted(
            set(warnings),
            key=lambda item: (
                item.code,
                item.scope_key.value if item.scope_key else "",
            ),
        )
    )
    return SnapshotProjection(frozen_rows, ordered_warnings, source.provenance)


def _derive_roster_identities(
    materialization: SnapshotMaterializationInput,
) -> list[dict[str, Any]]:
    context = materialization.planning_context
    return [
        {
            "league_id": context.sleeper_league_id,
            "roster_id": _numeric_roster_id(identity.sleeper_roster_id),
            "competition_id": str(identity.competition_id),
            "competition_season_id": str(identity.competition_season_id),
            "season_roster_id": str(identity.season_roster_id),
            "franchise_id": str(identity.franchise_id),
        }
        for identity in sorted(
            materialization.roster_identities,
            key=lambda item: _numeric_roster_id(item.sleeper_roster_id),
        )
    ]


def _derive_games(
    materialization: SnapshotMaterializationInput,
    source: SnapshotProjection,
) -> tuple[list[dict[str, Any]], list[CompletenessWarning]]:
    grouped: dict[tuple[int, int], list[Row]] = defaultdict(list)
    for row in source.rows_for("matchups"):
        grouped[(row["week"], row["matchup_id"])].append(row)
    scope_by_week = _scope_by_week(materialization, EndpointKind.MATCHUPS)
    games: list[dict[str, Any]] = []
    warnings: list[CompletenessWarning] = []
    playoff_start = materialization.planning_context.playoff_start_week
    for (week, matchup_id), members in sorted(grouped.items()):
        if len(members) != 2 or len({row["roster_id"] for row in members}) != 2:
            warnings.append(
                CompletenessWarning(
                    code="snapshot.matchup_group_omitted",
                    summary="A matchup group without exactly two rosters was omitted",
                    scope_key=scope_by_week[week],
                )
            )
            continue
        first, second = sorted(members, key=lambda row: row["roster_id"])
        winner = None
        if first["points"] > second["points"]:
            winner = first["roster_id"]
        elif second["points"] > first["points"]:
            winner = second["roster_id"]
        games.append(
            {
                "league_id": first["league_id"],
                "season": first["season"],
                "week": week,
                "matchup_id": matchup_id,
                "roster_id_a": first["roster_id"],
                "roster_id_b": second["roster_id"],
                "points_a": first["points"],
                "points_b": second["points"],
                "winner_roster_id": winner,
                "is_playoffs": int(playoff_start is not None and week >= playoff_start),
            }
        )
    return games, warnings


def _derive_standings(
    materialization: SnapshotMaterializationInput,
    source: SnapshotProjection,
    games: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[CompletenessWarning]]:
    context = materialization.planning_context
    cutoff = materialization.request.through_week
    regular_end = min(
        cutoff,
        context.playoff_start_week - 1
        if context.playoff_start_week is not None
        else cutoff,
    )
    rosters = sorted(source.rows_for("rosters"), key=lambda row: row["roster_id"])
    roster_scope = _first_scope(materialization, EndpointKind.LEAGUE_ROSTERS)
    rows: list[dict[str, Any]] = []
    warnings: list[CompletenessWarning] = []
    warned_lam = False
    for week in range(1, cutoff + 1):
        effective = min(week, regular_end)
        facts: list[dict[str, Any]] = []
        for roster in rosters:
            roster_id = roster["roster_id"]
            relevant = [
                game
                for game in games
                if not game["is_playoffs"]
                and game["week"] <= effective
                and roster_id in (game["roster_id_a"], game["roster_id_b"])
            ]
            points_for = 0.0
            points_against = 0.0
            outcomes: list[str] = []
            for game in sorted(relevant, key=lambda row: row["week"]):
                is_a = roster_id == game["roster_id_a"]
                team_points = game["points_a"] if is_a else game["points_b"]
                opponent_points = game["points_b"] if is_a else game["points_a"]
                points_for += team_points
                points_against += opponent_points
                if team_points > opponent_points:
                    outcomes.append("W")
                elif team_points < opponent_points:
                    outcomes.append("L")
                else:
                    outcomes.append("T")
            record_outcomes = outcomes
            if context.league_average_match == 1:
                record = roster["record_string"] or ""
                required = effective * 2
                if len(record) >= required:
                    record_outcomes = list(record[:required])
                elif not warned_lam:
                    warned_lam = True
                    warnings.append(
                        CompletenessWarning(
                            code="snapshot.league_average_record_incomplete",
                            summary=(
                                "League-average standings omit results that could not "
                                "be reconstructed at the cutoff"
                            ),
                            scope_key=roster_scope,
                        )
                    )
            streak_type, streak_len = _streak(record_outcomes)
            facts.append(
                {
                    "league_id": context.sleeper_league_id,
                    "season": str(context.season_year),
                    "week": week,
                    "roster_id": roster_id,
                    "wins": record_outcomes.count("W"),
                    "losses": record_outcomes.count("L"),
                    "ties": record_outcomes.count("T"),
                    "points_for": points_for,
                    "points_against": points_against,
                    "rank": None,
                    "streak_type": streak_type,
                    "streak_len": streak_len,
                }
            )
        ranked = sorted(
            facts,
            key=lambda row: (-row["wins"], -row["points_for"], row["roster_id"]),
        )
        for rank, fact in enumerate(ranked, start=1):
            fact["rank"] = rank
        rows.extend(sorted(facts, key=lambda row: row["roster_id"]))
    return rows, warnings


def _derive_profiles(
    materialization: SnapshotMaterializationInput,
    source: SnapshotProjection,
) -> list[dict[str, Any]]:
    users = {row["user_id"]: row for row in source.rows_for("users")}
    league_users: dict[str, Any] = {}
    managers: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for endpoint in materialization.endpoint_records:
        records = endpoint.records
        if isinstance(records, LeagueUsersEndpointRecords):
            league_users = {row.sleeper_user_id: row for row in records.league_users}
        elif isinstance(records, LeagueRostersEndpointRecords):
            for manager in records.managers:
                managers[manager.sleeper_roster_id].append(
                    (manager.source_order, manager.role, manager.sleeper_user_id)
                )
    result: list[dict[str, Any]] = []
    for roster in sorted(source.rows_for("rosters"), key=lambda row: row["roster_id"]):
        roster_key = str(roster["roster_id"])
        ordered = sorted(managers.get(roster_key, ()))
        user_id = next(
            (value for _, role, value in ordered if role == "owner"),
            ordered[0][2] if ordered else roster["owner_user_id"],
        )
        user = users.get(user_id) if user_id else None
        league_user = league_users.get(user_id) if user_id else None
        metadata = (
            parse_json_bytes(roster["metadata_json"].encode("utf-8"))
            if roster["metadata_json"]
            else {}
        )
        team_name = next(
            (
                value
                for value in (
                    metadata.get("team_name"),
                    metadata.get("name"),
                    metadata.get("team_name2"),
                    league_user.team_name if league_user else None,
                    user["display_name"] if user else None,
                )
                if value
            ),
            None,
        )
        avatar = user["avatar"] if user else metadata.get("avatar")
        result.append(
            {
                "league_id": roster["league_id"],
                "roster_id": roster["roster_id"],
                "team_name": team_name,
                "manager_name": user["display_name"] if user else None,
                "avatar_url": (
                    f"https://sleepercdn.com/avatars/{avatar}" if avatar else None
                ),
            }
        )
    return result


def _derive_draft_picks(
    materialization: SnapshotMaterializationInput,
    source: SnapshotProjection,
) -> list[dict[str, Any]]:
    context = materialization.planning_context
    roster_ids = [row["roster_id"] for row in source.rows_for("rosters")]
    rows: dict[tuple[int, int, int], dict[str, Any]] = {}
    for season in range(context.season_year + 1, context.season_year + 4):
        for round_number in range(1, context.draft_rounds + 1):
            for roster_id in roster_ids:
                rows[(season, round_number, roster_id)] = {
                    "league_id": context.sleeper_league_id,
                    "season": str(season),
                    "round": round_number,
                    "original_roster_id": roster_id,
                    "current_roster_id": roster_id,
                    "pick_id": None,
                    "source": "seed",
                }
    for endpoint in materialization.endpoint_records:
        if not isinstance(endpoint.records, TradedPicksEndpointRecords):
            continue
        for pick in endpoint.records.picks:
            key = (
                pick.draft_season_year,
                pick.draft_round,
                _numeric_roster_id(pick.original_sleeper_roster_id),
            )
            if key not in rows:
                continue
            rows[key]["current_roster_id"] = _numeric_roster_id(
                pick.current_owner_sleeper_roster_id
            )
            rows[key]["pick_id"] = pick.sleeper_pick_id
            rows[key]["source"] = "trade"
    return [rows[key] for key in sorted(rows)]


def _scope_by_week(
    materialization: SnapshotMaterializationInput,
    kind: EndpointKind,
) -> dict[int, ScopeKey]:
    result = {}
    for endpoint in materialization.endpoint_records:
        if endpoint.records.endpoint_kind is kind:
            week = int(endpoint.manifest_entry.scope_key.value.rsplit(":", 1)[1])
            result[week] = endpoint.manifest_entry.scope_key
    return result


def _first_scope(
    materialization: SnapshotMaterializationInput,
    kind: EndpointKind,
) -> ScopeKey:
    return next(
        endpoint.manifest_entry.scope_key
        for endpoint in materialization.endpoint_records
        if endpoint.records.endpoint_kind is kind
    )


def _streak(outcomes: list[str]) -> tuple[str | None, int | None]:
    if not outcomes:
        return None, None
    final = outcomes[-1]
    length = 0
    for outcome in reversed(outcomes):
        if outcome != final:
            break
        length += 1
    return final, length


def _numeric_roster_id(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError(
            "snapshot reporter schema requires numeric roster IDs"
        ) from error
    if result < 1 or str(result) != value.strip():
        raise ValueError(
            "snapshot reporter schema requires canonical positive roster IDs"
        )
    return result
