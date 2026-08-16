from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import Competition, CompetitionSeason, Franchise
from backend.database.models.memory import (
    CurrentRevision,
    EventVersion,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
)
from backend.database.models.reporting import AICall, Generation, ToolCall
from backend.database.models.sleeper import ApiRequest, DraftPick, Player, RefreshRun
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import (
    CrossCompetitionEntityReferenceError,
    CrossCompetitionReferenceError,
    EntityReferenceNotFoundError,
    StaleItemVersionError,
    WrongTargetKindError,
)
from backend.resources.memory.events import (
    EventContent,
    EventManager,
    MatchupEventPayload,
    TradeEventPayload,
)
from backend.resources.memory.events.shared import (
    insert_event_version,
    prepare_event_replacement,
    prepare_event_write,
)
from backend.resources.memory.revisions.writers import persist_version_envelopes
from backend.resources.memory.search_documents import (
    EVENT_DOCUMENT_BUILDER_VERSION,
    build_event_document,
)
from backend.tests.database.conftest import database_engine, migrated_database


@dataclass(frozen=True)
class EventDomain:
    competition_id: UUID
    season_id: UUID
    sender_id: UUID
    receiver_id: UUID
    player_id: str
    draft_pick_id: UUID
    generation_id: UUID
    tool_call_id: UUID
    api_request_id: UUID
    root_revision_id: UUID
    other_competition_id: UUID
    other_franchise_id: UUID
    other_draft_pick_id: UUID


def _seed_domain(database_engine: Engine) -> EventDomain:
    competition_id = uuid4()
    season_id = uuid4()
    sender_id = uuid4()
    receiver_id = uuid4()
    player_id = f"player-{uuid4()}"
    draft_pick_id = uuid4()
    generation_id = uuid4()
    ai_call_id = uuid4()
    tool_call_id = uuid4()
    refresh_run_id = uuid4()
    api_request_id = uuid4()
    root_revision_id = uuid4()
    other_competition_id = uuid4()
    other_franchise_id = uuid4()
    other_draft_pick_id = uuid4()
    now = datetime.now(UTC)

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            [
                {"id": competition_id, "display_name": "Event Manager League"},
                {
                    "id": other_competition_id,
                    "display_name": "Other Event League",
                },
            ],
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": season_id,
                "competition_id": competition_id,
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": f"league-{uuid4()}",
            },
        )
        connection.execute(
            sa.insert(Franchise),
            [
                {
                    "id": sender_id,
                    "competition_id": competition_id,
                    "display_name": "Sender Franchise",
                },
                {
                    "id": receiver_id,
                    "competition_id": competition_id,
                    "display_name": "Receiver Franchise",
                },
                {
                    "id": other_franchise_id,
                    "competition_id": other_competition_id,
                    "display_name": "Other Franchise",
                },
            ],
        )
        connection.execute(
            sa.insert(Generation),
            {
                "id": generation_id,
                "competition_id": competition_id,
                "competition_season_id": season_id,
                "kind": "test",
                "status": "pending",
                "request_text": "seed event manager",
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 0,
            },
        )
        connection.execute(
            sa.insert(RefreshRun),
            {
                "id": refresh_run_id,
                "competition_id": competition_id,
                "competition_season_id": season_id,
                "endpoint_scope": {},
                "trigger_source": "test",
                "status": "succeeded",
                "code_version": "test",
                "normalizer_version": "test",
            },
        )
        connection.execute(
            sa.insert(AICall),
            {
                "id": ai_call_id,
                "generation_id": generation_id,
                "turn_number": 1,
                "attempt_number": 1,
                "requested_model": "test-model",
                "input_messages": [],
                "tool_definitions": [],
                "request_parameters": {},
                "status": "succeeded",
            },
        )
        connection.execute(
            sa.insert(ToolCall),
            {
                "id": tool_call_id,
                "generation_id": generation_id,
                "ai_call_id": ai_call_id,
                "tool_ordinal": 0,
                "tool_name": "get_transactions",
                "implementation_version": "test",
                "arguments_jsonb": {},
                "status": "succeeded",
            },
        )
        connection.execute(
            sa.insert(ApiRequest),
            {
                "id": api_request_id,
                "refresh_run_id": refresh_run_id,
                "competition_season_id": season_id,
                "endpoint_kind": "transactions",
                "scope_key": f"transactions:{uuid4()}",
                "request_path": "/test",
                "request_parameters": {},
                "requested_at": now,
                "completed_at": now,
                "status": "succeeded",
                "normalization_status": "succeeded",
            },
        )
        connection.execute(
            sa.insert(cast(sa.Table, Player.__table__)),
            {
                "sleeper_player_id": player_id,
                "full_name": "Event Player",
                "metadata": {},
                "source_api_request_id": api_request_id,
            },
        )
        connection.execute(
            sa.insert(DraftPick),
            [
                {
                    "id": draft_pick_id,
                    "competition_id": competition_id,
                    "draft_season_year": 2027,
                    "round": 1,
                    "original_franchise_id": sender_id,
                    "current_franchise_id": sender_id,
                    "source": "seed",
                },
                {
                    "id": other_draft_pick_id,
                    "competition_id": other_competition_id,
                    "draft_season_year": 2027,
                    "round": 1,
                    "original_franchise_id": other_franchise_id,
                    "current_franchise_id": other_franchise_id,
                    "source": "seed",
                },
            ],
        )
        connection.execute(
            sa.insert(MemoryRevision),
            {
                "id": root_revision_id,
                "competition_id": competition_id,
                "sequence_number": 0,
                "competition_season_id": season_id,
                "week": 0,
                "state_content_hash": "seed-root",
            },
        )
        connection.execute(
            sa.insert(CurrentRevision),
            {
                "competition_id": competition_id,
                "current_revision_id": root_revision_id,
                "lock_version": 0,
            },
        )

    return EventDomain(
        competition_id=competition_id,
        season_id=season_id,
        sender_id=sender_id,
        receiver_id=receiver_id,
        player_id=player_id,
        draft_pick_id=draft_pick_id,
        generation_id=generation_id,
        tool_call_id=tool_call_id,
        api_request_id=api_request_id,
        root_revision_id=root_revision_id,
        other_competition_id=other_competition_id,
        other_franchise_id=other_franchise_id,
        other_draft_pick_id=other_draft_pick_id,
    )


def _trade(domain: EventDomain) -> EventContent:
    return EventContent.model_validate(
        {
            "event_type": "trade",
            "headline": "A blockbuster trade changed the league.",
            "summary": "The sender moved a star for a future pick and budget.",
            "salience": 5,
            "confidence": "source_backed",
            "status": "active",
            "details": {
                "kind": "trade",
                "sender_franchise_id": domain.sender_id,
                "receiver_franchise_id": domain.receiver_id,
                "assets": [
                    {
                        "kind": "player",
                        "direction": "sender_to_receiver",
                        "player_id": domain.player_id,
                    },
                    {
                        "kind": "draft_pick",
                        "direction": "receiver_to_sender",
                        "draft_pick_id": domain.draft_pick_id,
                    },
                    {
                        "kind": "budget",
                        "direction": "sender_to_receiver",
                        "amount": 15,
                    },
                ],
            },
            "primary_api_request_id": domain.api_request_id,
            "primary_tool_call_id": domain.tool_call_id,
            "source_hints": {"week": 6},
        }
    )


def _matchup(domain: EventDomain) -> EventContent:
    return EventContent.model_validate(
        {
            "event_type": "matchup",
            "headline": "The receiver won the rematch.",
            "summary": "The trade partners met without settling the argument.",
            "salience": 4,
            "confidence": "inferred",
            "status": "archived",
            "details": {
                "kind": "matchup",
                "winner_franchise_id": domain.receiver_id,
                "loser_franchise_id": domain.sender_id,
                "sleeper_matchup_id": "opaque-rematch-id",
            },
        }
    )


def _manager(database_engine: Engine, competition_id: UUID) -> EventManager:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "local_user"},
            "scope": {"kind": "competition", "competition_id": competition_id},
            "correlation_id": uuid4(),
        }
    )
    return EventManager(create_session_factory(database_engine), context)


def test_complete_event_create_replace_exact_history_and_projection(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    item_id = uuid4()
    first_version_id = uuid4()
    first_revision_id = uuid4()
    second_version_id = uuid4()
    second_revision_id = uuid4()

    with session_factory.begin() as session:
        first_revision = MemoryRevision(
            id=first_revision_id,
            competition_id=domain.competition_id,
            sequence_number=1,
            previous_revision_id=domain.root_revision_id,
            competition_season_id=domain.season_id,
            week=6,
            state_content_hash="test-event-state-one",
        )
        item = MemoryItem(
            id=item_id,
            competition_id=domain.competition_id,
            kind="event",
            agent_key="event:blockbuster",
        )
        version = MemoryVersion(
            id=first_version_id,
            item_id=item_id,
            competition_id=domain.competition_id,
            revision_number=1,
            content_schema_version=1,
            introduced_revision_id=first_revision_id,
            competition_season_id=domain.season_id,
            week=6,
            creating_generation_id=domain.generation_id,
            change_reason="record the trade",
        )
        persist_version_envelopes(
            session,
            first_revision,
            new_items=(item,),
            new_versions=(version,),
        )
        prepared = prepare_event_write(session, domain.competition_id, _trade(domain))
        insert_event_version(session, version, prepared)
        session.flush()
        session.execute(
            sa.update(CurrentRevision)
            .where(CurrentRevision.competition_id == domain.competition_id)
            .values(current_revision_id=first_revision_id, lock_version=1)
        )

    with session_factory.begin() as session:
        replacement_content = _matchup(domain)
        with pytest.raises(StaleItemVersionError):
            prepare_event_replacement(
                session,
                domain.competition_id,
                item_id,
                0,
                replacement_content,
            )
        replacement = prepare_event_replacement(
            session,
            domain.competition_id,
            item_id,
            1,
            replacement_content,
        )
        second_revision = MemoryRevision(
            id=second_revision_id,
            competition_id=domain.competition_id,
            sequence_number=2,
            previous_revision_id=first_revision_id,
            competition_season_id=domain.season_id,
            week=7,
            state_content_hash="test-event-state-two",
        )
        version = MemoryVersion(
            id=second_version_id,
            item_id=item_id,
            competition_id=domain.competition_id,
            revision_number=replacement.next_revision_number,
            content_schema_version=1,
            introduced_revision_id=second_revision_id,
            competition_season_id=domain.season_id,
            week=7,
            creating_generation_id=domain.generation_id,
            change_reason="record the rematch",
        )
        persist_version_envelopes(
            session,
            second_revision,
            new_items=(),
            new_versions=(version,),
            retired_versions=(replacement.previous_version,),
        )
        insert_event_version(session, version, replacement.validated)
        session.flush()
        session.execute(
            sa.update(CurrentRevision)
            .where(CurrentRevision.competition_id == domain.competition_id)
            .values(current_revision_id=second_revision_id, lock_version=2)
        )

    manager = _manager(database_engine, domain.competition_id)
    exact = manager.exact(first_version_id)
    history = manager.history(item_id)

    assert isinstance(exact.content.details, TradeEventPayload)
    assert exact.version.retired_revision_id == second_revision_id
    assert [event.version.version_id for event in history] == [
        second_version_id,
        first_version_id,
    ]
    assert isinstance(history[0].content.details, MatchupEventPayload)
    assert history[0].content.details.sleeper_matchup_id == "opaque-rematch-id"

    expected_projection = build_event_document(_trade(domain))
    with session_factory() as session:
        search_row = session.get_one(MemorySearchDocument, first_version_id)
        assert search_row.item_id == item_id
        assert search_row.competition_id == domain.competition_id
        assert search_row.kind == "event"
        assert search_row.status == "active"
        assert search_row.salience == 5
        assert search_row.builder_version == EVENT_DOCUMENT_BUILDER_VERSION
        assert search_row.content_hash == expected_projection.content_hash
        assert f"player:{domain.player_id}" in search_row.entity_keys
        assert search_row.evidence_version_ids == []
        assert search_row.related_item_ids == []
        assert search_row.tags == []
        event_row = session.get_one(EventVersion, first_version_id)
        assert event_row.primary_tool_call_generation_id == domain.generation_id
        assert session.scalar(
            sa.select(sa.func.count())
            .select_from(MemorySearchDocument)
            .where(MemorySearchDocument.item_id == item_id)
        ) == 2


def test_event_write_validates_payload_scope_receipts_and_item_boundary(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    content = _trade(domain)
    details = content.details
    assert isinstance(details, TradeEventPayload)

    missing_player = content.model_copy(
        update={
            "details": details.model_copy(
                update={
                    "assets": [
                        details.assets[0].model_copy(update={"player_id": "missing"}),
                        *details.assets[1:],
                    ]
                }
            )
        }
    )
    missing_pick = content.model_copy(
        update={
            "details": details.model_copy(
                update={
                    "assets": [
                        details.assets[0],
                        details.assets[1].model_copy(update={"draft_pick_id": uuid4()}),
                        details.assets[2],
                    ]
                }
            )
        }
    )
    cross_pick = content.model_copy(
        update={
            "details": details.model_copy(
                update={
                    "assets": [
                        details.assets[0],
                        details.assets[1].model_copy(
                            update={"draft_pick_id": domain.other_draft_pick_id}
                        ),
                        details.assets[2],
                    ]
                }
            )
        }
    )
    cross_franchise = content.model_copy(
        update={
            "details": details.model_copy(
                update={"sender_franchise_id": domain.other_franchise_id}
            )
        }
    )
    invalid_receipt = content.model_copy(
        update={"primary_api_request_id": uuid4()}
    )
    invalid_tool_receipt = content.model_copy(
        update={"primary_tool_call_id": uuid4(), "primary_api_request_id": None}
    )

    wrong_kind_item_id = uuid4()
    cross_scope_item_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(MemoryItem),
            [
                {
                    "id": wrong_kind_item_id,
                    "competition_id": domain.competition_id,
                    "kind": "fact",
                },
                {
                    "id": cross_scope_item_id,
                    "competition_id": domain.other_competition_id,
                    "kind": "event",
                },
            ],
        )

    with session_factory() as session:
        with pytest.raises(EntityReferenceNotFoundError):
            prepare_event_write(session, domain.competition_id, missing_player)
        with pytest.raises(EntityReferenceNotFoundError):
            prepare_event_write(session, domain.competition_id, missing_pick)
        with pytest.raises(CrossCompetitionEntityReferenceError):
            prepare_event_write(session, domain.competition_id, cross_pick)
        with pytest.raises(CrossCompetitionEntityReferenceError):
            prepare_event_write(session, domain.competition_id, cross_franchise)
        with pytest.raises(EntityReferenceNotFoundError):
            prepare_event_write(session, domain.competition_id, invalid_receipt)
        with pytest.raises(EntityReferenceNotFoundError):
            prepare_event_write(
                session, domain.competition_id, invalid_tool_receipt
            )
        with pytest.raises(WrongTargetKindError):
            prepare_event_replacement(
                session,
                domain.competition_id,
                wrong_kind_item_id,
                1,
                content,
            )
        with pytest.raises(CrossCompetitionReferenceError):
            prepare_event_replacement(
                session,
                domain.competition_id,
                cross_scope_item_id,
                1,
                content,
            )

        prepared = prepare_event_write(session, domain.competition_id, content)
        mismatched_version = MemoryVersion(
            id=uuid4(),
            item_id=uuid4(),
            competition_id=uuid4(),
            revision_number=1,
            introduced_revision_id=uuid4(),
        )
        with pytest.raises(CrossCompetitionReferenceError):
            insert_event_version(session, mismatched_version, prepared)


def test_event_content_and_projection_roll_back_with_canonical_envelope(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    item_id = uuid4()
    version_id = uuid4()
    revision_id = uuid4()

    with pytest.raises(RuntimeError, match="abort canonical write"):
        with session_factory.begin() as session:
            revision = MemoryRevision(
                id=revision_id,
                competition_id=domain.competition_id,
                sequence_number=1,
                previous_revision_id=domain.root_revision_id,
                competition_season_id=domain.season_id,
                week=6,
                state_content_hash="must-roll-back",
            )
            item = MemoryItem(
                id=item_id,
                competition_id=domain.competition_id,
                kind="event",
            )
            version = MemoryVersion(
                id=version_id,
                item_id=item_id,
                competition_id=domain.competition_id,
                revision_number=1,
                content_schema_version=1,
                introduced_revision_id=revision_id,
                competition_season_id=domain.season_id,
                week=6,
                creating_generation_id=domain.generation_id,
            )
            persist_version_envelopes(
                session,
                revision,
                new_items=(item,),
                new_versions=(version,),
            )
            prepared = prepare_event_write(
                session,
                domain.competition_id,
                _trade(domain),
            )
            insert_event_version(session, version, prepared)
            session.flush()
            assert session.get(EventVersion, version_id) is not None
            assert session.get(MemorySearchDocument, version_id) is not None
            raise RuntimeError("abort canonical write")

    with database_engine.connect() as connection:
        for model, id_column in (
            (MemoryRevision, MemoryRevision.id),
            (MemoryItem, MemoryItem.id),
            (MemoryVersion, MemoryVersion.id),
            (EventVersion, EventVersion.version_id),
            (MemorySearchDocument, MemorySearchDocument.version_id),
        ):
            expected_id = (
                revision_id
                if model is MemoryRevision
                else item_id if model is MemoryItem else version_id
            )
            assert connection.scalar(
                sa.select(sa.func.count())
                .select_from(model)
                .where(id_column == expected_id)
            ) == 0
