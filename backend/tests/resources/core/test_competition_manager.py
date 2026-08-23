from uuid import uuid4

import pytest

from backend.resources.core import (
    ArchiveCompetition,
    CompetitionArchivedConflict,
    CompetitionManager,
    CompetitionQuery,
    CoreResourceNotFound,
    CreateCompetition,
    RenameCompetition,
)


def test_create_get_and_paginated_list_are_stable_and_normalized(
    competition_manager: CompetitionManager,
) -> None:
    zulu = competition_manager.create(CreateCompetition(display_name="Zulu"))
    alpha = competition_manager.create(CreateCompetition(display_name=" alpha "))
    bravo = competition_manager.create(CreateCompetition(display_name="Bravo"))

    first_page = competition_manager.list(CompetitionQuery(limit=2))
    second_page = competition_manager.list(CompetitionQuery(limit=2, offset=2))

    assert first_page.total == 3
    assert [item.id for item in first_page.items] == [alpha.id, bravo.id]
    assert [item.id for item in second_page.items] == [zulu.id]
    assert competition_manager.get(alpha.id) == alpha
    assert alpha.display_name == "alpha"
    assert alpha.created_at.tzinfo is not None
    assert alpha.updated_at.tzinfo is not None


def test_rename_is_idempotent_and_archive_is_one_way_and_retry_safe(
    competition_manager: CompetitionManager,
) -> None:
    created = competition_manager.create(CreateCompetition(display_name="Original"))

    unchanged = competition_manager.rename(
        RenameCompetition(
            competition_id=created.id,
            display_name="Original",
        )
    )
    renamed = competition_manager.rename(
        RenameCompetition(
            competition_id=created.id,
            display_name=" Renamed ",
        )
    )
    archived = competition_manager.archive(
        ArchiveCompetition(competition_id=created.id)
    )
    archived_again = competition_manager.archive(
        ArchiveCompetition(competition_id=created.id)
    )

    assert unchanged.updated_at == created.updated_at
    assert renamed.display_name == "Renamed"
    assert archived.archived_at is not None
    assert archived.updated_at == archived.archived_at
    assert archived_again == archived
    assert competition_manager.get(created.id) == archived
    assert competition_manager.list(CompetitionQuery()).items == ()
    assert competition_manager.list(
        CompetitionQuery(include_archived=True)
    ).items == (archived,)
    with pytest.raises(CompetitionArchivedConflict):
        competition_manager.rename(
            RenameCompetition(
                competition_id=created.id,
                display_name="Cannot Change",
            )
        )


def test_competition_reads_and_mutations_return_typed_not_found(
    competition_manager: CompetitionManager,
) -> None:
    missing_id = uuid4()

    with pytest.raises(CoreResourceNotFound, match="competition"):
        competition_manager.get(missing_id)
    with pytest.raises(CoreResourceNotFound, match="competition"):
        competition_manager.rename(
            RenameCompetition(
                competition_id=missing_id,
                display_name="Missing",
            )
        )
    with pytest.raises(CoreResourceNotFound, match="competition"):
        competition_manager.archive(ArchiveCompetition(competition_id=missing_id))
