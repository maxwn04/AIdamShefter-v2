from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.resources.context import CompetitionScope, GlobalScope, ManagerContext
from backend.resources.memory.common import (
    MemoryItemIdentity,
    MemoryVersionMetadata,
    VersionedMemory,
)
from backend.resources.memory.storylines import StorylineContent, StorylineEntityRef


@pytest.mark.parametrize(
    ("actor", "expected_kind"),
    [
        ({"kind": "local_user"}, "local_user"),
        ({"kind": "system_process", "process_name": "worker"}, "system_process"),
        ({"kind": "generation", "generation_id": uuid4()}, "generation"),
    ],
)
def test_manager_context_discriminates_every_actor(
    actor: dict[str, object],
    expected_kind: str,
) -> None:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": actor,
            "scope": {"kind": "competition", "competition_id": uuid4()},
            "correlation_id": uuid4(),
        }
    )

    assert context.actor.kind == expected_kind
    assert context.scope.kind == "competition"


def test_manager_context_discriminates_both_scopes() -> None:
    global_context = ManagerContext[GlobalScope].model_validate(
        {
            "actor": {"kind": "system_process", "process_name": "catalog-refresh"},
            "scope": {"kind": "global", "reason": "player catalog refresh"},
            "correlation_id": uuid4(),
        }
    )
    assert global_context.scope.kind == "global"

    with pytest.raises(ValidationError):
        ManagerContext[CompetitionScope].model_validate(
            {
                "actor": {"kind": "system_process", "process_name": "worker"},
                "scope": {"kind": "global", "reason": "player catalog refresh"},
                "correlation_id": uuid4(),
            }
        )


def test_contract_models_are_frozen_and_reject_unknown_fields() -> None:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "local_user"},
            "scope": {"kind": "competition", "competition_id": uuid4()},
            "correlation_id": uuid4(),
        }
    )

    with pytest.raises(ValidationError, match="frozen"):
        context.correlation_id = uuid4()

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ManagerContext[CompetitionScope].model_validate(
            {
                **context.model_dump(),
                "pinned_revision_id": uuid4(),
            }
        )


@pytest.mark.parametrize(
    ("kind", "reference_id"),
    [
        ("franchise", uuid4()),
        ("player", "player-1"),
        ("season_roster", uuid4()),
        ("season", uuid4()),
        ("sleeper_user", "user-1"),
    ],
)
def test_storyline_entity_reference_discriminator(
    kind: str,
    reference_id: object,
) -> None:
    reference = TypeAdapter(StorylineEntityRef).validate_python(
        {"kind": kind, "id": reference_id, "role": "focus"}
    )

    assert reference.kind == kind


def test_versioned_memory_enforces_kind_and_schema_version() -> None:
    content = StorylineContent(
        headline="A rivalry resumes",
        summary="The league's longest-running rivalry has another chapter.",
        status="active",
        salience=4,
        tags=[],
        subjects=[],
        evidence=[],
        related_storylines=[],
    )
    item = MemoryItemIdentity(
        item_id=uuid4(),
        competition_id=uuid4(),
        kind="storyline",
        created_at=datetime.now(UTC),
    )
    version = MemoryVersionMetadata(
        version_id=uuid4(),
        revision_number=1,
        content_schema_version=1,
        introduced_revision_id=uuid4(),
        creating_generation_id=uuid4(),
        recorded_at=datetime.now(UTC),
    )

    resource = VersionedMemory[StorylineContent](
        item=item,
        version=version,
        content=content,
    )
    assert resource.content.schema_version == 1

    with pytest.raises(ValidationError, match="item kind"):
        VersionedMemory[StorylineContent](
            item=item.model_copy(update={"kind": "fact"}),
            version=version,
            content=content,
        )

    with pytest.raises(ValidationError, match="content schema version"):
        VersionedMemory[StorylineContent](
            item=item,
            version=version.model_copy(update={"content_schema_version": 2}),
            content=content,
        )
