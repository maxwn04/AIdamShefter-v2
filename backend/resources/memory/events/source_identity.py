"""Exact Sleeper trade identity used only by the event write boundary."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class SleeperTradeIdentity:
    competition_season_id: UUID
    league_id: str
    transaction_id: str

    @classmethod
    def from_hints(cls, hints: dict[str, Any], season_id: UUID) -> SleeperTradeIdentity:
        # Existing resolver receipts predate the explicit provider/league fields.
        # Their parameterized resolution queries retain the exact Sleeper league.
        if hints.get("provider", "sleeper") != "sleeper":
            raise ValueError("Trade receipt is not a Sleeper source")
        if hints.get("competition_season_id") != str(season_id):
            raise ValueError("Trade receipt and canonical season disagree")
        leagues = {str(q["parameters"]["league"]) for q in hints.get("resolution_queries", [])
                   if q.get("parameters", {}).get("league") is not None}
        if hints.get("league_id") is not None:
            leagues.add(str(hints["league_id"]))
        transaction = hints.get("transaction_id")
        if len(leagues) != 1 or not transaction or not next(iter(leagues)).strip():
            raise ValueError("Trade receipt lacks one exact league and transaction identity")
        return cls(season_id, next(iter(leagues)), str(transaction))

    @property
    def agent_key(self) -> str:
        identity = ["sleeper", str(self.competition_season_id), self.league_id, self.transaction_id]
        digest = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
        return "source-trade:" + digest
