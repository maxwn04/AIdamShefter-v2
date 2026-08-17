from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from pydantic import TypeAdapter
from sqlalchemy.engine import Engine

from backend.database.models.core import Competition, CompetitionSeason, Franchise
from backend.database.models.memory import (
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
)
from backend.database.models.memory.context_notes import (
    ContextNote as ContextNoteRow,
)
from backend.database.models.memory.context_notes import (
    ContextNoteVersion,
)
from backend.database.models.reporting import Generation
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import (
    CrossCompetitionEntityReferenceError,
    EntityReferenceNotFoundError,
    TargetNotFoundError,
)
from backend.resources.memory.context_notes import (
    ContextNoteContent,
    ContextNoteIdentity,
    ContextNoteManager,
    ContextNoteStatus,
)
from backend.resources.memory.context_notes.shared import (
    insert_context_note_identity,
    insert_context_note_version,
    prepare_context_note_replacement,
    prepare_context_note_write,
)
from backend.resources.memory.revisions.writers import persist_version_envelopes
from backend.resources.memory.search_documents import (
    CONTEXT_NOTE_DOCUMENT_BUILDER_VERSION,
)
from backend.tests.database.conftest import database_engine, migrated_database


@dataclass(frozen=True)
class ContextNoteDomain:
    competition_id: UUID
    other_competition_id: UUID
    season_id: UUID
    other_season_id: UUID
    franchise_id: UUID
    other_franchise_id: UUID
    generation_id: UUID
    root_revision_id: UUID


def _seed_domain(database_engine: Engine) -> ContextNoteDomain:
    competition_id = uuid4()
    other_competition_id = uuid4()
    season_id = uuid4()
    other_season_id = uuid4()
    franchise_id = uuid4()
    other_franchise_id = uuid4()
    generation_id = uuid4()
    root_revision_id = uuid4()

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            [
                {"id": competition_id, "display_name": "Context League"},
                {"id": other_competition_id, "display_name": "Other League"},
            ],
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            [
                _season(season_id, competition_id),
                _season(other_season_id, other_competition_id),
            ],
        )
        connection.execute(
            sa.insert(Franchise),
            [
                _franchise(franchise_id, competition_id, "Owls"),
                _franchise(other_franchise_id, other_competition_id, "Foxes"),
            ],
        )
        connection.execute(
            sa.insert(Generation),
            _generation(generation_id, competition_id, season_id),
        )
        connection.execute(
            sa.insert(MemoryRevision),
            _revision(root_revision_id, competition_id, 0, season_id),
        )

    return ContextNoteDomain(
        competition_id=competition_id,
        other_competition_id=other_competition_id,
        season_id=season_id,
        other_season_id=other_season_id,
        franchise_id=franchise_id,
        other_franchise_id=other_franchise_id,
        generation_id=generation_id,
        root_revision_id=root_revision_id,
    )


def _season(season_id: UUID, competition_id: UUID) -> dict[str, object]:
    return {
        "id": season_id,
        "competition_id": competition_id,
        "season_year": 2026,
        "sequence_number": 1,
        "sleeper_league_id": f"league-{season_id}",
    }


def _franchise(
    franchise_id: UUID,
    competition_id: UUID,
    display_name: str,
) -> dict[str, object]:
    return {
        "id": franchise_id,
        "competition_id": competition_id,
        "display_name": display_name,
    }


def _generation(
    generation_id: UUID,
    competition_id: UUID,
    season_id: UUID,
) -> dict[str, object]:
    return {
        "id": generation_id,
        "competition_id": competition_id,
        "competition_season_id": season_id,
        "kind": "test",
        "status": "pending",
        "request_text": "seed context-note manager",
        "requested_primary_model": "test-model",
        "settings_jsonb": {},
        "current_turn": 0,
    }


def _revision(
    revision_id: UUID,
    competition_id: UUID,
    sequence_number: int,
    season_id: UUID,
    *,
    previous_revision_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "id": revision_id,
        "competition_id": competition_id,
        "sequence_number": sequence_number,
        "previous_revision_id": previous_revision_id,
        "competition_season_id": season_id,
        "week": sequence_number,
        "state_content_hash": f"seed-{revision_id}",
    }


def _version(
    version_id: UUID,
    item_id: UUID,
    domain: ContextNoteDomain,
    revision_id: UUID,
    revision_number: int = 1,
) -> dict[str, object]:
    return {
        "id": version_id,
        "item_id": item_id,
        "competition_id": domain.competition_id,
        "revision_number": revision_number,
        "content_schema_version": 1,
        "introduced_revision_id": revision_id,
        "competition_season_id": domain.season_id,
        "week": 1,
        "creating_generation_id": domain.generation_id,
    }


def _identity(payload: dict[str, object]) -> ContextNoteIdentity:
    return TypeAdapter(ContextNoteIdentity).validate_python(payload)


def _content(*, archived: bool = False) -> ContextNoteContent:
    return ContextNoteContent(
        narrative=(
            "The roster now needs a reset."
            if archived
            else "The young roster is ahead of schedule."
        ),
        outlook="Build around the current core.",
        status=(ContextNoteStatus.ARCHIVED if archived else ContextNoteStatus.ACTIVE),
        tags=["team-identity", "youth"],
    )


def _manager(database_engine: Engine, competition_id: UUID) -> ContextNoteManager:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "local_user"},
            "scope": {"kind": "competition", "competition_id": competition_id},
            "correlation_id": uuid4(),
        }
    )
    return ContextNoteManager(create_session_factory(database_engine), context)


def test_context_note_lifecycle_hydrates_stable_identity_and_history(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    first_revision_id = uuid4()
    second_revision_id = uuid4()
    identities = (
        _identity({"scope": "competition", "note_key": "league_voice"}),
        _identity(
            {
                "scope": "competition_season",
                "competition_season_id": domain.season_id,
                "note_key": "playoff_race",
            }
        ),
        _identity(
            {
                "scope": "franchise",
                "franchise_id": domain.franchise_id,
                "note_key": "team_identity",
            }
        ),
    )
    item_ids = tuple(uuid4() for _ in identities)
    version_ids = tuple(uuid4() for _ in identities)

    with session_factory.begin() as session:
        revision = MemoryRevision(
            **_revision(
                first_revision_id,
                domain.competition_id,
                1,
                domain.season_id,
                previous_revision_id=domain.root_revision_id,
            )
        )
        items = tuple(
            MemoryItem(
                id=item_id,
                competition_id=domain.competition_id,
                kind="context_note",
            )
            for item_id in item_ids
        )
        versions = tuple(
            MemoryVersion(**_version(version_id, item_id, domain, first_revision_id))
            for item_id, version_id in zip(item_ids, version_ids, strict=True)
        )
        persist_version_envelopes(
            session,
            revision,
            new_items=items,
            new_versions=versions,
        )
        for item, version, identity in zip(
            items,
            versions,
            identities,
            strict=True,
        ):
            prepared = prepare_context_note_write(
                session,
                domain.competition_id,
                identity,
                _content(),
            )
            insert_context_note_identity(session, item, prepared)
            insert_context_note_version(session, version, prepared)

    replacement_version_id = uuid4()
    with session_factory.begin() as session:
        replacement = prepare_context_note_replacement(
            session,
            domain.competition_id,
            item_ids[2],
            1,
            _content(archived=True),
        )
        revision = MemoryRevision(
            **_revision(
                second_revision_id,
                domain.competition_id,
                2,
                domain.season_id,
                previous_revision_id=first_revision_id,
            )
        )
        version = MemoryVersion(
            **_version(
                replacement_version_id,
                item_ids[2],
                domain,
                second_revision_id,
                replacement.next_revision_number,
            )
        )
        persist_version_envelopes(
            session,
            revision,
            new_items=(),
            new_versions=(version,),
            retired_versions=(replacement.previous_version,),
        )
        insert_context_note_version(session, version, replacement.validated)

    manager = _manager(database_engine, domain.competition_id)
    assert manager.exact(version_ids[0]).note_identity == identities[0]
    assert manager.exact(version_ids[1]).note_identity == identities[1]
    current, previous = manager.history(item_ids[2])
    assert current.note_identity == previous.note_identity == identities[2]
    assert current.content.status == "archived"
    assert previous.version.retired_revision_id == second_revision_id

    with session_factory() as session:
        projections = session.scalars(
            sa.select(MemorySearchDocument).where(
                MemorySearchDocument.item_id.in_(item_ids)
            )
        ).all()
    assert len(projections) == 4
    assert {projection.builder_version for projection in projections} == {
        CONTEXT_NOTE_DOCUMENT_BUILDER_VERSION
    }
    assert {
        tuple(projection.entity_keys)
        for projection in projections
        if projection.item_id == item_ids[2]
    } == {(f"franchise:{domain.franchise_id}",)}
    with pytest.raises(TargetNotFoundError):
        _manager(database_engine, domain.other_competition_id).exact(version_ids[0])


def test_context_note_scope_validation_covers_all_identity_variants(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)

    with session_factory() as session:
        for identity in (
            _identity({"scope": "competition", "note_key": "league_voice"}),
            _identity(
                {
                    "scope": "competition_season",
                    "competition_season_id": domain.season_id,
                    "note_key": "playoff_race",
                }
            ),
            _identity(
                {
                    "scope": "franchise",
                    "franchise_id": domain.franchise_id,
                    "note_key": "outlook",
                }
            ),
        ):
            prepare_context_note_write(
                session,
                domain.competition_id,
                identity,
                _content(),
            )

        with pytest.raises(EntityReferenceNotFoundError):
            prepare_context_note_write(
                session,
                domain.competition_id,
                _identity(
                    {
                        "scope": "competition_season",
                        "competition_season_id": uuid4(),
                        "note_key": "missing",
                    }
                ),
                _content(),
            )
        with pytest.raises(CrossCompetitionEntityReferenceError):
            prepare_context_note_write(
                session,
                domain.competition_id,
                _identity(
                    {
                        "scope": "franchise",
                        "franchise_id": domain.other_franchise_id,
                        "note_key": "cross-scope",
                    }
                ),
                _content(),
            )


def test_context_note_write_rolls_back_identity_content_and_projection(
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
                **_revision(
                    revision_id,
                    domain.competition_id,
                    1,
                    domain.season_id,
                    previous_revision_id=domain.root_revision_id,
                )
            )
            item = MemoryItem(
                id=item_id,
                competition_id=domain.competition_id,
                kind="context_note",
            )
            version = MemoryVersion(
                **_version(version_id, item_id, domain, revision_id)
            )
            persist_version_envelopes(
                session,
                revision,
                new_items=(item,),
                new_versions=(version,),
            )
            prepared = prepare_context_note_write(
                session,
                domain.competition_id,
                _identity(
                    {
                        "scope": "franchise",
                        "franchise_id": domain.franchise_id,
                        "note_key": "team_identity",
                    }
                ),
                _content(),
            )
            insert_context_note_identity(session, item, prepared)
            insert_context_note_version(session, version, prepared)
            session.flush()
            raise RuntimeError("abort canonical write")

    with database_engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(ContextNoteRow)
                .where(ContextNoteRow.item_id == item_id)
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(ContextNoteVersion)
                .where(ContextNoteVersion.version_id == version_id)
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count())
                .select_from(MemorySearchDocument)
                .where(MemorySearchDocument.version_id == version_id)
            )
            == 0
        )
