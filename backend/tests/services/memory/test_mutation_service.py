from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from pydantic import TypeAdapter
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
    StorylineVersion,
    TriggerVersion,
)
from backend.database.models.memory.context_notes import (
    ContextNote as ContextNoteRow,
)
from backend.database.models.memory.context_notes import ContextNoteVersion
from backend.database.models.reporting import Generation
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import (
    DuplicateContextNoteError,
    StaleCanonicalRevisionError,
    WrongTargetKindError,
)
from backend.resources.memory.context_notes.objects import (
    ContextNoteContent,
    ContextNoteIdentity,
)
from backend.resources.memory.events.objects import EventContent
from backend.resources.memory.facts.objects import FactContent
from backend.resources.memory.revisions import RevisionManager
from backend.resources.memory.storylines.objects import StorylineContent
from backend.resources.memory.triggers.objects import TriggerContent
from backend.services.memory import (
    GenerationMemoryContext,
    MemoryMutationBundle,
    MemoryMutationOrigin,
    MemoryMutationService,
)
from backend.tests.database.conftest import database_engine, migrated_database


class EmptyRetrieval:
    def search(self, **_kwargs: object) -> object:
        return ()


class Domain:
    def __init__(self) -> None:
        self.competition_id = uuid4()
        self.season_id = uuid4()
        self.winner_id = uuid4()
        self.loser_id = uuid4()
        self.generation_id = uuid4()
        self.root_revision_id = uuid4()


def _seed_domain(engine: Engine) -> Domain:
    domain = Domain()
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {
                "id": domain.competition_id,
                "display_name": "Mutation Bundle League",
            },
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": domain.season_id,
                "competition_id": domain.competition_id,
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": f"league-{domain.competition_id}",
            },
        )
        connection.execute(
            sa.insert(Franchise),
            [
                {
                    "id": domain.winner_id,
                    "competition_id": domain.competition_id,
                    "display_name": "Owls",
                },
                {
                    "id": domain.loser_id,
                    "competition_id": domain.competition_id,
                    "display_name": "Foxes",
                },
            ],
        )
        connection.execute(
            sa.insert(Generation),
            {
                "id": domain.generation_id,
                "competition_id": domain.competition_id,
                "competition_season_id": domain.season_id,
                "kind": "test",
                "status": "pending",
                "request_text": "commit a memory bundle",
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 0,
            },
        )
        connection.execute(
            sa.insert(MemoryRevision),
            {
                "id": domain.root_revision_id,
                "competition_id": domain.competition_id,
                "sequence_number": 0,
                "competition_season_id": domain.season_id,
                "week": 0,
                "state_content_hash": "seed-root",
            },
        )
        connection.execute(
            sa.insert(CurrentRevision),
            {
                "competition_id": domain.competition_id,
                "current_revision_id": domain.root_revision_id,
                "lock_version": 0,
            },
        )
    return domain


def _add_generation(engine: Engine, domain: Domain) -> UUID:
    generation_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Generation),
            {
                "id": generation_id,
                "competition_id": domain.competition_id,
                "competition_season_id": domain.season_id,
                "kind": "test",
                "status": "pending",
                "request_text": "commit another memory bundle",
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 0,
            },
        )
    return generation_id


def _service(engine: Engine, domain: Domain) -> MemoryMutationService:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {
                "kind": "generation",
                "generation_id": domain.generation_id,
            },
            "scope": {
                "kind": "competition",
                "competition_id": domain.competition_id,
            },
            "correlation_id": uuid4(),
        }
    )
    return MemoryMutationService(
        RevisionManager(create_session_factory(engine), context)
    )


def _generation_context(domain: Domain) -> GenerationMemoryContext:
    return GenerationMemoryContext(
        competition_id=domain.competition_id,
        generation_id=domain.generation_id,
        pinned_revision_id=domain.root_revision_id,
        retrieval=EmptyRetrieval(),
        competition_season_id=domain.season_id,
        week=7,
        knowledge_cutoff_at=datetime(2026, 10, 20, tzinfo=UTC),
    )


def _event(domain: Domain) -> EventContent:
    return EventContent.model_validate(
        {
            "event_type": "matchup",
            "headline": "The Owls upset the Foxes.",
            "summary": "A one-point finish reset the playoff race.",
            "salience": 5,
            "confidence": "inferred",
            "status": "active",
            "details": {
                "kind": "matchup",
                "winner_franchise_id": domain.winner_id,
                "loser_franchise_id": domain.loser_id,
                "sleeper_matchup_id": "week-7-main",
            },
        }
    )


def _fact(domain: Domain, event_version_id: UUID, *, archived: bool = False) -> FactContent:
    return FactContent.model_validate(
        {
            "claim": (
                "The Owls' upset is now archived."
                if archived
                else "The Owls defeated the Foxes by one point."
            ),
            "category": "result",
            "numbers": {"margin": 1},
            "confidence": "inferred",
            "status": "archived" if archived else "active",
            "subjects": [
                {
                    "kind": "franchise",
                    "id": domain.winner_id,
                    "role": "subject",
                    "display_name": "Owls",
                }
            ],
            "originating_event_version_ids": [event_version_id],
        }
    )


def _storyline(
    domain: Domain,
    event_version_id: UUID,
    fact_version_id: UUID,
) -> StorylineContent:
    return StorylineContent.model_validate(
        {
            "headline": "The Owls opened a playoff path",
            "summary": "The upset turned a long shot into a live race.",
            "status": "active",
            "arc_type": "playoff_race",
            "salience": 5,
            "tags": ["playoffs"],
            "subjects": [
                {
                    "kind": "franchise",
                    "id": domain.winner_id,
                    "role": "focus",
                    "display_name": "Owls",
                }
            ],
            "evidence": [
                {"kind": "event", "version_id": event_version_id, "role": "origin"},
                {"kind": "fact", "version_id": fact_version_id, "role": "support"},
            ],
            "related_storylines": [],
            "callback_condition": "Revisit after week 8.",
        }
    )


def _trigger(
    event_item_id: UUID,
    storyline_item_id: UUID,
) -> TriggerContent:
    return TriggerContent.model_validate(
        {
            "trigger_type": "trade_evaluation",
            "status": "open",
            "fire_policy": "until_resolved",
            "target_storyline_item_id": storyline_item_id,
            "origin_event_item_id": event_item_id,
            "target_week": 8,
            "condition": {"kind": "trade_evaluation"},
        }
    )


def _note() -> ContextNoteContent:
    return ContextNoteContent.model_validate(
        {
            "narrative": "The league has entered a volatile playoff race.",
            "outlook": "Treat every week as an elimination game.",
            "status": "active",
            "tags": ["playoffs"],
        }
    )


def _note_identity(domain: Domain) -> ContextNoteIdentity:
    return TypeAdapter(ContextNoteIdentity).validate_python(
        {
            "scope": "competition_season",
            "competition_season_id": domain.season_id,
            "note_key": "playoff_race",
        }
    )


def _complete_bundle(domain: Domain) -> tuple[MemoryMutationBundle, dict[str, UUID]]:
    context = _generation_context(domain)
    event_ref = context.propose_event(_event(domain))
    fact_ref = context.propose_fact(_fact(domain, event_ref.version_id))
    storyline_ref = context.propose_storyline(
        _storyline(domain, event_ref.version_id, fact_ref.version_id)
    )
    trigger_ref = context.propose_trigger(
        _trigger(event_ref.item_id, storyline_ref.item_id)
    )
    note_ref = context.propose_context_note(_note_identity(domain), _note())
    return context.take_completed_bundle(), {
        "event_item": event_ref.item_id,
        "event_version": event_ref.version_id,
        "fact_item": fact_ref.item_id,
        "fact_version": fact_ref.version_id,
        "storyline_item": storyline_ref.item_id,
        "storyline_version": storyline_ref.version_id,
        "trigger_version": trigger_ref.version_id,
        "note_version": note_ref.version_id,
    }


def test_multi_resource_bundle_commits_one_revision_with_local_references(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    bundle, ids = _complete_bundle(domain)
    result = _service(database_engine, domain).apply(bundle)

    assert result.revision is not None
    assert result.revision.sequence_number == 1
    assert result.revision.previous_revision_id == domain.root_revision_id
    assert result.revision.state_content_hash.startswith("sha256-cbor-v1:")
    with create_session_factory(database_engine)() as session:
        current = session.get(CurrentRevision, domain.competition_id)
        assert current is not None
        assert current.current_revision_id == result.revision.revision_id
        assert current.lock_version == 1
        assert session.scalar(
            sa.select(sa.func.count()).select_from(MemoryRevision).where(
                MemoryRevision.competition_id == domain.competition_id
            )
        ) == 2
        assert session.scalar(
            sa.select(sa.func.count()).select_from(MemoryItem).where(
                MemoryItem.competition_id == domain.competition_id
            )
        ) == 5
        assert session.scalar(
            sa.select(sa.func.count()).select_from(MemoryVersion).where(
                MemoryVersion.competition_id == domain.competition_id
            )
        ) == 5
        assert session.scalar(
            sa.select(sa.func.count()).select_from(MemorySearchDocument).where(
                MemorySearchDocument.competition_id == domain.competition_id
            )
        ) == 5
        assert session.get(EventVersion, ids["event_version"]) is not None
        fact = session.get(FactVersion, ids["fact_version"])
        assert fact is not None
        assert fact.originating_event_version_ids == [ids["event_version"]]
        storyline = session.get(StorylineVersion, ids["storyline_version"])
        assert storyline is not None
        assert {entry["version_id"] for entry in storyline.evidence} == {
            str(ids["event_version"]),
            str(ids["fact_version"]),
        }
        assert session.get(TriggerVersion, ids["trigger_version"]) is not None
        assert session.get(ContextNoteVersion, ids["note_version"]) is not None


def test_public_complete_replacement_retires_prior_version(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    bundle, ids = _complete_bundle(domain)
    created = _service(database_engine, domain).apply(bundle)
    assert created.revision is not None
    replacement_generation_id = _add_generation(database_engine, domain)
    origin = MemoryMutationOrigin(
        generation_id=replacement_generation_id,
        expected_revision_id=created.revision.revision_id,
        competition_season_id=domain.season_id,
        week=8,
    )
    replaced = _service(database_engine, domain).replace_fact(
        origin,
        ids["fact_item"],
        1,
        _fact(domain, ids["event_version"], archived=True),
    )
    assert replaced.revision is not None
    assert replaced.revision.sequence_number == 2
    with create_session_factory(database_engine)() as session:
        versions = session.scalars(
            sa.select(MemoryVersion)
            .where(MemoryVersion.item_id == ids["fact_item"])
            .order_by(MemoryVersion.revision_number)
        ).all()
        assert [version.revision_number for version in versions] == [1, 2]
        assert versions[0].retired_revision_id == replaced.revision.revision_id
        assert versions[1].retired_revision_id is None


def test_stale_bundle_and_late_typed_failure_leave_no_partial_state(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    first_bundle, _ = _complete_bundle(domain)
    service = _service(database_engine, domain)
    committed = service.apply(first_bundle)
    assert committed.revision is not None

    stale_generation_id = _add_generation(database_engine, domain)
    stale_context = GenerationMemoryContext(
        competition_id=domain.competition_id,
        generation_id=stale_generation_id,
        pinned_revision_id=domain.root_revision_id,
        retrieval=EmptyRetrieval(),
        competition_season_id=domain.season_id,
        week=8,
    )
    stale_context.propose_context_note(
        TypeAdapter(ContextNoteIdentity).validate_python(
            {"scope": "competition", "note_key": "stale"}
        ),
        _note(),
    )
    with pytest.raises(StaleCanonicalRevisionError):
        service.apply(stale_context.take_completed_bundle())

    failure_generation_id = _add_generation(database_engine, domain)
    current_context = GenerationMemoryContext(
        competition_id=domain.competition_id,
        generation_id=failure_generation_id,
        pinned_revision_id=committed.revision.revision_id,
        retrieval=EmptyRetrieval(),
        competition_season_id=domain.season_id,
        week=8,
    )
    duplicate_identity = TypeAdapter(ContextNoteIdentity).validate_python(
        {"scope": "competition", "note_key": "duplicate"}
    )
    first_ref = current_context.propose_context_note(duplicate_identity, _note())
    second_ref = current_context.propose_context_note(duplicate_identity, _note())
    with pytest.raises(DuplicateContextNoteError):
        service.apply(current_context.take_completed_bundle())

    with create_session_factory(database_engine)() as session:
        current = session.get(CurrentRevision, domain.competition_id)
        assert current is not None
        assert current.current_revision_id == committed.revision.revision_id
        assert current.lock_version == 1
        assert session.get(ContextNoteRow, first_ref.item_id) is None
        assert session.get(ContextNoteRow, second_ref.item_id) is None
        assert session.get(MemoryVersion, first_ref.version_id) is None
        assert session.get(MemoryVersion, second_ref.version_id) is None
        assert session.scalar(
            sa.select(sa.func.count()).select_from(MemoryRevision).where(
                MemoryRevision.competition_id == domain.competition_id
            )
        ) == 2


def test_empty_completed_bundle_creates_no_revision(database_engine: Engine) -> None:
    domain = _seed_domain(database_engine)
    result = _service(database_engine, domain).apply(
        _generation_context(domain).take_completed_bundle()
    )
    assert result.revision is None
    assert result.changes == ()
    with create_session_factory(database_engine)() as session:
        assert session.scalar(
            sa.select(sa.func.count()).select_from(MemoryRevision).where(
                MemoryRevision.competition_id == domain.competition_id
            )
        ) == 1


def test_same_bundle_reference_keeps_its_required_kind(database_engine: Engine) -> None:
    domain = _seed_domain(database_engine)
    context = _generation_context(domain)
    note_ref = context.propose_context_note(_note_identity(domain), _note())
    context.propose_fact(_fact(domain, note_ref.version_id))

    with pytest.raises(WrongTargetKindError):
        _service(database_engine, domain).apply(context.take_completed_bundle())

    with create_session_factory(database_engine)() as session:
        assert session.scalar(
            sa.select(sa.func.count()).select_from(MemoryRevision).where(
                MemoryRevision.competition_id == domain.competition_id
            )
        ) == 1
        assert session.scalar(
            sa.select(sa.func.count()).select_from(MemoryItem).where(
                MemoryItem.competition_id == domain.competition_id
            )
        ) == 0
