"""Canonical visibility SQL shared by typed memory resource managers."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from backend.database.models.memory import MemoryRevision, MemoryVersion


def visible_versions_statement(
    competition_id: UUID,
    revision_id: UUID,
) -> Select[tuple[MemoryVersion]]:
    """Select versions visible at one exact canonical revision."""

    pinned = (
        sa.select(
            MemoryRevision.competition_id.label("competition_id"),
            MemoryRevision.sequence_number.label("sequence_number"),
        )
        .where(
            MemoryRevision.id == revision_id,
            MemoryRevision.competition_id == competition_id,
        )
        .subquery("pinned_revision")
    )
    introduced = aliased(MemoryRevision, name="introduced_revision")
    retired = aliased(MemoryRevision, name="retired_revision")
    return (
        sa.select(MemoryVersion)
        .join(
            pinned,
            pinned.c.competition_id == MemoryVersion.competition_id,
        )
        .join(
            introduced,
            sa.and_(
                introduced.id == MemoryVersion.introduced_revision_id,
                introduced.competition_id == MemoryVersion.competition_id,
            ),
        )
        .outerjoin(
            retired,
            sa.and_(
                retired.id == MemoryVersion.retired_revision_id,
                retired.competition_id == MemoryVersion.competition_id,
            ),
        )
        .where(
            MemoryVersion.competition_id == competition_id,
            introduced.sequence_number <= pinned.c.sequence_number,
            sa.or_(
                MemoryVersion.retired_revision_id.is_(None),
                retired.sequence_number > pinned.c.sequence_number,
            ),
        )
    )
