"""Competition-scoped reference validation for complete trigger content."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.database.models.core import CompetitionSeason, Franchise
from backend.database.models.memory import MemoryItem
from backend.resources.memory.common.errors import (
    CrossCompetitionEntityReferenceError,
    CrossCompetitionReferenceError,
    EntityReferenceNotFoundError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.triggers.conditions.rematch import RematchCondition
from backend.resources.memory.triggers.objects import TriggerContent


@dataclass(frozen=True, slots=True)
class ValidatedTriggerContent:
    competition_id: UUID
    content: TriggerContent


def validate_trigger_content(
    session: Session,
    competition_id: UUID,
    content: TriggerContent,
) -> ValidatedTriggerContent:
    """Validate all database-backed trigger references in the transaction."""

    _validate_target_season(session, competition_id, content)
    _validate_condition(session, competition_id, content)
    _validate_stable_target(
        session,
        competition_id,
        content.target_storyline_item_id,
        MemoryKind.STORYLINE,
    )
    _validate_stable_target(
        session,
        competition_id,
        content.origin_event_item_id,
        MemoryKind.EVENT,
    )
    return ValidatedTriggerContent(
        competition_id=competition_id,
        content=content,
    )


def _validate_target_season(
    session: Session,
    competition_id: UUID,
    content: TriggerContent,
) -> None:
    season_id = content.target_competition_season_id
    if season_id is None:
        return
    actual_scope = session.scalar(
        sa.select(CompetitionSeason.competition_id).where(
            CompetitionSeason.id == season_id
        )
    )
    if actual_scope is None:
        raise EntityReferenceNotFoundError("season", season_id)
    if actual_scope != competition_id:
        raise CrossCompetitionEntityReferenceError(
            "season",
            season_id,
            competition_id,
        )


def _validate_condition(
    session: Session,
    competition_id: UUID,
    content: TriggerContent,
) -> None:
    if not isinstance(content.condition, RematchCondition):
        return
    rows = session.execute(
        sa.select(Franchise.id, Franchise.competition_id).where(
            Franchise.id.in_(set(content.condition.franchise_ids))
        )
    )
    found = {franchise_id: scope for franchise_id, scope in rows}
    for franchise_id in content.condition.franchise_ids:
        actual_scope = found.get(franchise_id)
        if actual_scope is None:
            raise EntityReferenceNotFoundError("franchise", franchise_id)
        if actual_scope != competition_id:
            raise CrossCompetitionEntityReferenceError(
                "franchise",
                franchise_id,
                competition_id,
            )


def _validate_stable_target(
    session: Session,
    competition_id: UUID,
    item_id: UUID | None,
    expected_kind: MemoryKind,
) -> None:
    if item_id is None:
        return
    item = session.get(MemoryItem, item_id)
    if item is None:
        raise TargetNotFoundError(item_id, (expected_kind,))
    if item.competition_id != competition_id:
        raise CrossCompetitionReferenceError(
            item_id,
            competition_id,
            item.competition_id,
        )
    if item.kind != expected_kind.value:
        raise WrongTargetKindError(
            item_id,
            (expected_kind,),
            MemoryKind(item.kind),
        )
