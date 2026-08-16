"""Competition-scoped reference validation for complete fact content."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.database.models.core import CompetitionSeason, Franchise, SeasonRoster
from backend.database.models.memory import EventVersion, MemoryItem, MemoryVersion
from backend.database.models.reporting import Generation, ToolCall
from backend.database.models.sleeper import ApiRequest, LeagueUser, Player, User
from backend.resources.memory.common.errors import (
    CrossCompetitionEntityReferenceError,
    CrossCompetitionReferenceError,
    EntityReferenceNotFoundError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.facts.objects import FactContent


@dataclass(frozen=True, slots=True)
class ValidatedFactContent:
    competition_id: UUID
    content: FactContent
    primary_tool_call_generation_id: UUID | None


def validate_fact_content(
    session: Session,
    competition_id: UUID,
    content: FactContent,
) -> ValidatedFactContent:
    """Validate all database-backed fact references in the caller's transaction."""

    _validate_subjects(session, competition_id, content)
    _validate_originating_events(session, competition_id, content)
    receipt_generation_id = _validate_tool_receipt(
        session, competition_id, content.primary_tool_call_id
    )
    _validate_api_receipt(session, competition_id, content.primary_api_request_id)
    return ValidatedFactContent(
        competition_id=competition_id,
        content=content,
        primary_tool_call_generation_id=receipt_generation_id,
    )


def _validate_subjects(
    session: Session,
    competition_id: UUID,
    content: FactContent,
) -> None:
    franchise_ids: list[UUID] = []
    roster_ids: list[UUID] = []
    season_ids: list[UUID] = []
    player_ids: list[str] = []
    user_ids: list[str] = []
    for subject in content.subjects:
        match subject.kind:
            case "franchise":
                franchise_ids.append(subject.id)
            case "season_roster":
                roster_ids.append(subject.id)
            case "season":
                season_ids.append(subject.id)
            case "player":
                player_ids.append(subject.id)
            case "sleeper_user":
                user_ids.append(subject.id)

    _validate_scoped_uuid_entities(
        session,
        competition_id,
        "franchise",
        Franchise.id,
        Franchise.competition_id,
        franchise_ids,
    )
    _validate_scoped_uuid_entities(
        session,
        competition_id,
        "season_roster",
        SeasonRoster.id,
        SeasonRoster.competition_id,
        roster_ids,
    )
    _validate_scoped_uuid_entities(
        session,
        competition_id,
        "season",
        CompetitionSeason.id,
        CompetitionSeason.competition_id,
        season_ids,
    )

    if player_ids:
        found_players = set(
            session.scalars(
                sa.select(Player.sleeper_player_id).where(
                    Player.sleeper_player_id.in_(set(player_ids))
                )
            )
        )
        for player_id in player_ids:
            if player_id not in found_players:
                raise EntityReferenceNotFoundError("player", player_id)

    if user_ids:
        rows = session.execute(
            sa.select(User.sleeper_user_id, CompetitionSeason.competition_id)
            .outerjoin(
                LeagueUser,
                LeagueUser.sleeper_user_id == User.sleeper_user_id,
            )
            .outerjoin(
                CompetitionSeason,
                CompetitionSeason.id == LeagueUser.competition_season_id,
            )
            .where(User.sleeper_user_id.in_(set(user_ids)))
        )
        memberships: dict[str, set[UUID]] = {}
        found_users: set[str] = set()
        for user_id, scoped_competition_id in rows:
            found_users.add(user_id)
            if scoped_competition_id is not None:
                memberships.setdefault(user_id, set()).add(scoped_competition_id)
        for user_id in user_ids:
            if user_id not in found_users:
                raise EntityReferenceNotFoundError("sleeper_user", user_id)
            if competition_id not in memberships.get(user_id, set()):
                raise CrossCompetitionEntityReferenceError(
                    "sleeper_user", user_id, competition_id
                )


def _validate_scoped_uuid_entities(
    session: Session,
    competition_id: UUID,
    entity_kind: str,
    id_column: InstrumentedAttribute[UUID],
    competition_column: InstrumentedAttribute[UUID],
    ids: list[UUID],
) -> None:
    if not ids:
        return
    rows = session.execute(
        sa.select(id_column, competition_column).where(id_column.in_(set(ids)))
    )
    found: dict[UUID, UUID] = {entity_id: scope for entity_id, scope in rows}
    for entity_id in ids:
        actual_scope = found.get(entity_id)
        if actual_scope is None:
            raise EntityReferenceNotFoundError(entity_kind, entity_id)
        if actual_scope != competition_id:
            raise CrossCompetitionEntityReferenceError(
                entity_kind, entity_id, competition_id
            )


def _validate_originating_events(
    session: Session,
    competition_id: UUID,
    content: FactContent,
) -> None:
    expected = content.originating_event_version_ids
    if not expected:
        return
    rows = session.execute(
        sa.select(
            MemoryVersion.id,
            MemoryVersion.competition_id,
            MemoryItem.kind,
            EventVersion.version_id.label("typed_event_version_id"),
        )
        .join(MemoryItem, MemoryItem.id == MemoryVersion.item_id)
        .outerjoin(EventVersion, EventVersion.version_id == MemoryVersion.id)
        .where(MemoryVersion.id.in_(set(expected)))
    )
    found = {
        version_id: (scope, kind, typed_event_id)
        for version_id, scope, kind, typed_event_id in rows
    }
    for version_id in expected:
        target = found.get(version_id)
        if target is None:
            raise TargetNotFoundError(version_id, (MemoryKind.EVENT,))
        target_scope, target_kind, typed_event_id = target
        if target_scope != competition_id:
            raise CrossCompetitionReferenceError(
                version_id, competition_id, target_scope
            )
        if target_kind != MemoryKind.EVENT.value:
            raise WrongTargetKindError(
                version_id,
                (MemoryKind.EVENT,),
                MemoryKind(target_kind),
            )
        if typed_event_id is None:
            raise TargetNotFoundError(version_id, (MemoryKind.EVENT,))


def _validate_tool_receipt(
    session: Session,
    competition_id: UUID,
    tool_call_id: UUID | None,
) -> UUID | None:
    if tool_call_id is None:
        return None
    row = session.execute(
        sa.select(ToolCall.generation_id, Generation.competition_id)
        .join(Generation, Generation.id == ToolCall.generation_id)
        .where(ToolCall.id == tool_call_id)
    ).one_or_none()
    if row is None:
        raise EntityReferenceNotFoundError("tool_call", tool_call_id)
    generation_id, actual_scope = row
    if actual_scope != competition_id:
        raise CrossCompetitionEntityReferenceError(
            "tool_call", tool_call_id, competition_id
        )
    return generation_id


def _validate_api_receipt(
    session: Session,
    competition_id: UUID,
    api_request_id: UUID | None,
) -> None:
    if api_request_id is None:
        return
    row = session.execute(
        sa.select(ApiRequest.id, CompetitionSeason.competition_id)
        .outerjoin(
            CompetitionSeason,
            CompetitionSeason.id == ApiRequest.competition_season_id,
        )
        .where(ApiRequest.id == api_request_id)
    ).one_or_none()
    if row is None:
        raise EntityReferenceNotFoundError("api_request", api_request_id)
    _, actual_scope = row
    if actual_scope is not None and actual_scope != competition_id:
        raise CrossCompetitionEntityReferenceError(
            "api_request", api_request_id, competition_id
        )
