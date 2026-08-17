from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import Competition, CompetitionSeason, Franchise
from backend.database.models.memory import (
    CurrentRevision,
    EventVersion,
    FactVersion,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
)
from backend.database.models.reporting import Generation
from backend.database.models.sleeper import ApiRequest, RefreshRun
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import (
    CrossCompetitionReferenceError,
    EntityReferenceNotFoundError,
    StaleItemVersionError,
    WrongTargetKindError,
)
from backend.resources.memory.facts.manager import FactManager
from backend.resources.memory.facts.objects import FactContent
from backend.resources.memory.facts.shared import (
    insert_fact_version,
    prepare_fact_replacement,
    prepare_fact_write,
)
from backend.resources.memory.revisions.writers import persist_version_envelopes
from backend.resources.memory.search_documents import (
    FACT_DOCUMENT_BUILDER_VERSION,
    build_fact_document,
)
from backend.tests.database.conftest import database_engine, migrated_database


@dataclass(frozen=True)
class FactDomain:
    competition_id: UUID
    season_id: UUID
    franchise_id: UUID
    generation_id: UUID
    api_request_id: UUID
    event_version_id: UUID
    root_revision_id: UUID


def _seed_domain(database_engine: Engine) -> FactDomain:
    competition_id = uuid4()
    season_id = uuid4()
    franchise_id = uuid4()
    generation_id = uuid4()
    refresh_run_id = uuid4()
    api_request_id = uuid4()
    root_revision_id = uuid4()
    event_item_id = uuid4()
    event_version_id = uuid4()
    now = datetime.now(UTC)

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": "Fact Manager League"},
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
            {
                "id": franchise_id,
                "competition_id": competition_id,
                "display_name": "Fact Manager Franchise",
            },
        )
        connection.execute(
            sa.insert(Generation),
            {
                "id": generation_id,
                "competition_id": competition_id,
                "competition_season_id": season_id,
                "kind": "test",
                "status": "pending",
                "request_text": "seed fact manager",
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
            sa.insert(ApiRequest),
            {
                "id": api_request_id,
                "refresh_run_id": refresh_run_id,
                "competition_season_id": season_id,
                "endpoint_kind": "league",
                "scope_key": f"league:{uuid4()}",
                "request_path": "/test",
                "request_parameters": {},
                "requested_at": now,
                "completed_at": now,
                "status": "succeeded",
                "normalization_status": "succeeded",
            },
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
        connection.execute(
            sa.insert(MemoryItem),
            {
                "id": event_item_id,
                "competition_id": competition_id,
                "kind": "event",
            },
        )
        connection.execute(
            sa.insert(MemoryVersion),
            {
                "id": event_version_id,
                "item_id": event_item_id,
                "competition_id": competition_id,
                "revision_number": 1,
                "introduced_revision_id": root_revision_id,
                "competition_season_id": season_id,
                "week": 0,
                "creating_generation_id": generation_id,
            },
        )
        connection.execute(
            sa.insert(EventVersion),
            {
                "version_id": event_version_id,
                "competition_id": competition_id,
                "event_type": "matchup",
                "headline": "Seed matchup event",
                "summary": "A typed event used as exact fact evidence.",
                "salience": 1,
                "confidence": "unverified",
                "status": "active",
                "details": {
                    "kind": "matchup",
                    "winner_franchise_id": str(franchise_id),
                    "loser_franchise_id": str(uuid4()),
                    "sleeper_matchup_id": "seed-matchup",
                },
            },
        )

    return FactDomain(
        competition_id=competition_id,
        season_id=season_id,
        franchise_id=franchise_id,
        generation_id=generation_id,
        api_request_id=api_request_id,
        event_version_id=event_version_id,
        root_revision_id=root_revision_id,
    )


def _content(domain: FactDomain, *, replacement: bool = False) -> FactContent:
    return FactContent.model_validate(
        {
            "claim": (
                "The franchise's streak ended at six games."
                if replacement
                else "The franchise won six straight games."
            ),
            "category": "streak",
            "numbers": {"wins": 6},
            "confidence": "inferred" if replacement else "source_backed",
            "status": "archived" if replacement else "active",
            "subjects": [
                {
                    "kind": "franchise",
                    "id": domain.franchise_id,
                    "role": "subject",
                    "display_name": "Fact Manager Franchise",
                }
            ],
            "originating_event_version_ids": [domain.event_version_id],
            "primary_api_request_id": None if replacement else domain.api_request_id,
            "source_hints": {"week": 6},
        }
    )


def _manager(database_engine: Engine, competition_id: UUID) -> FactManager:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "local_user"},
            "scope": {"kind": "competition", "competition_id": competition_id},
            "correlation_id": uuid4(),
        }
    )
    return FactManager(create_session_factory(database_engine), context)


def test_complete_fact_create_replace_exact_and_history(
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
            state_content_hash="test-state-one",
        )
        item = MemoryItem(
            id=item_id,
            competition_id=domain.competition_id,
            kind="fact",
            agent_key="fact:streak",
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
            change_reason="record the streak",
        )
        persist_version_envelopes(
            session,
            first_revision,
            new_items=(item,),
            new_versions=(version,),
        )
        prepared = prepare_fact_write(session, domain.competition_id, _content(domain))
        insert_fact_version(session, version, prepared)
        session.flush()
        session.execute(
            sa.update(CurrentRevision)
            .where(CurrentRevision.competition_id == domain.competition_id)
            .values(current_revision_id=first_revision_id, lock_version=1)
        )

    with session_factory.begin() as session:
        second_revision = MemoryRevision(
            id=second_revision_id,
            competition_id=domain.competition_id,
            sequence_number=2,
            previous_revision_id=first_revision_id,
            competition_season_id=domain.season_id,
            week=7,
            state_content_hash="test-state-two",
        )
        replacement_content = _content(domain, replacement=True)
        with pytest.raises(StaleItemVersionError):
            prepare_fact_replacement(
                session,
                domain.competition_id,
                item_id,
                0,
                replacement_content,
            )
        replacement = prepare_fact_replacement(
            session,
            domain.competition_id,
            item_id,
            1,
            replacement_content,
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
            change_reason="close the streak",
        )
        persist_version_envelopes(
            session,
            second_revision,
            new_items=(),
            new_versions=(version,),
            retired_versions=(replacement.previous_version,),
        )
        insert_fact_version(session, version, replacement.validated)
        session.flush()
        session.execute(
            sa.update(CurrentRevision)
            .where(CurrentRevision.competition_id == domain.competition_id)
            .values(current_revision_id=second_revision_id, lock_version=2)
        )

    manager = _manager(database_engine, domain.competition_id)
    exact = manager.exact(first_version_id)
    history = manager.history(item_id)

    assert exact.content.status == "active"
    assert exact.content.confidence == "source_backed"
    assert exact.content.primary_api_request_id == domain.api_request_id
    assert exact.content.originating_event_version_ids == [domain.event_version_id]
    assert exact.version.retired_revision_id == second_revision_id
    assert [fact.version.version_id for fact in history] == [
        second_version_id,
        first_version_id,
    ]
    assert history[0].content.status == "archived"
    assert history[0].content.confidence == "inferred"

    expected_projection = build_fact_document(_content(domain))
    with session_factory() as session:
        search_row = session.get_one(MemorySearchDocument, first_version_id)
        assert search_row.version_id == first_version_id
        assert search_row.item_id == item_id
        assert search_row.competition_id == domain.competition_id
        assert search_row.competition_season_id == domain.season_id
        assert search_row.week == 6
        assert search_row.kind == "fact"
        assert search_row.status == "active"
        assert search_row.builder_version == FACT_DOCUMENT_BUILDER_VERSION
        assert search_row.content_hash == expected_projection.content_hash
        assert search_row.entity_keys == [f"franchise:{domain.franchise_id}"]
        assert search_row.evidence_version_ids == [domain.event_version_id]
        assert search_row.related_item_ids == []
        assert search_row.tags == []
        assert session.scalar(
            sa.select(sa.func.count())
            .select_from(MemorySearchDocument)
            .where(MemorySearchDocument.item_id == item_id)
        ) == 2


def test_fact_write_validates_subject_origin_and_receipt_before_rollback(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    non_event_item_id = uuid4()
    non_event_version_id = uuid4()
    item_id = uuid4()
    version_id = uuid4()
    revision_id = uuid4()
    valid_content = _content(domain)
    missing_subject = valid_content.model_copy(
        update={
            "subjects": [
                valid_content.subjects[0].model_copy(update={"id": uuid4()})
            ]
        }
    )
    wrong_origin = valid_content.model_copy(
        update={"originating_event_version_ids": [non_event_version_id]}
    )
    invalid_receipt = valid_content.model_copy(
        update={"primary_api_request_id": uuid4()}
    )

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(MemoryItem),
            {
                "id": non_event_item_id,
                "competition_id": domain.competition_id,
                "kind": "storyline",
            },
        )
        connection.execute(
            sa.insert(MemoryVersion),
            {
                "id": non_event_version_id,
                "item_id": non_event_item_id,
                "competition_id": domain.competition_id,
                "revision_number": 1,
                "introduced_revision_id": domain.root_revision_id,
                "competition_season_id": domain.season_id,
                "week": 0,
                "creating_generation_id": domain.generation_id,
            },
        )

    with session_factory() as session:
        with pytest.raises(EntityReferenceNotFoundError):
            prepare_fact_write(session, domain.competition_id, missing_subject)
        with pytest.raises(WrongTargetKindError):
            prepare_fact_write(session, domain.competition_id, wrong_origin)
        prepared = prepare_fact_write(session, domain.competition_id, valid_content)
        mismatched_version = MemoryVersion(
            id=uuid4(),
            item_id=uuid4(),
            competition_id=uuid4(),
            revision_number=1,
            introduced_revision_id=uuid4(),
        )
        with pytest.raises(CrossCompetitionReferenceError):
            insert_fact_version(session, mismatched_version, prepared)

    with (
        pytest.raises(EntityReferenceNotFoundError),
        session_factory.begin() as session,
    ):
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
            kind="fact",
        )
        version = MemoryVersion(
            id=version_id,
            item_id=item_id,
            competition_id=domain.competition_id,
            revision_number=1,
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
        prepared = prepare_fact_write(session, domain.competition_id, invalid_receipt)
        insert_fact_version(session, version, prepared)

    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(MemoryRevision)
            .where(MemoryRevision.id == revision_id)
        ) == 0
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(MemoryItem)
            .where(MemoryItem.id == item_id)
        ) == 0
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(MemoryVersion)
            .where(MemoryVersion.id == version_id)
        ) == 0
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(FactVersion)
            .where(FactVersion.version_id == version_id)
        ) == 0
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(MemorySearchDocument)
            .where(MemorySearchDocument.version_id == version_id)
        ) == 0
        assert connection.scalar(
            sa.select(CurrentRevision.current_revision_id).where(
                CurrentRevision.competition_id == domain.competition_id
            )
        ) == domain.root_revision_id


def test_fact_content_and_projection_roll_back_with_canonical_envelope(
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
                kind="fact",
            )
            version = MemoryVersion(
                id=version_id,
                item_id=item_id,
                competition_id=domain.competition_id,
                revision_number=1,
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

            prepared = prepare_fact_write(
                session,
                domain.competition_id,
                _content(domain),
            )
            insert_fact_version(session, version, prepared)
            session.flush()
            assert session.get(FactVersion, version_id) is not None
            assert session.scalar(
                sa.select(sa.func.count())
                .select_from(MemorySearchDocument)
                .where(MemorySearchDocument.version_id == version_id)
            ) == 1
            raise RuntimeError("abort canonical write")

    with database_engine.connect() as connection:
        for model, id_column in (
            (MemoryRevision, MemoryRevision.id),
            (MemoryItem, MemoryItem.id),
            (MemoryVersion, MemoryVersion.id),
            (FactVersion, FactVersion.version_id),
            (MemorySearchDocument, MemorySearchDocument.version_id),
        ):
            expected_id = revision_id if model is MemoryRevision else (
                item_id if model is MemoryItem else version_id
            )
            assert connection.scalar(
                sa.select(sa.func.count())
                .select_from(model)
                .where(id_column == expected_id)
            ) == 0
