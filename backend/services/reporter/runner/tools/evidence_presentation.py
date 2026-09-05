"""Bounded selected evidence from executed frozen queries, with private raw audit."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
import re
from typing import Any, Callable

from backend.services.reporter.runner.evidence import (
    EVIDENCE_VERSION, EvidenceOutcome, EvidenceRecord,
)

PAGE_SIZE = 40
_PRIVATE = {
    "competition_id", "competition_season_id", "season_roster_id", "franchise_id",
    "sleeper_league_id", "league_id", "snapshot_id", "snapshot_metadata",
    "diagnostics", "provenance", "source_observation_ids", "created_ts",
    "build_key", "input_revision", "storage_key", "selected_requests_json",
    "completeness_warnings_json", "metadata_json", "settings_json",
}
_LIMITED_TOOLS = {"season_leaders", "week_player_leaderboard", "run_sql"}
_WEEK_TOOLS = {
    "league_snapshot", "week_games", "team_game", "week_player_leaderboard",
    "bench_analysis", "roster_snapshot",
    "roster_at_cutoff", "player_summary",
}


def selected_records(
    source: str,
    tool: str,
    raw: Any,
    arguments: dict[str, Any],
    seasons: list[dict[str, Any]],
    identity: Callable[[str, int | None], tuple[str | None, str | None]],
    snapshot_limitations: tuple[str, ...] = (),
    snapshot_population_complete: bool = True,
    snapshot_warnings: tuple[dict[str, Any], ...] = (),
) -> tuple[EvidenceRecord, ...]:
    """Select source objects in deterministic traversal order, retaining scope.

    This is presentation, not an inference engine: fields retain source names.
    Structured assets are separate directional records. No output-size truncation
    occurs in the catalog; pagination only bounds the model-facing view.
    """
    primary = next((s for s in seasons if s.get("role") == "primary"), {})
    season = arguments.get("season") or primary.get("season_year")
    selected = next((s for s in seasons if s.get("season_year") == season), primary)
    cutoff = selected.get("through_week")
    week_to = arguments.get("week_to") or arguments.get("week") or cutoff
    week_from = arguments.get("week_from") or (week_to if tool in _WEEK_TOOLS else 1)
    if tool in {"available_seasons", "league_history", "franchise_history", "run_sql"}:
        season = week_from = week_to = None
    limitations: list[str] = list(snapshot_limitations)
    if tool in _LIMITED_TOOLS:
        limitations.append("Bounded query results; complete comparison population is not established.")
    if tool == "run_sql":
        limitations.append("SQL field semantics, units and season scope require review; evidence is diagnostic.")
    if tool in {"roster_at_cutoff", "player_summary"}:
        limitations.append("Snapshot observation at cutoff; not a reconstructed earlier roster or player status.")
    records: list[EvidenceRecord] = []
    if tool == "run_sql" and isinstance(raw, dict):
        return _sql_records(source, raw, tuple(limitations))

    def visit(
        node: Any, path: str, subject: str | None, subject_id: str | None,
        node_season: int | None, start: int | None, end: int | None,
        perspective: str | None, population: str | None,
        inherited_limits: tuple[str, ...], inherited_outcome: EvidenceOutcome = "found",
        inherited_complete: bool = True,
    ) -> None:
        if isinstance(node, (list, tuple)):
            for i, child in enumerate(node):
                visit(child, f"{path}/{i}", subject, subject_id, node_season, start,
                      end, perspective, f"{source}:{path}", inherited_limits, inherited_outcome, inherited_complete)
            return
        if not isinstance(node, dict):
            # Scalar list results still have an exact source field binding.
            records.append(EvidenceRecord(
                ref=f"{source}.r{len(records)}", source=source, tool=tool,
                outcome=inherited_outcome, season=node_season,
                week_from=start, week_to=end, fields={"value": node},
                field_paths={"value": path}, limitations=inherited_limits,
            ))
            return
        # A draft asset's year is its maturity, not the observation season.
        if not any(segment in path.split("/") for segment in ("picks", "draft_picks", "assets_sent", "assets_received")):
            node_season = _integer(node.get("season", node.get("season_year"))) or node_season
        if node.get("through_week") is not None:
            start, end = 1, _integer(node["through_week"])
        if node.get("as_of_week") is not None:
            end = _integer(node["as_of_week"])
        if node.get("week") is not None:
            start = end = _integer(node["week"])
        start = _integer(node.get("week_from")) or start
        end = _integer(node.get("week_to")) or end
        team = node.get("team") if isinstance(node.get("team"), dict) else {}
        own_subject = node.get("team_name") or team.get("team_name")
        player_name = node.get("player_name") or node.get("full_name")
        player_metric = (tool not in {"transactions", "team_transactions"}
                         and player_name and (tool in {"player_summary", "player_weekly_log", "season_leaders", "week_player_leaderboard"}
                                              or any(_points_field(key) for key in node)))
        if player_metric:
            perspective = str(own_subject or subject) if own_subject or subject else perspective
            subject, subject_id = str(player_name), None
        elif tool == "player_weekly_log" and subject is not None and own_subject:
            # Weekly team assignment is perspective; the metric still belongs to the player.
            perspective = str(own_subject)
        # Player-only results use player names, while roster assets keep team perspective.
        elif own_subject:
            subject = str(own_subject)
            subject_id, _ = identity(subject, node_season)
        elif subject is None and (node.get("player_name") or node.get("full_name")):
            subject = str(node.get("player_name") or node.get("full_name"))
        local_limits = list(inherited_limits)
        for key in ("limitations", "warnings", "caveats", "warning", "limitation"):
            if node.get(key):
                value = node[key]
                local_limits.extend(str(item) for item in value) if isinstance(value, list) else local_limits.append(str(value))
        outcome = inherited_outcome
        node_complete = inherited_complete and not node.get("truncated", False) and node.get("complete") is not False
        if not node_complete:
            local_limits.append("Source population is incomplete; unrestricted comparisons are not supported.")
        scoped_limits, scope_complete = _scoped_warnings(snapshot_warnings, seasons, node_season, end, tool)
        record_limits = tuple(dict.fromkeys(local_limits + scoped_limits))
        if node.get("found") is False:
            outcome = "not_found"
            local_limits.append("Requested evidence was not found; this is not support for a comparison.")
        elif node.get("error") or node.get("available") is False:
            outcome = "unavailable"
        elif outcome in {"found", "partial"} and (node.get("partial") is True or node.get("complete") is False):
            outcome = "partial"
        if tool in {"transactions", "team_transactions", "league_snapshot"} and node.get("type") in {"trade", "waiver", "free_agent"} and node.get("status") != "complete":
            outcome = "unavailable"
            local_limits.append("Transaction is not confirmed complete; listed assets are not evidence of completed movement.")
        record_limits = tuple(dict.fromkeys(local_limits + scoped_limits))
        fields: dict[str, Any] = {}
        paths: dict[str, str] = {}
        units: dict[str, str] = {}
        for key, value in node.items():
            if key in _PRIVATE or key.endswith("_uuid") or key == "roster_lookup":
                continue
            if isinstance(value, dict) or (isinstance(value, (list, tuple)) and any(isinstance(x, (dict, list, tuple)) for x in value)):
                continue
            if len(json.dumps(value, default=str)) > 1500:
                local_limits.append(f"Field {key} omitted from selected evidence because it exceeds the presentation size limit.")
                continue
            fields[key] = _numeric_value(key, value)
            paths[key] = f"{path}/{_escape(key)}"
            if _points_field(key) and isinstance(value, (int, float)):
                units[key] = "fantasy_points"
        if own_subject and not player_metric and tool != "player_weekly_log":
            _, roster_key = identity(str(own_subject), node_season)
            roster_key = node.get("sleeper_roster_id") or roster_key
            if roster_key is not None and node_season is not None:
                fields["roster_lookup"] = {"roster_key": str(roster_key), "season": node_season}
                paths["roster_lookup"] = f"{path}/team_name"
        if "assets_sent" in node and "assets_received" in node:
            sent = sum(a.get("asset_type") == "pick" for a in node["assets_sent"])
            received = sum(a.get("asset_type") == "pick" for a in node["assets_received"])
            fields["net_draft_picks"] = received - sent
            paths["net_draft_picks"] = f"{path}/assets_received - {path}/assets_sent (pick counts)"
            units["net_draft_picks"] = "draft_picks"
        if tool == "roster_at_cutoff" and path == "" and isinstance(node.get("roster"), dict):
            fields["roster_members"] = sorted(_roster_members(node["roster"]))
            paths["roster_members"] = "/roster/**/player_name (listed membership)"
        # Multi-team score fields must carry the owner of that side explicitly.
        sides = (("team_a", "points_a"), ("team_b", "points_b"),
                 ("winner_team_name", "winner_points"), ("loser_team_name", "loser_points"))
        for team_key, points_key in sides:
            if node.get(team_key) and points_key in node:
                fields.pop(points_key, None)
                paths.pop(points_key, None)
                units.pop(points_key, None)
                side_subject = str(node[team_key])
                side_id, _ = identity(side_subject, node_season)
                records.append(EvidenceRecord(
                    ref=f"{source}.r{len(records)}", source=source, tool=tool, outcome=outcome,
                    subject=side_subject, subject_id=side_id, season=node_season,
                    week_from=start, week_to=end,
                    fields={points_key: _numeric_value(points_key, node[points_key]), "team_name": side_subject},
                    field_paths={points_key: f"{path}/{points_key}", "team_name": f"{path}/{team_key}"},
                    units={points_key: "fantasy_points"}, limitations=record_limits,
                ))
        if fields or outcome != "found":
            records.append(EvidenceRecord(
                ref=f"{source}.r{len(records)}", source=source, tool=tool,
                outcome=outcome, subject=subject, subject_id=subject_id,
                season=node_season, week_from=start, week_to=end,
                perspective=perspective, fields=fields, field_paths=paths, units=units,
                temporal_kind="observation" if tool in {"roster_at_cutoff", "player_summary"} else "interval",
                complete=(node_complete and outcome == "found" and snapshot_population_complete and scope_complete
                          and _complete_population(tool, population)),
                population=population, limitations=tuple(dict.fromkeys(local_limits + scoped_limits)),
            ))
        for key, child in node.items():
            if key in _PRIVATE or key.endswith("_uuid") or key == "roster_lookup" or not isinstance(child, (dict, list, tuple)):
                continue
            if not child or (isinstance(child, (list, tuple)) and not any(isinstance(x, (dict, list, tuple)) for x in child)):
                continue
            child_subject, child_id = subject, subject_id
            if key in {"team_a_players", "team_b_players"}:
                child_subject = node.get("team_a" if key == "team_a_players" else "team_b")
                child_id, _ = identity(child_subject, node_season) if child_subject else (None, None)
            child_perspective = {"assets_sent": "sent", "assets_received": "received"}.get(key, perspective)
            child_start = 1 if key in {"standings", "standing"} else start
            visit(child, f"{path}/{_escape(key)}", child_subject, child_id, node_season,
                  child_start, end, child_perspective, population, tuple(local_limits), outcome, node_complete)

    root_subject = None
    if isinstance(raw, dict):
        team = raw.get("team") if isinstance(raw.get("team"), dict) else {}
        root_subject = raw.get("team_name") or team.get("team_name")
    root_id, _ = identity(root_subject, season) if root_subject else (None, None)
    visit(raw, "", root_subject, root_id, season, week_from, week_to, None, None, tuple(limitations))
    if not records:
        records.append(EvidenceRecord(
            ref=f"{source}.r0", source=source, tool=tool, outcome="not_found",
            season=season, week_from=week_from, week_to=week_to,
            limitations=tuple(limitations) + ("No records returned; absence is not positive outcome evidence.",),
        ))
    return tuple(records)


def evidence_page(records: tuple[EvidenceRecord, ...], offset: int = 0, limit: int = PAGE_SIZE) -> dict[str, Any]:
    if offset < 0 or not 1 <= limit <= PAGE_SIZE:
        raise ValueError(f"offset must be nonnegative and limit between 1 and {PAGE_SIZE}")
    selected = records[offset:offset + limit]
    scope = {
        key: getattr(selected[0], key)
        for key in ("season", "week_from", "week_to", "perspective", "temporal_kind")
        if selected and all(getattr(record, key) == getattr(selected[0], key) for record in selected)
    }
    visible = []
    limitations = list(dict.fromkeys(item for record in records for item in record.limitations))
    for record in selected:
        payload = asdict(record)
        payload.pop("field_paths")  # exact provenance remains in private audit
        payload.pop("source")
        payload.pop("tool")
        payload.pop("subject_id")
        if not record.complete:
            payload.pop("population")
        if record.limitations:
            payload["limitation_refs"] = [limitations.index(item) for item in record.limitations]
        payload.pop("limitations")
        for key in scope:
            payload.pop(key)
        for optional in ("population", "units"):
            if optional in payload and not payload[optional]:
                payload.pop(optional)
        payload["display"] = {
            key: f"{value:.2f}" for key, value in record.fields.items()
            if record.units.get(key) == "fantasy_points" and isinstance(value, (int, float))
        }
        if not payload["display"]:
            payload.pop("display")
        visible.append(payload)
    return {
        "evidence_version": EVIDENCE_VERSION,
        "source": records[0].source if records else None,
        "tool": records[0].tool if records else None,
        "scope": scope,
        "subjects": {record.subject: record.subject_id for record in selected if record.subject and record.subject_id},
        "records": visible,
        "total_records": len(records),
        "next_offset": offset + len(selected) if offset + len(selected) < len(records) else None,
        "limitations": limitations,
    }


def public_subject_id(franchise_id: str) -> str:
    return "franchise_" + sha256(franchise_id.encode()).hexdigest()[:20]


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _complete_population(tool: str, population: str | None) -> bool:
    """Only curated full standings collections currently certify comparisons."""
    return bool(population and population.endswith("/standings") and tool in {
        "standings", "league_snapshot", "league_history",
    })


def _sql_records(source: str, raw: dict[str, Any], limitations: tuple[str, ...]) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    columns = raw.get("columns", [])
    for index, row in enumerate(raw.get("rows", [])):
        fields, paths = {}, {}
        omitted = False
        for position, (column, value) in enumerate(zip(columns, row)):
            private_value = isinstance(value, str) and (
                re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|[0-9a-fA-F]{64}", value)
                or value.lstrip().startswith(("{", "["))
            )
            if column in _PRIVATE or column.endswith(("_uuid", "_json")) or private_value or len(json.dumps(value, default=str)) > 1500:
                omitted = True
                continue
            if columns.count(column) != 1:
                omitted = True
                continue
            fields[column] = value
            paths[column] = f"/rows/{index}/{position}"
        records.append(EvidenceRecord(
            ref=f"{source}.r{index}", source=source, tool="run_sql", outcome="partial",
            temporal_kind="unknown",
            fields=fields, field_paths=paths,
            limitations=limitations + (("Internal, serialized or oversized SQL fields were omitted from presentation.",) if omitted else ()),
        ))
    return tuple(records) or (EvidenceRecord(
        ref=f"{source}.r0", source=source, tool="run_sql", outcome="not_found",
        limitations=limitations + ("No SQL rows returned.",),
    ),)


def _roster_members(node: Any) -> set[str]:
    if isinstance(node, dict):
        name = node.get("player_name") or node.get("full_name")
        return ({str(name)} if name else set()).union(*(_roster_members(value) for value in node.values()))
    if isinstance(node, list):
        return set().union(*(_roster_members(value) for value in node))
    return set()


def _scoped_warnings(
    warnings: tuple[dict[str, Any], ...], seasons: list[dict[str, Any]],
    season: int | None, week_to: int | None, tool: str,
) -> tuple[list[str], bool]:
    """Apply domain warnings to the selected season and cutoff, preserving audit elsewhere."""
    scopes = {str(item["competition_season_id"]): item["season_year"] for item in seasons}
    limits: list[str] = []
    complete = True
    game_codes = {"snapshot.matchup_group_omitted", "snapshot.matchup_completion_unknown", "snapshot.league_average_record_incomplete"}
    for warning in warnings:
        code = warning["code"]
        scope = warning.get("scope_key") or {}
        parts = scope.get("value", "").split(":")
        warning_season = next((scopes[part] for part in parts if part in scopes), None)
        if season is not None and warning_season is not None and season != warning_season:
            continue
        if parts[0] == "matchups" and parts[-1].isdigit() and week_to is not None and int(parts[-1]) > week_to:
            continue
        if code == "snapshot.player_state_omitted" and tool not in {"player_summary", "player_weekly_log", "season_leaders", "week_player_leaderboard", "roster_at_cutoff", "roster_snapshot"}:
            continue
        if code == "snapshot.roster_reconstruction_limited" and tool not in {"roster_at_cutoff", "roster_snapshot"}:
            continue
        if code == "snapshot.bracket_cutoff_unknown" and tool not in {"playoff_bracket", "team_playoff_path"}:
            continue
        if code in game_codes and tool in {"transactions", "team_transactions", "player_summary", "roster_at_cutoff", "available_seasons"}:
            continue
        limits.append(warning["summary"])
        if code in game_codes:
            complete = False
    return limits, complete


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _points_field(key: str) -> bool:
    return "points" in key or key in {"score", "total", "avg"}


def _numeric_value(key: str, value: Any) -> Any:
    if _points_field(key) and isinstance(value, float):
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return value
