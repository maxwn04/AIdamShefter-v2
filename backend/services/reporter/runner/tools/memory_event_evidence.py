"""Resolve durable event details from saved facts and the same frozen snapshot.

The brief supplies selected, validated evidence; the snapshot supplies hidden
identities and the complete event. Model-authored identifiers are never used.
Resolution is exact and fails closed on ambiguous or insufficient evidence.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any
from uuid import UUID

from backend.services.reporter.runner.evidence import EvidenceRecord
from backend.services.reporter.runner.grounding import validate_fact
from backend.services.reporter.runner.research_brief import ResearchBriefError
from backend.services.reporter.runner.tools.evidence_presentation import public_subject_id

if TYPE_CHECKING:
    from backend.services.datalayer import FrozenLeagueData
    from backend.services.reporter.runner.tools.context import ToolContext


class EventEvidenceError(ValueError):
    """Actionable pre-proposal failure; no dependent memory has been selected."""


@dataclass(frozen=True)
class ResolvedEvent:
    details: dict[str, Any]
    week: int
    audit: dict[str, Any]
    occurred_at: datetime | None = None


def resolve_event(
    context: ToolContext, data: FrozenLeagueData, event_type: str,
    fact_ids: list[str], *, competition_season_id: UUID,
) -> ResolvedEvent:
    records: dict[str, EvidenceRecord] = {}
    facts = []
    for fact_id in dict.fromkeys(fact_ids):
        fact = context.brief.brief.get_fact(fact_id)
        if fact is None or fact.support_status != "traceable":
            raise EventEvidenceError(
                f"{fact_id} is not a successfully saved traceable fact. Save the supporting fact first; do not invent event IDs."
            )
        try:
            validate_fact(fact, context.evidence)
        except ResearchBriefError as error:
            raise EventEvidenceError(f"{fact_id} no longer has valid source bindings: {error}") from error
        facts.append(fact)
        for binding in fact.bindings:
            record = context.evidence.resolve(binding.ref)
            if record is not None:
                records[record.ref] = record
    if event_type == "matchup":
        selected = [r for r in records.values() if r.tool in {
            "week_games", "team_game", "league_snapshot", "team_playoff_path",
        } and any(k in r.fields for k in ("points_a", "points_b", "winner_points", "loser_points"))]
    else:
        selected = [r for r in records.values() if r.tool in {
            "transactions", "team_transactions", "league_snapshot",
        } and r.perspective in {"sent", "received"} and "asset_type" in r.fields]
    if not selected:
        needed = "team matchup scores" if event_type == "matchup" else "sent/received transaction assets"
        raise EventEvidenceError(f"Selected facts need executed {needed}, not standings, prose references, or guessed typed details.")
    scopes = {(r.season, r.fields.get("source_week", r.week_from),
               r.fields.get("source_week", r.week_to)) for r in selected} if event_type == "trade" else {
                   (r.season, r.week_from, r.week_to) for r in selected}
    if len(scopes) != 1:
        raise EventEvidenceError("Select facts for one event in one season and week; split different events into separate saves.")
    season, start, end = next(iter(scopes))
    if season is None or start is None or start != end:
        raise EventEvidenceError("Event evidence needs a single explicit season and week. Query the individual event and save its fact.")
    snapshot_season = next((s for s in data.available_seasons() if s.season_year == season), None)
    if snapshot_season is None:
        raise EventEvidenceError("The fact season is unavailable in the frozen snapshot.")
    if snapshot_season.competition_season_id != competition_season_id:
        raise EventEvidenceError("This generation can save events only for its own season. Keep the historical fact as a research lead; do not relabel it as a current-season event.")
    if start > snapshot_season.through_week:
        raise EventEvidenceError("The event is beyond this frozen season's cutoff.")
    audit: dict[str, Any] = {"source_fact_ids": [f.id for f in facts],
        "bindings": [b.model_dump(mode="json") for f in facts for b in f.bindings],
        "season": season, "week": start,
        "competition_season_id": str(snapshot_season.competition_season_id),
        "resolution_queries": []}

    def query(sql: str, **params: Any) -> list[dict[str, Any]]:
        result = data.run_sql(sql, {"league": snapshot_season.sleeper_league_id,
                                   "week": start, **params}, limit=200)
        rows = [dict(zip(result["columns"], row, strict=True)) for row in result["rows"]]
        audit["resolution_queries"].append({"sql": sql, "parameters": {
            "league": snapshot_season.sleeper_league_id, "week": start, **params}, "rows": rows})
        if len(rows) >= 200:
            raise EventEvidenceError("Frozen event resolution exceeded its row bound. Narrow the source event before retrying.")
        return rows

    if event_type == "matchup":
        games = query("""SELECT g.*, a.franchise_id AS franchise_a,
            b.franchise_id AS franchise_b, pa.team_name AS team_a, pb.team_name AS team_b
            FROM games g JOIN roster_identities a ON a.league_id=g.league_id AND a.roster_id=g.roster_id_a
            JOIN roster_identities b ON b.league_id=g.league_id AND b.roster_id=g.roster_id_b
            JOIN team_profiles pa ON pa.league_id=g.league_id AND pa.roster_id=g.roster_id_a
            JOIN team_profiles pb ON pb.league_id=g.league_id AND pb.roster_id=g.roster_id_b
            WHERE g.league_id=:league AND g.week=:week""")
        matches = [g for g in games if all(_matches_game(record, g) for record in selected)]
        if len(matches) != 1:
            raise EventEvidenceError("The saved facts do not identify exactly one frozen matchup. Select scores for the same matchup; verify its season and teams.")
        game = matches[0]
        if game["winner_roster_id"] is None:
            raise EventEvidenceError("A tied or unplayed game cannot be saved as a winner/loser matchup event.")
        winning_side = "a" if game["winner_roster_id"] == game["roster_id_a"] else "b"
        losing_side = "b" if winning_side == "a" else "a"
        return ResolvedEvent({"kind": "matchup", "sleeper_matchup_id": str(game["matchup_id"]),
            "winner_franchise_id": game[f"franchise_{winning_side}"],
            "loser_franchise_id": game[f"franchise_{losing_side}"]}, start, audit)

    moves = query("""SELECT t.transaction_id, t.week, t.created_ts, tm.*, p.full_name AS player_name,
        ri.franchise_id, origin.franchise_id AS original_franchise_id,
        tp.team_name, original_team.team_name AS pick_original_team_name,
        sender.franchise_id AS sender_franchise_id, receiver.franchise_id AS receiver_franchise_id
        FROM transactions t JOIN transaction_moves tm ON tm.league_id=t.league_id AND tm.transaction_id=t.transaction_id
        LEFT JOIN players p ON p.player_id=tm.player_id
        JOIN roster_identities ri ON ri.league_id=tm.league_id AND ri.roster_id=tm.roster_id
        JOIN team_profiles tp ON tp.league_id=tm.league_id AND tp.roster_id=tm.roster_id
        LEFT JOIN roster_identities origin ON origin.league_id=tm.league_id AND origin.roster_id=tm.pick_original_roster_id
        LEFT JOIN team_profiles original_team ON original_team.league_id=tm.league_id AND original_team.roster_id=tm.pick_original_roster_id
        LEFT JOIN roster_identities sender ON sender.league_id=tm.league_id AND sender.roster_id=tm.from_roster_id
        LEFT JOIN roster_identities receiver ON receiver.league_id=tm.league_id AND receiver.roster_id=tm.to_roster_id
        WHERE t.league_id=:league AND t.week=:week AND t.type='trade' AND t.status='complete'
        ORDER BY t.transaction_id, tm.move_index, tm.direction""")
    transactions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for move in moves:
        transactions[move["transaction_id"]].append(move)
    matches = [rows for rows in transactions.values()
               if all(any(_matches_move(record, row) for row in rows) for record in selected)]
    if len(matches) != 1:
        raise EventEvidenceError("The directional asset facts do not identify exactly one completed trade. Add a distinguishing asset/participant fact; keep each trade separate.")
    matched = matches[0]
    participants = {r["franchise_id"] for r in matched}
    if len(participants) != 2:
        raise EventEvidenceError("Durable trade events currently support exactly two franchises; this trade needs a different representation.")
    sender, receiver = sorted(participants)
    assets: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in matched:
        if row["direction"] not in {"add", "drop", "pick_in", "pick_out"}:
            raise EventEvidenceError("The frozen trade includes an unsupported transfer direction; no partial event was saved.")
        if {row["sender_franchise_id"], row["receiver_franchise_id"]} != participants:
            raise EventEvidenceError("The frozen trade is missing an exact asset transfer identity; no partial event was saved.")
        direction = "sender_to_receiver" if row["sender_franchise_id"] == sender else "receiver_to_sender"
        if row["asset_type"] == "player" and row["player_id"]:
            key = ("player", row["player_id"])
            asset = {"kind": "player", "direction": direction, "player_id": row["player_id"]}
        elif row["asset_type"] == "pick" and row["original_franchise_id"]:
            try:
                draft_year = int(row["pick_season"])
                draft_round = int(row["pick_round"])
            except (TypeError, ValueError) as error:
                raise EventEvidenceError(
                    "The frozen pick lacks a draft year or round; no partial event was saved."
                ) from error
            key = ("draft_pick", row["pick_season"], row["pick_round"], row["original_franchise_id"])
            asset = {"kind": "draft_pick", "direction": direction, "season": draft_year,
                     "round": draft_round, "original_franchise_id": row["original_franchise_id"]}
        else:
            raise EventEvidenceError("An asset cannot be represented with its frozen identity; no assets were silently dropped.")
        if key in assets and assets[key] != asset:
            raise EventEvidenceError("Duplicate asset transfers prevent an unambiguous trade event.")
        assets[key] = asset
    if not assets:
        raise EventEvidenceError("No complete transferable assets were present; no event was saved.")
    audit["transaction_id"] = matched[0]["transaction_id"]
    timestamp = matched[0].get("created_ts")
    occurred_at = datetime.fromtimestamp(timestamp / 1000, tz=UTC) if timestamp is not None else None
    audit["source_week"] = start
    audit["occurred_at"] = occurred_at.isoformat() if occurred_at else None
    audit["temporal_note"] = "source_week is the provider grouping; occurred_at is the actual source timestamp when available"
    return ResolvedEvent({"kind": "trade", "sender_franchise_id": sender,
        "receiver_franchise_id": receiver, "assets": list(assets.values())}, start, audit, occurred_at)


def _same_number(left: Any, right: Any) -> bool:
    return Decimal(str(left)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal(str(right)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _matches_game(record: EvidenceRecord, game: dict[str, Any]) -> bool:
    number = record.fields.get("sleeper_matchup_number")
    if number is not None and str(number) != str(game["matchup_id"]):
        return False
    for side in ("a", "b"):
        identity_matches = record.subject_id == public_subject_id(game[f"franchise_{side}"]) if record.subject_id else record.subject == game[f"team_{side}"]
        if identity_matches:
            scores = [record.fields[k] for k in ("points_a", "points_b", "winner_points", "loser_points") if k in record.fields]
            return bool(scores) and all(_same_number(score, game[f"points_{side}"]) for score in scores)
    return False


def _matches_move(record: EvidenceRecord, row: dict[str, Any]) -> bool:
    identity_matches = record.subject_id == public_subject_id(row["franchise_id"]) if record.subject_id else record.subject == row["team_name"]
    direction = "received" if row["direction"] in {"add", "pick_in"} else "sent"
    if not identity_matches or record.perspective != direction:
        return False
    if record.fields.get("occurred_at"):
        if row.get("created_ts") is None:
            return False
        expected = datetime.fromisoformat(str(record.fields["occurred_at"]).replace("Z", "+00:00"))
        if expected != datetime.fromtimestamp(row["created_ts"] / 1000, tz=UTC):
            return False
    for key in ("asset_type", "player_name", "pick_season", "pick_round", "pick_original_team_name"):
        if key in record.fields and str(record.fields[key]) != str(row.get(key)):
            return False
    return any(key in record.fields for key in ("player_name", "pick_season"))
