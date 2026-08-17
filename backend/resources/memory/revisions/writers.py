"""Package-internal concurrency primitives for canonical revision writes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.memory import (
    CurrentRevision,
    MemoryItem,
    MemoryRevision,
    MemoryVersion,
)
from backend.resources.memory.common.errors import (
    CrossCompetitionReferenceError,
    MemoryIdentityConflictError,
    RevisionNotFoundError,
    StaleItemVersionError,
    StaleCanonicalRevisionError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes.objects import ContextNoteIdentity
from backend.resources.memory.revisions.hashing import (
    StateHashItem,
    StoredSchemaContent,
)


@dataclass(frozen=True, slots=True)
class LockedRevisionParent:
    current_revision_id: UUID
    next_sequence_number: int
    next_lock_version: int


@dataclass(frozen=True, slots=True)
class CanonicalReferenceTarget:
    reference_id: UUID
    target: Literal["item", "version"]
    expected_kinds: tuple[MemoryKind, ...]


@dataclass(frozen=True, slots=True)
class CanonicalResourceWrite:
    """Opaque resource-local write accepted by revision orchestration."""

    operation: Literal["create", "replace"]
    kind: MemoryKind
    dependency_order: int
    item_id: UUID
    version_id: UUID
    expected_item_revision: int | None
    content_schema_version: int
    agent_key: str | None
    competition_season_id: UUID | None
    week: int | None
    occurred_at: datetime | None
    creating_tool_call_id: UUID | None
    change_reason: str | None
    stored_content: StoredSchemaContent
    context_note_identity: ContextNoteIdentity | None
    references: tuple[CanonicalReferenceTarget, ...]
    persist_typed: Callable[[Session, MemoryItem, MemoryVersion], None]


@dataclass(frozen=True, slots=True)
class CanonicalWriteBundle:
    competition_id: UUID
    generation_id: UUID
    expected_revision_id: UUID
    competition_season_id: UUID | None
    week: int | None
    knowledge_cutoff_at: datetime | None
    writes: tuple[CanonicalResourceWrite, ...]


StateReader = Callable[[Session, UUID], tuple[StateHashItem, ...]]


def persist_version_envelopes(
    session: Session,
    revision: MemoryRevision,
    *,
    new_items: Iterable[MemoryItem],
    new_versions: Iterable[MemoryVersion],
    retired_versions: Iterable[MemoryVersion] = (),
) -> None:
    """Persist generic revision state in dependency order inside one transaction.

    The ORM intentionally has no relationship graph, so SQLAlchemy cannot infer
    the foreign-key order among pending revision, item, and version objects.
    Canonical write orchestration uses this package-internal operation before
    invoking typed resource writers; callers never coordinate these flush
    stages themselves.
    """

    items = tuple(new_items)
    versions = tuple(new_versions)
    retired = tuple(retired_versions)

    session.add(revision)
    session.flush((revision,))

    if retired:
        for previous in retired:
            previous.retired_revision_id = revision.id
        session.flush(retired)

    if items:
        session.add_all(items)
        session.flush(items)

    if versions:
        session.add_all(versions)
        session.flush(versions)


def lock_current_revision(
    session: Session,
    competition_id: UUID,
    expected_revision_id: UUID,
) -> LockedRevisionParent:
    """Lock and validate the parent of a future canonical revision.

    The caller must already own the surrounding transaction. This helper is not
    a public application API; the completed revision manager write operation
    will enclose it with version, projection, and pointer writes atomically.
    """

    statement = (
        sa.select(
            CurrentRevision.current_revision_id,
            CurrentRevision.lock_version,
            MemoryRevision.sequence_number,
        )
        .join(
            MemoryRevision,
            sa.and_(
                MemoryRevision.id == CurrentRevision.current_revision_id,
                MemoryRevision.competition_id == CurrentRevision.competition_id,
            ),
        )
        .where(CurrentRevision.competition_id == competition_id)
        .with_for_update(of=CurrentRevision)
    )
    row = session.execute(statement).one_or_none()
    if row is None:
        raise RevisionNotFoundError(competition_id)
    current_revision_id = cast(UUID, row.current_revision_id)
    lock_version = cast(int, row.lock_version)
    sequence_number = cast(int, row.sequence_number)
    if current_revision_id != expected_revision_id:
        raise StaleCanonicalRevisionError(
            competition_id,
            expected_revision_id,
            current_revision_id,
        )
    return LockedRevisionParent(
        current_revision_id=current_revision_id,
        next_sequence_number=sequence_number + 1,
        next_lock_version=lock_version + 1,
    )


def validate_reference_targets(
    session: Session,
    competition_id: UUID,
    writes: tuple[CanonicalResourceWrite, ...],
) -> None:
    """Batch-load stable and exact targets, including proposal-local identities."""

    local_items = {
        write.item_id: write.kind
        for write in writes
        if write.operation == "create"
    }
    local_versions = {write.version_id: write.kind for write in writes}
    requirements = tuple(
        reference for write in writes for reference in write.references
    )
    item_ids = {
        reference.reference_id
        for reference in requirements
        if reference.target == "item" and reference.reference_id not in local_items
    }
    version_ids = {
        reference.reference_id
        for reference in requirements
        if reference.target == "version"
        and reference.reference_id not in local_versions
    }
    item_rows = session.execute(
        sa.select(MemoryItem.id, MemoryItem.competition_id, MemoryItem.kind).where(
            MemoryItem.id.in_(item_ids)
        )
    ) if item_ids else ()
    found_items = {
        item_id: (scope, MemoryKind(kind)) for item_id, scope, kind in item_rows
    }
    version_rows = session.execute(
        sa.select(
            MemoryVersion.id,
            MemoryVersion.competition_id,
            MemoryItem.kind,
        )
        .join(MemoryItem, MemoryItem.id == MemoryVersion.item_id)
        .where(MemoryVersion.id.in_(version_ids))
    ) if version_ids else ()
    found_versions = {
        version_id: (scope, MemoryKind(kind))
        for version_id, scope, kind in version_rows
    }

    for reference in requirements:
        local = (
            local_items.get(reference.reference_id)
            if reference.target == "item"
            else local_versions.get(reference.reference_id)
        )
        if local is not None:
            if local not in reference.expected_kinds:
                raise WrongTargetKindError(
                    reference.reference_id,
                    reference.expected_kinds,
                    local,
                )
            continue
        found = (
            found_items.get(reference.reference_id)
            if reference.target == "item"
            else found_versions.get(reference.reference_id)
        )
        if found is None:
            raise TargetNotFoundError(
                reference.reference_id,
                reference.expected_kinds,
            )
        actual_scope, actual_kind = found
        if actual_scope != competition_id:
            raise CrossCompetitionReferenceError(
                reference.reference_id,
                competition_id,
                actual_scope,
            )
        if actual_kind not in reference.expected_kinds:
            raise WrongTargetKindError(
                reference.reference_id,
                reference.expected_kinds,
                actual_kind,
            )


def build_version_envelopes(
    session: Session,
    revision: MemoryRevision,
    bundle: CanonicalWriteBundle,
) -> tuple[
    tuple[tuple[CanonicalResourceWrite, MemoryItem, MemoryVersion], ...],
    tuple[MemoryVersion, ...],
]:
    """Batch-resolve replacements and construct every generic envelope."""

    replacement_writes = tuple(
        write for write in bundle.writes if write.operation == "replace"
    )
    replacement_ids = {write.item_id for write in replacement_writes}
    item_rows = session.scalars(
        sa.select(MemoryItem).where(MemoryItem.id.in_(replacement_ids))
    ).all() if replacement_ids else []
    existing_items = {item.id: item for item in item_rows}
    current_rows = session.scalars(
        sa.select(MemoryVersion).where(
            MemoryVersion.item_id.in_(replacement_ids),
            MemoryVersion.retired_revision_id.is_(None),
        )
    ).all() if replacement_ids else []
    current_versions = {version.item_id: version for version in current_rows}

    create_ids = {
        write.item_id for write in bundle.writes if write.operation == "create"
    }
    conflicting_id = session.scalar(
        sa.select(MemoryItem.id).where(MemoryItem.id.in_(create_ids)).limit(1)
    ) if create_ids else None
    if conflicting_id is not None:
        raise MemoryIdentityConflictError(conflicting_id)
    version_ids = {write.version_id for write in bundle.writes}
    conflicting_version_id = session.scalar(
        sa.select(MemoryVersion.id).where(MemoryVersion.id.in_(version_ids)).limit(1)
    ) if version_ids else None
    if conflicting_version_id is not None:
        raise MemoryIdentityConflictError(conflicting_version_id)

    resolved: list[tuple[CanonicalResourceWrite, MemoryItem, MemoryVersion]] = []
    retired: list[MemoryVersion] = []
    for write in bundle.writes:
        if write.operation == "create":
            item = MemoryItem(
                id=write.item_id,
                competition_id=bundle.competition_id,
                kind=write.kind.value,
                agent_key=write.agent_key,
            )
            revision_number = 1
        else:
            item = existing_items.get(write.item_id)
            if item is None:
                raise TargetNotFoundError(write.item_id, (write.kind,))
            if item.competition_id != bundle.competition_id:
                raise CrossCompetitionReferenceError(
                    write.item_id,
                    bundle.competition_id,
                    item.competition_id,
                )
            if item.kind != write.kind.value:
                raise WrongTargetKindError(
                    write.item_id,
                    (write.kind,),
                    MemoryKind(item.kind),
                )
            previous = current_versions.get(write.item_id)
            if previous is None:
                raise TargetNotFoundError(write.item_id, (write.kind,))
            expected = write.expected_item_revision
            if expected is None:
                raise ValueError("replacement write is missing its expected revision")
            if previous.revision_number != expected:
                raise StaleItemVersionError(
                    write.item_id,
                    expected,
                    previous.revision_number,
                )
            revision_number = previous.revision_number + 1
            retired.append(previous)

        version = MemoryVersion(
            id=write.version_id,
            item_id=write.item_id,
            competition_id=bundle.competition_id,
            revision_number=revision_number,
            content_schema_version=write.content_schema_version,
            introduced_revision_id=revision.id,
            competition_season_id=(
                write.competition_season_id or bundle.competition_season_id
            ),
            week=write.week if write.week is not None else bundle.week,
            occurred_at=write.occurred_at,
            creating_generation_id=bundle.generation_id,
            creating_tool_call_id=write.creating_tool_call_id,
            change_reason=write.change_reason,
        )
        resolved.append((write, item, version))
    return tuple(resolved), tuple(retired)


def advance_current_revision(
    session: Session,
    competition_id: UUID,
    parent: LockedRevisionParent,
    revision_id: UUID,
) -> None:
    updated_competition_id = session.scalar(
        sa.update(CurrentRevision)
        .where(
            CurrentRevision.competition_id == competition_id,
            CurrentRevision.current_revision_id == parent.current_revision_id,
            CurrentRevision.lock_version == parent.next_lock_version - 1,
        )
        .values(
            current_revision_id=revision_id,
            lock_version=parent.next_lock_version,
            updated_at=sa.func.now(),
        )
        .returning(CurrentRevision.competition_id)
    )
    if updated_competition_id is None:
        actual = session.scalar(
            sa.select(CurrentRevision.current_revision_id).where(
                CurrentRevision.competition_id == competition_id
            )
        )
        if actual is None:
            raise RevisionNotFoundError(competition_id)
        raise StaleCanonicalRevisionError(
            competition_id,
            parent.current_revision_id,
            actual,
        )
