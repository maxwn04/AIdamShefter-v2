"""Normalization helpers for transactions."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from ..schema.models import Transaction, TransactionMove


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def normalize_transactions(
    raw_transactions: Iterable[Mapping[str, Any]],
    league_id: str,
    season: str,
    week: int,
) -> list[Transaction]:
    rows: list[Transaction] = []
    for raw_tx in raw_transactions:
        rows.append(
            Transaction(
                league_id=str(league_id),
                season=str(season),
                week=int(week),
                transaction_id=str(raw_tx["transaction_id"]),
                type=str(raw_tx.get("type", "")),
                status=raw_tx.get("status"),
                created_ts=raw_tx.get("created"),
                settings_json=_json_dumps(raw_tx.get("settings")),
                metadata_json=_json_dumps(raw_tx.get("metadata")),
            )
        )
    return rows


def _normalize_moves_from_map(
    moves: Mapping[str, Any] | None,
    *,
    transaction_id: str,
    direction: str,
    bid_amount: int | None = None,
) -> list[TransactionMove]:
    if not moves:
        return []
    rows: list[TransactionMove] = []
    for player_id, roster_id in moves.items():
        rows.append(
            TransactionMove(
                transaction_id=transaction_id,
                roster_id=int(roster_id) if roster_id is not None else None,
                player_id=str(player_id) if player_id is not None else None,
                asset_type="player",
                direction=direction,
                bid_amount=bid_amount,
                from_roster_id=None,
                to_roster_id=None,
                pick_season=None,
                pick_round=None,
                pick_original_roster_id=None,
                pick_id=None,
            )
        )
    return rows


def normalize_transaction_moves(
    raw_transactions: Iterable[Mapping[str, Any]],
) -> list[TransactionMove]:
    rows: list[TransactionMove] = []
    for raw_tx in raw_transactions:
        transaction_id = str(raw_tx["transaction_id"])
        settings = raw_tx.get("settings") or {}
        bid_amount = settings.get("waiver_bid") or settings.get("price")

        rows.extend(
            _normalize_moves_from_map(
                raw_tx.get("adds"),
                transaction_id=transaction_id,
                direction="add",
                bid_amount=bid_amount,
            )
        )
        rows.extend(
            _normalize_moves_from_map(
                raw_tx.get("drops"),
                transaction_id=transaction_id,
                direction="drop",
                bid_amount=bid_amount,
            )
        )

        for pick in raw_tx.get("draft_picks") or []:
            owner_id = pick.get("owner_id")
            previous_owner_id = pick.get("previous_owner_id")
            pick_season = pick.get("season")
            pick_round = pick.get("round")
            pick_original_roster_id = pick.get("roster_id")
            pick_id = pick.get("draft_pick_id")

            rows.append(
                TransactionMove(
                    transaction_id=transaction_id,
                    roster_id=int(previous_owner_id)
                    if previous_owner_id is not None
                    else None,
                    player_id=None,
                    asset_type="pick",
                    direction="pick_out",
                    bid_amount=bid_amount,
                    from_roster_id=int(previous_owner_id)
                    if previous_owner_id is not None
                    else None,
                    to_roster_id=int(owner_id) if owner_id is not None else None,
                    pick_season=str(pick_season) if pick_season is not None else None,
                    pick_round=int(pick_round) if pick_round is not None else None,
                    pick_original_roster_id=int(pick_original_roster_id)
                    if pick_original_roster_id is not None
                    else None,
                    pick_id=str(pick_id) if pick_id is not None else None,
                )
            )
            rows.append(
                TransactionMove(
                    transaction_id=transaction_id,
                    roster_id=int(owner_id) if owner_id is not None else None,
                    player_id=None,
                    asset_type="pick",
                    direction="pick_in",
                    bid_amount=bid_amount,
                    from_roster_id=int(previous_owner_id)
                    if previous_owner_id is not None
                    else None,
                    to_roster_id=int(owner_id) if owner_id is not None else None,
                    pick_season=str(pick_season) if pick_season is not None else None,
                    pick_round=int(pick_round) if pick_round is not None else None,
                    pick_original_roster_id=int(pick_original_roster_id)
                    if pick_original_roster_id is not None
                    else None,
                    pick_id=str(pick_id) if pick_id is not None else None,
                )
            )
    return rows
