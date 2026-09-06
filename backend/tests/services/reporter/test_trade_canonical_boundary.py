"""Frozen source -> selected evidence -> canonical PostgreSQL trade regression."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import Competition, CompetitionSeason, Franchise
from backend.database.models.memory import MemoryItem, MemoryRevision, MemoryVersion
from backend.database.models.reporting import Generation
from backend.database.models.sleeper import ApiRequest, Player, RefreshRun
from backend.database.sessions import create_session_factory
from backend.resources.memory.events import EventContent, TradeEventPayload
from backend.resources.memory.events.shared import insert_event_version, prepare_event_write
from backend.resources.memory.revisions.writers import persist_version_envelopes
from backend.services.datalayer import FrozenLeagueData, ReadyDataSnapshot
from backend.services.memory import GenerationMemoryContext
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.memory.test_event_manager import _manager
from backend.tests.services.datalayer.test_frozen_query_runtime import (
    _mutated_copy_many,
    v3_ready_snapshot,
)
from backend.tests.services.reporter.test_executed_evidence import execute, save, setup
from backend.tests.services.reporter.test_memory_tools import RecordingRetrieval, _call


def test_three_party_frozen_trade_persists_every_asset_and_exact_endpoint(
    v3_ready_snapshot: ReadyDataSnapshot, tmp_path: Path, database_engine: Engine,
) -> None:
    third_id = uuid4()
    changed = _mutated_copy_many(
        v3_ready_snapshot.artifact.path, tmp_path / "three-party.sqlite", (
            ("INSERT INTO rosters(league_id,roster_id) VALUES ('league-2026',3)", ()),
            ("INSERT INTO roster_identities SELECT league_id,3,competition_id,"
             "competition_season_id,?,? FROM roster_identities "
             "WHERE league_id='league-2026' AND roster_id=1", (str(uuid4()), str(third_id))),
            ("INSERT INTO team_profiles(league_id,roster_id,team_name,manager_name) "
             "VALUES ('league-2026',3,'Third Club','Third Manager')", ()),
            ("UPDATE team_profiles SET team_name='First Club' "
             "WHERE league_id='league-2026' AND roster_id=1", ()),
            ("UPDATE team_profiles SET team_name='Second Club' "
             "WHERE league_id='league-2026' AND roster_id=2", ()),
            ("UPDATE transactions SET type='trade',status='complete',created_ts=1788307200000 "
             "WHERE league_id='league-2026' AND transaction_id='tx1'", ()),
            ("DELETE FROM transaction_moves WHERE league_id='league-2026'", ()),
            # Paired source rows deliberately have different move indexes.
            ("INSERT INTO transaction_moves(league_id,transaction_id,move_index,roster_id,"
             "player_id,asset_type,direction,from_roster_id,to_roster_id) VALUES "
             "('league-2026','tx1',0,1,'p1','player','drop',1,2),"
             "('league-2026','tx1',10,2,'p1','player','add',1,2),"
             "('league-2026','tx1',1,2,'p2','player','drop',2,3),"
             "('league-2026','tx1',11,3,'p2','player','add',2,3)", ()),
            # Same draft year and round; original owner makes these distinct picks.
            ("INSERT INTO transaction_moves(league_id,transaction_id,move_index,roster_id,"
             "asset_type,direction,from_roster_id,to_roster_id,pick_season,pick_round,"
             "pick_original_roster_id) VALUES "
             "('league-2026','tx1',2,3,'pick','pick_out',3,1,'2026',1,1),"
             "('league-2026','tx1',12,1,'pick','pick_in',3,1,'2026',1,1),"
             "('league-2026','tx1',3,3,'pick','pick_out',3,2,'2026',1,2),"
             "('league-2026','tx1',13,2,'pick','pick_in',3,2,'2026',1,2)", ()),
        ),
    )
    with FrozenLeagueData.open(v3_ready_snapshot.model_copy(update={"artifact": changed})) as data:
        primary = next(season for season in data.available_seasons() if season.role == "primary")
        franchises = {
            roster: data.resolve_roster_identity(str(roster), season=2026).identity.franchise_id
            for roster in (1, 2, 3)
        }
        generation_id, root_id = uuid4(), uuid4()
        registry, context = setup(data)
        memory = GenerationMemoryContext(
            competition_id=primary.competition_id,
            generation_id=generation_id, pinned_revision_id=root_id,
            retrieval=RecordingRetrieval(),
            competition_season_id=primary.competition_season_id, week=1,
        )
        register_memory_tools(registry, memory, data)
        executed, records = execute(
            registry, context, "transactions", season=2026, week_from=1, week_to=1,
        )
        # Choose a model-visible binding, rather than injecting an EvidenceRecord.
        movement = next(record for record in records
                        if record.subject == "First Club" and record.perspective == "sent"
                        and record.fields.get("asset_type") == "player")
        shown = next(row for row in executed.result["records"] if row["ref"] == movement.ref)
        assert shown["fields"]["player_name"] == movement.fields["player_name"]
        assert save(context, movement, "player_name", "transaction", id="fact_trade")["ok"]
        fact = context.brief.brief.get_fact("fact_trade")
        assert fact is not None and fact.support_status == "traceable"
        assert len(fact.bindings) == 1 and fact.bindings[0].ref == shown["ref"]
        saved = _call(
            registry, "save_memory_event", id="three_party", event_type="trade",
            source_fact_ids=["fact_trade"], headline="Three clubs trade",
            summary="Two players and two distinct 2026 firsts changed hands.",
        )
        assert saved["saved"] is True, saved
        proposal, = memory.proposal_snapshot()
        assert isinstance(proposal.content, EventContent)
        assert proposal.content.source_hints["source_fact_ids"] == ["fact_trade"]
        assert proposal.metadata.occurred_at == datetime(2026, 9, 2, tzinfo=UTC)

    # Persist exactly the proposal produced by the registered memory tool.
    now = datetime.now(UTC)
    refresh_id, request_id = uuid4(), uuid4()
    with database_engine.begin() as connection:
        connection.execute(sa.insert(Competition), {
            "id": primary.competition_id, "display_name": "Frozen trade boundary",
        })
        connection.execute(sa.insert(CompetitionSeason), {
            "id": primary.competition_season_id, "competition_id": primary.competition_id,
            "season_year": 2026, "sequence_number": 1, "sleeper_league_id": "league-2026",
        })
        connection.execute(sa.insert(Franchise), [
            {"id": identity, "competition_id": primary.competition_id,
             "display_name": f"Club {roster}"} for roster, identity in franchises.items()
        ])
        connection.execute(sa.insert(Generation), {
            "id": generation_id, "competition_id": primary.competition_id,
            "competition_season_id": primary.competition_season_id, "kind": "test",
            "status": "pending", "request_text": "trade boundary", "requested_primary_model": "test",
            "settings_jsonb": {}, "current_turn": 0,
        })
        connection.execute(sa.insert(RefreshRun), {
            "id": refresh_id, "competition_id": primary.competition_id,
            "competition_season_id": primary.competition_season_id, "endpoint_scope": {},
            "trigger_source": "test", "status": "succeeded", "code_version": "test",
            "normalizer_version": "test",
        })
        connection.execute(sa.insert(ApiRequest), {
            "id": request_id, "refresh_run_id": refresh_id,
            "competition_season_id": primary.competition_season_id,
            "endpoint_kind": "players", "scope_key": "boundary-players", "request_path": "/test",
            "request_parameters": {}, "requested_at": now, "completed_at": now,
            "status": "succeeded", "normalization_status": "succeeded",
        })
        connection.execute(sa.insert(cast(sa.Table, Player.__table__)), [
            {"sleeper_player_id": player, "full_name": player, "metadata": {},
             "source_api_request_id": request_id} for player in ("p1", "p2")
        ])
        connection.execute(sa.insert(MemoryRevision), {
            "id": root_id, "competition_id": primary.competition_id,
            "sequence_number": 0, "state_content_hash": "boundary-root",
        })

    revision_id = uuid4()
    session_factory = create_session_factory(database_engine)
    with session_factory.begin() as session:
        revision = MemoryRevision(
            id=revision_id, competition_id=primary.competition_id, sequence_number=1,
            previous_revision_id=root_id, state_content_hash="boundary-trade",
        )
        item = MemoryItem(
            id=proposal.item_id, competition_id=primary.competition_id, kind="event",
            agent_key=proposal.metadata.agent_key,
        )
        version = MemoryVersion(
            id=proposal.version_id, item_id=proposal.item_id,
            competition_id=primary.competition_id, revision_number=1,
            content_schema_version=proposal.content.schema_version, introduced_revision_id=revision_id,
            competition_season_id=proposal.metadata.competition_season_id,
            week=proposal.metadata.week, occurred_at=proposal.metadata.occurred_at,
            creating_generation_id=generation_id,
        )
        persist_version_envelopes(session, revision, new_items=(item,), new_versions=(version,))
        prepared = prepare_event_write(session, primary.competition_id, proposal.content)
        insert_event_version(session, version, prepared)

    event = _manager(database_engine, primary.competition_id).exact(proposal.version_id)
    assert event.content == proposal.content
    assert event.version.occurred_at == proposal.metadata.occurred_at
    payload = event.content.details
    assert isinstance(payload, TradeEventPayload)
    assert payload.sender_franchise_id is None and payload.receiver_franchise_id is None
    assert len(payload.assets) == 4
    actual = {
        ((asset.kind, asset.player_id) if asset.kind == "player" else
         (asset.kind, asset.season, asset.round, asset.original_franchise_id)):
        (asset.from_franchise_id, asset.to_franchise_id)
        for asset in payload.assets
    }
    assert actual == {
        ("player", "p1"): (franchises[1], franchises[2]),
        ("player", "p2"): (franchises[2], franchises[3]),
        ("draft_pick", 2026, 1, franchises[1]): (franchises[3], franchises[1]),
        ("draft_pick", 2026, 1, franchises[2]): (franchises[3], franchises[2]),
    }
    assert all(asset.direction is None for asset in payload.assets)
    encoded = json.loads(event.content.model_dump_json())
    assert EventContent.model_validate(encoded) == event.content
