from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID

import pytest

from backend.resources.memory.cursors import (
    decode_revision_cursor,
    encode_item_cursor,
    encode_revision_cursor,
)
from backend.resources.memory.errors import (
    InvalidMemoryCursor,
    InvalidMemoryQuery,
    MemoryNotFound,
    MemoryScopeViolation,
)
from backend.resources.memory.manager import MemoryManager
from backend.resources.memory.objects import (
    ExpansionPolicy,
    HydratedMemoryVersion,
    ItemHistory,
    MemoryListQuery,
    MemoryPage,
    MemoryQuery,
    MemoryRevisionRef,
    RevisionPage,
)
from backend.services.memory.service import CandidateMatch, MemoryService


COMPETITION_ID = UUID("00000000-0000-0000-0000-000000000010")
REVISION_ID = UUID("00000000-0000-0000-0000-000000000020")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000030")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000040")


class FakeMemoryManager:
    """Purpose-built boundary fake; it models no ORM or transaction behavior."""

    def __init__(self, revision: MemoryRevisionRef) -> None:
        self.current = revision
        self.revisions = {revision.id: revision}
        self.revision_requests: list[tuple[UUID, UUID | None]] = []
        self.visible_item_requests: list[
            tuple[MemoryRevisionRef, UUID, ExpansionPolicy]
        ] = []
        self.visible_version_requests: list[
            tuple[MemoryRevisionRef, UUID, ExpansionPolicy]
        ] = []
        self.list_item_requests: list[tuple[MemoryRevisionRef, MemoryListQuery]] = []
        self.history_requests: list[tuple[UUID, UUID]] = []
        self.list_revision_requests: list[tuple[UUID, str | None, int]] = []
        self.item_result = cast(HydratedMemoryVersion, object())
        self.version_result = cast(HydratedMemoryVersion, object())
        self.page_result = cast(MemoryPage, object())
        self.history_result = cast(ItemHistory, object())
        self.revisions_result = cast(RevisionPage, object())

    def current_revision(self, competition_id: UUID) -> MemoryRevisionRef:
        assert competition_id == self.current.competition_id
        return self.current

    def get_revision(
        self,
        revision_id: UUID,
        competition_id: UUID | None = None,
    ) -> MemoryRevisionRef:
        self.revision_requests.append((revision_id, competition_id))
        revision = self.revisions.get(revision_id)
        if revision is None:
            raise MemoryNotFound("revision unavailable")
        if (
            competition_id is not None
            and competition_id != revision.competition_id
        ):
            raise MemoryScopeViolation("revision outside competition")
        return revision

    def get_visible_item(
        self,
        revision: MemoryRevisionRef,
        item_id: UUID,
        expansion: ExpansionPolicy,
    ) -> HydratedMemoryVersion:
        self.visible_item_requests.append((revision, item_id, expansion))
        return self.item_result

    def get_visible_version(
        self,
        revision: MemoryRevisionRef,
        version_id: UUID,
        expansion: ExpansionPolicy,
    ) -> HydratedMemoryVersion:
        self.visible_version_requests.append((revision, version_id, expansion))
        return self.version_result

    def list_visible_items(
        self,
        revision: MemoryRevisionRef,
        query: MemoryListQuery,
    ) -> MemoryPage:
        self.list_item_requests.append((revision, query))
        return self.page_result

    def item_history(self, competition_id: UUID, item_id: UUID) -> ItemHistory:
        self.history_requests.append((competition_id, item_id))
        return self.history_result

    def list_revisions(
        self,
        competition_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> RevisionPage:
        self.list_revision_requests.append((competition_id, cursor, limit))
        return self.revisions_result

    def find_candidates(
        self,
        revision: MemoryRevisionRef,
        query: MemoryQuery,
    ) -> Sequence[CandidateMatch]:
        return ()

    def scan_visible_candidates(
        self,
        revision: MemoryRevisionRef,
        query: MemoryQuery,
    ) -> Sequence[CandidateMatch]:
        return ()

    def hydrate_visible_versions(
        self,
        revision: MemoryRevisionRef,
        version_ids: Sequence[UUID],
        expansion: ExpansionPolicy,
    ) -> Mapping[UUID, HydratedMemoryVersion]:
        return {}


def revision_ref() -> MemoryRevisionRef:
    return MemoryRevisionRef(
        id=REVISION_ID,
        competition_id=COMPETITION_ID,
        sequence_number=7,
        state_content_hash="revision-seven",
    )


def test_pinned_reader_keeps_one_resolved_revision_for_every_direct_read() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)

    reader = service.at_revision(REVISION_ID)
    manager.current = MemoryRevisionRef(
        id=UUID("00000000-0000-0000-0000-000000000021"),
        competition_id=COMPETITION_ID,
        sequence_number=8,
        state_content_hash="revision-eight",
    )

    assert reader.revision is revision
    assert reader.get_item(ITEM_ID) is manager.item_result
    assert reader.get_version(VERSION_ID) is manager.version_result
    assert manager.revision_requests == [(REVISION_ID, None)]
    assert manager.visible_item_requests[0][:2] == (revision, ITEM_ID)
    assert manager.visible_version_requests[0][:2] == (revision, VERSION_ID)


def test_pin_current_binds_the_exact_revision_resolved_once() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)

    reader = service.pin_current(COMPETITION_ID)
    manager.current = MemoryRevisionRef(
        id=UUID("00000000-0000-0000-0000-000000000021"),
        competition_id=COMPETITION_ID,
        sequence_number=8,
        state_content_hash="revision-eight",
    )

    assert reader.revision is revision
    assert reader.get_item(ITEM_ID) is manager.item_result
    assert manager.visible_item_requests[0][:2] == (revision, ITEM_ID)
    assert manager.revision_requests == []


def test_inspection_get_item_scopes_an_explicit_revision_to_competition() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)

    result = service.get_item(COMPETITION_ID, ITEM_ID, revision_id=REVISION_ID)

    assert result is manager.item_result
    assert manager.revision_requests == [(REVISION_ID, COMPETITION_ID)]
    assert manager.visible_item_requests[0][:2] == (revision, ITEM_ID)


def test_inspection_get_item_resolves_current_revision_once() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)

    result = service.get_item(COMPETITION_ID, ITEM_ID)

    assert result is manager.item_result
    assert manager.revision_requests == []
    assert manager.visible_item_requests[0][:2] == (revision, ITEM_ID)


def test_list_items_resolves_and_returns_one_revision_scoped_page() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)
    query = MemoryListQuery(competition_id=COMPETITION_ID)

    result = service.list_items(query)

    assert result is manager.page_result
    assert manager.list_item_requests == [(revision, query)]
    assert manager.revision_requests == []


def test_list_items_cursor_keeps_the_first_pages_revision_after_current_moves() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)
    cursor = encode_item_cursor(revision.id, ITEM_ID)
    manager.current = MemoryRevisionRef(
        id=UUID("00000000-0000-0000-0000-000000000021"),
        competition_id=COMPETITION_ID,
        sequence_number=8,
        state_content_hash="revision-eight",
    )

    result = service.list_items(
        MemoryListQuery(competition_id=COMPETITION_ID, cursor=cursor)
    )

    assert result is manager.page_result
    assert manager.revision_requests == [(REVISION_ID, COMPETITION_ID)]
    assert manager.list_item_requests[0][0] is revision


def test_list_items_rejects_cursor_and_explicit_revision_conflict() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)
    cursor = encode_item_cursor(revision.id, ITEM_ID)

    with pytest.raises(InvalidMemoryCursor):
        service.list_items(
            MemoryListQuery(
                competition_id=COMPETITION_ID,
                revision_id=UUID("00000000-0000-0000-0000-000000000021"),
                cursor=cursor,
            )
        )

    assert manager.revision_requests == []


def test_list_items_translates_unavailable_cursor_revision() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)
    unavailable_revision_id = UUID("00000000-0000-0000-0000-000000000099")

    with pytest.raises(InvalidMemoryCursor):
        service.list_items(
            MemoryListQuery(
                competition_id=COMPETITION_ID,
                cursor=encode_item_cursor(unavailable_revision_id, ITEM_ID),
            )
        )


def test_list_items_translates_cross_competition_cursor_revision() -> None:
    revision = revision_ref()
    manager = FakeMemoryManager(revision)
    service = MemoryService(manager)
    other_competition_id = UUID("00000000-0000-0000-0000-000000000011")

    with pytest.raises(InvalidMemoryCursor):
        service.list_items(
            MemoryListQuery(
                competition_id=other_competition_id,
                cursor=encode_item_cursor(revision.id, ITEM_ID),
            )
        )


def test_revision_cursor_requires_a_json_integer_sequence() -> None:
    cursor = encode_revision_cursor(COMPETITION_ID, True)

    with pytest.raises(InvalidMemoryCursor):
        decode_revision_cursor(cursor)


def test_revision_list_limit_uses_a_stable_query_error() -> None:
    manager = MemoryManager(cast(Any, object()))

    with pytest.raises(InvalidMemoryQuery):
        manager.list_revisions(COMPETITION_ID, None, 0)


def test_basic_history_and_revision_inspection_stays_competition_scoped() -> None:
    manager = FakeMemoryManager(revision_ref())
    service = MemoryService(manager)

    history = service.item_history(COMPETITION_ID, ITEM_ID)
    revisions = service.list_revisions(COMPETITION_ID, cursor="next", limit=12)

    assert history is manager.history_result
    assert revisions is manager.revisions_result
    assert manager.history_requests == [(COMPETITION_ID, ITEM_ID)]
    assert manager.list_revision_requests == [(COMPETITION_ID, "next", 12)]
