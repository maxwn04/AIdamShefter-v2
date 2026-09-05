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
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
    TriggerVersion,
)
from backend.database.models.reporting import Generation
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import (
    CrossCompetitionEntityReferenceError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.revisions.writers import persist_version_envelopes
from backend.resources.memory.search_documents import TRIGGER_DOCUMENT_BUILDER_VERSION
from backend.resources.memory.triggers import TriggerContent, TriggerManager
from backend.resources.memory.triggers.shared import (
    insert_trigger_version,
    prepare_trigger_replacement,
    prepare_trigger_write,
)
from backend.tests.database.conftest import database_engine, migrated_database


@dataclass(frozen=True)
class TriggerDomain:
    competition_id: UUID
    other_competition_id: UUID
    season_id: UUID
    generation_id: UUID
    current_revision_id: UUID
    franchise_ids: tuple[UUID, UUID]
    cross_franchise_id: UUID
    storyline_item_id: UUID
    event_item_id: UUID
    cross_trigger_version_id: UUID


def _seed_domain(database_engine: Engine) -> TriggerDomain:
    competition_id = uuid4()
    other_competition_id = uuid4()
    season_id = uuid4()
    other_season_id = uuid4()
    generation_id = uuid4()
    other_generation_id = uuid4()
    root_revision_id = uuid4()
    current_revision_id = uuid4()
    other_revision_id = uuid4()
    franchise_ids = (uuid4(), uuid4())
    cross_franchise_id = uuid4()
    storyline_item_id = uuid4()
    event_item_id = uuid4()
    cross_event_item_id = uuid4()
    cross_trigger_item_id = uuid4()
    cross_trigger_version_id = uuid4()

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            [
                {"id": competition_id, "display_name": "Trigger League"},
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
                _franchise(franchise_ids[0], competition_id, "Owls"),
                _franchise(franchise_ids[1], competition_id, "Sharks"),
                _franchise(cross_franchise_id, other_competition_id, "Foxes"),
            ],
        )
        connection.execute(
            sa.insert(Generation),
            [
                _generation(generation_id, competition_id, season_id),
                _generation(
                    other_generation_id,
                    other_competition_id,
                    other_season_id,
                ),
            ],
        )
        connection.execute(
            sa.insert(MemoryRevision),
            [
                _revision(root_revision_id, competition_id, 0, season_id),
                _revision(
                    current_revision_id,
                    competition_id,
                    1,
                    season_id,
                    previous_revision_id=root_revision_id,
                ),
                _revision(
                    other_revision_id,
                    other_competition_id,
                    0,
                    other_season_id,
                ),
            ],
        )
        connection.execute(
            sa.insert(CurrentRevision),
            [
                {
                    "competition_id": competition_id,
                    "current_revision_id": current_revision_id,
                    "lock_version": 1,
                },
                {
                    "competition_id": other_competition_id,
                    "current_revision_id": other_revision_id,
                    "lock_version": 0,
                },
            ],
        )
        connection.execute(
            sa.insert(MemoryItem),
            [
                _item(storyline_item_id, competition_id, "storyline"),
                _item(event_item_id, competition_id, "event"),
                _item(cross_event_item_id, other_competition_id, "event"),
                _item(cross_trigger_item_id, other_competition_id, "trigger"),
            ],
        )
        connection.execute(
            sa.insert(MemoryVersion),
            _version(
                cross_trigger_version_id,
                cross_trigger_item_id,
                other_competition_id,
                other_revision_id,
                other_season_id,
                other_generation_id,
            ),
        )
        connection.execute(
            sa.insert(TriggerVersion),
            {
                "version_id": cross_trigger_version_id,
                "competition_id": other_competition_id,
                "trigger_type": "trade_evaluation",
                "status": "open",
                "fire_policy": "one_shot",
                "origin_event_item_id": cross_event_item_id,
                "target_week": 4,
                "condition": {"kind": "trade_evaluation"},
            },
        )

    return TriggerDomain(
        competition_id=competition_id,
        other_competition_id=other_competition_id,
        season_id=season_id,
        generation_id=generation_id,
        current_revision_id=current_revision_id,
        franchise_ids=franchise_ids,
        cross_franchise_id=cross_franchise_id,
        storyline_item_id=storyline_item_id,
        event_item_id=event_item_id,
        cross_trigger_version_id=cross_trigger_version_id,
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
        "request_text": "seed trigger manager",
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


def _item(item_id: UUID, competition_id: UUID, kind: str) -> dict[str, object]:
    return {"id": item_id, "competition_id": competition_id, "kind": kind}


def _version(
    version_id: UUID,
    item_id: UUID,
    competition_id: UUID,
    revision_id: UUID,
    season_id: UUID,
    generation_id: UUID,
) -> dict[str, object]:
    return {
        "id": version_id,
        "item_id": item_id,
        "competition_id": competition_id,
        "revision_number": 1,
        "content_schema_version": 1,
        "introduced_revision_id": revision_id,
        "competition_season_id": season_id,
        "week": 1,
        "creating_generation_id": generation_id,
    }


def _scheduled_review(domain: TriggerDomain, *, resolved: bool = False) -> TriggerContent:
    return TriggerContent.model_validate({
        "trigger_type": "scheduled_review", "status": "satisfied" if resolved else "open",
        "fire_policy": "one_shot", "target_storyline_item_id": domain.storyline_item_id,
        "target_competition_season_id": domain.season_id, "target_week": 5,
        "condition": {"kind": "scheduled_review", "review_question": "Does the lineup edge persist?"},
        "resolution_reason": "Reviewed; no material development." if resolved else None,
    })


def _manager(database_engine: Engine, competition_id: UUID) -> TriggerManager:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "local_user"},
            "scope": {"kind": "competition", "competition_id": competition_id},
            "correlation_id": uuid4(),
        }
    )
    return TriggerManager(create_session_factory(database_engine), context)


def test_trigger_lifecycle_hydrates_history_and_projects_replacements(
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
        revision = MemoryRevision(
            **_revision(
                first_revision_id,
                domain.competition_id,
                2,
                domain.season_id,
                previous_revision_id=domain.current_revision_id,
            )
        )
        item = MemoryItem(
            id=item_id,
            competition_id=domain.competition_id,
            kind="trigger",
        )
        version = MemoryVersion(
            **_version(
                first_version_id,
                item_id,
                domain.competition_id,
                first_revision_id,
                domain.season_id,
                domain.generation_id,
            )
        )
        persist_version_envelopes(
            session,
            revision,
            new_items=(item,),
            new_versions=(version,),
        )
        insert_trigger_version(
            session,
            version,
            prepare_trigger_write(
                session,
                domain.competition_id,
                _scheduled_review(domain),
            ),
        )
        session.execute(
            sa.update(CurrentRevision)
            .where(CurrentRevision.competition_id == domain.competition_id)
            .values(current_revision_id=first_revision_id, lock_version=2)
        )

    with session_factory.begin() as session:
        replacement = prepare_trigger_replacement(
            session,
            domain.competition_id,
            item_id,
            1,
            _scheduled_review(domain, resolved=True),
        )
        revision = MemoryRevision(
            **_revision(
                second_revision_id,
                domain.competition_id,
                3,
                domain.season_id,
                previous_revision_id=first_revision_id,
            )
        )
        version_data = _version(
            second_version_id,
            item_id,
            domain.competition_id,
            second_revision_id,
            domain.season_id,
            domain.generation_id,
        )
        version_data["revision_number"] = replacement.next_revision_number
        version = MemoryVersion(**version_data)
        persist_version_envelopes(
            session,
            revision,
            new_items=(),
            new_versions=(version,),
            retired_versions=(replacement.previous_version,),
        )
        insert_trigger_version(session, version, replacement.validated)

    manager = _manager(database_engine, domain.competition_id)
    historical = manager.exact(first_version_id)
    current, previous = manager.history(item_id)

    assert historical.version.retired_revision_id == second_revision_id
    assert current.version.version_id == second_version_id
    assert previous.version.version_id == first_version_id
    assert current.content.status == "satisfied"
    assert current.content.target_week == 5

    with session_factory() as session:
        projections = session.scalars(
            sa.select(MemorySearchDocument).where(
                MemorySearchDocument.item_id == item_id
            )
        ).all()
    assert len(projections) == 2
    assert {projection.builder_version for projection in projections} == {
        TRIGGER_DOCUMENT_BUILDER_VERSION
    }

    with pytest.raises(TargetNotFoundError):
        manager.exact(domain.cross_trigger_version_id)


def test_trigger_reference_validation_enforces_kind_and_scope(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    rematch = TriggerContent.model_validate(
        {
            "trigger_type": "rematch",
            "status": "open",
            "fire_policy": "one_shot",
            "target_competition_season_id": domain.season_id,
            "target_week": 8,
            "condition": {
                "kind": "rematch",
                "franchise_ids": domain.franchise_ids,
            },
        }
    )

    with session_factory() as session:
        prepare_trigger_write(session, domain.competition_id, rematch)
        with pytest.raises(WrongTargetKindError):
            prepare_trigger_write(
                session,
                domain.competition_id,
                _scheduled_review(domain).model_copy(
                    update={"target_storyline_item_id": domain.event_item_id}
                ),
            )
        with pytest.raises(CrossCompetitionEntityReferenceError):
            prepare_trigger_write(
                session,
                domain.competition_id,
                rematch.model_copy(
                    update={
                        "condition": rematch.condition.model_copy(
                            update={
                                "franchise_ids": (
                                    domain.franchise_ids[0],
                                    domain.cross_franchise_id,
                                )
                            }
                        )
                    }
                ),
            )


def test_trigger_write_rolls_back_typed_content_and_projection(
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
                    2,
                    domain.season_id,
                    previous_revision_id=domain.current_revision_id,
                )
            )
            item = MemoryItem(
                id=item_id,
                competition_id=domain.competition_id,
                kind="trigger",
            )
            version = MemoryVersion(
                **_version(
                    version_id,
                    item_id,
                    domain.competition_id,
                    revision_id,
                    domain.season_id,
                    domain.generation_id,
                )
            )
            persist_version_envelopes(
                session,
                revision,
                new_items=(item,),
                new_versions=(version,),
            )
            insert_trigger_version(
                session,
                version,
                prepare_trigger_write(
                    session,
                    domain.competition_id,
                    _scheduled_review(domain),
                ),
            )
            session.flush()
            raise RuntimeError("abort canonical write")

    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(TriggerVersion)
            .where(TriggerVersion.version_id == version_id)
        ) == 0
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(MemorySearchDocument)
            .where(MemorySearchDocument.version_id == version_id)
        ) == 0
