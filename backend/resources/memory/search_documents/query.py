"""PostgreSQL candidate discovery over revision-visible search documents."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Session, aliased

from backend.database.models.core.competitions import CompetitionSeason
from backend.database.models.memory import MemoryItem, MemorySearchDocument
from backend.database.models.memory.context_notes import ContextNote
from backend.database.models.memory.triggers import TriggerVersion
from backend.resources.memory.revisions.shared import visible_versions_statement
from backend.resources.memory.search_documents.objects import SearchDocumentQuery


def query_search_documents(
    session: Session,
    competition_id: UUID,
    revision_id: UUID,
    query: SearchDocumentQuery,
) -> tuple[tuple[MemorySearchDocument, float], ...]:
    """Return visible rows matching any discovery signal and every filter."""

    visible = visible_versions_statement(competition_id, revision_id).subquery(
        "visible_memory_versions"
    )
    lexical_query = (
        sa.func.websearch_to_tsquery("english", query.text)
        if query.text is not None
        else None
    )
    lexical_rank = (
        sa.func.ts_rank_cd(MemorySearchDocument.search_vector, lexical_query)
        if lexical_query is not None
        else sa.literal(0.0)
    ).label("lexical_rank")
    statement = (
        sa.select(MemorySearchDocument, lexical_rank)
        .join(visible, visible.c.id == MemorySearchDocument.version_id)
        .where(MemorySearchDocument.competition_id == competition_id)
    )

    if query.kinds:
        statement = statement.where(
            MemorySearchDocument.kind.in_(kind.value for kind in query.kinds)
        )
    if query.statuses:
        statement = statement.where(MemorySearchDocument.status.in_(query.statuses))
    if query.agent_key is not None:
        statement = statement.join(
            MemoryItem, MemoryItem.id == MemorySearchDocument.item_id
        ).where(MemoryItem.agent_key == query.agent_key)
    if query.competition_season_id is not None:
        statement = statement.where(
            MemorySearchDocument.competition_season_id
            == query.competition_season_id
        )
    if query.season is not None:
        statement = statement.join(
            CompetitionSeason,
            sa.and_(
                CompetitionSeason.id == MemorySearchDocument.competition_season_id,
                CompetitionSeason.competition_id == competition_id,
            ),
        ).where(CompetitionSeason.season_year == query.season)
    if query.required_entity_keys:
        statement = statement.where(
            sa.or_(
                MemorySearchDocument.entity_keys.op("&&")(
                    sa.cast(list(query.required_entity_keys), ARRAY(sa.Text()))
                ),
                _trigger_reference_entity_match(competition_id, revision_id, query),
            )
        )
    if query.due_in_season is not None:
        statement = statement.join(
            TriggerVersion, TriggerVersion.version_id == MemorySearchDocument.version_id,
        ).where(
            TriggerVersion.competition_id == competition_id,
            sa.or_(
                TriggerVersion.target_competition_season_id.is_(None),
                TriggerVersion.target_competition_season_id == query.due_in_season,
            ),
            sa.or_(
                TriggerVersion.status == "open",
                sa.and_(TriggerVersion.fire_policy != "one_shot", TriggerVersion.status == "fired"),
            ),
            sa.or_(
                TriggerVersion.target_week.is_not(None),
                TriggerVersion.target_at.is_not(None),
            ),
            sa.or_(
                TriggerVersion.target_week.is_(None),
                TriggerVersion.target_week <= query.due_week if query.due_week is not None else sa.false(),
            ),
            sa.or_(
                TriggerVersion.target_at.is_(None),
                TriggerVersion.target_at <= query.due_at if query.due_at is not None else sa.false(),
            ),
        )
    if query.context_for_season is not None:
        statement = statement.join(
            ContextNote, ContextNote.item_id == MemorySearchDocument.item_id,
        ).where(
            ContextNote.competition_id == competition_id,
            sa.or_(
                ContextNote.scope == "competition",
                sa.and_(
                    ContextNote.scope == "competition_season",
                    ContextNote.competition_season_id == query.context_for_season,
                ),
                sa.and_(
                    ContextNote.scope == "franchise",
                    ContextNote.franchise_id.in_(query.context_franchise_ids),
                ),
            ),
        )
    statement = statement.where(
        *temporal_conditions(
            competition_id, query,
            season_id=visible.c.competition_season_id,
            week=visible.c.week,
            recorded_at=visible.c.recorded_at,
        )
    )
    if query.week is not None:
        statement = statement.where(MemorySearchDocument.week == query.week)
    if query.week_from is not None:
        statement = statement.where(MemorySearchDocument.week >= query.week_from)
    if query.week_to is not None:
        statement = statement.where(MemorySearchDocument.week <= query.week_to)

    signals: list[sa.ColumnElement[bool]] = []
    if query.entity_keys:
        signals.append(
            MemorySearchDocument.entity_keys.op("&&")(
                sa.cast(list(query.entity_keys), ARRAY(sa.Text()))
            )
        )
    if query.evidence_version_ids:
        signals.append(
            MemorySearchDocument.evidence_version_ids.op("&&")(
                sa.cast(
                    list(query.evidence_version_ids),
                    ARRAY(PGUUID(as_uuid=True)),
                )
            )
        )
    if query.related_item_ids:
        signals.append(
            MemorySearchDocument.related_item_ids.op("&&")(
                sa.cast(
                    list(query.related_item_ids),
                    ARRAY(PGUUID(as_uuid=True)),
                )
            )
        )
    if query.tags:
        signals.append(
            MemorySearchDocument.tags.op("&&")(
                sa.cast(list(query.tags), ARRAY(sa.Text()))
            )
        )
    if lexical_query is not None:
        signals.append(MemorySearchDocument.search_vector.op("@@")(lexical_query))
    if signals:
        statement = statement.where(sa.or_(*signals))

    rows = session.execute(statement).all()
    return tuple((row[0], float(row[1])) for row in rows)


def _trigger_reference_entity_match(
    competition_id: UUID,
    revision_id: UUID,
    query: SearchDocumentQuery,
) -> sa.ColumnElement[bool]:
    """Let callbacks inherit team filters from one pinned, eligible parent.

    Scheduled and trade callbacks need not repeat their parent's franchises in
    their own condition. Resolve only their canonical storyline/event links;
    never enrich stored projections or traverse arbitrary related-item chains.
    """
    trigger = aliased(TriggerVersion, name="entity_filter_trigger")
    target_document = aliased(MemorySearchDocument, name="entity_filter_target")
    target_version = visible_versions_statement(
        competition_id, revision_id,
    ).subquery("entity_filter_visible_targets")
    inherited = (
        sa.select(sa.literal(1))
        .select_from(trigger)
        .join(
            target_version,
            sa.or_(
                target_version.c.item_id == trigger.target_storyline_item_id,
                target_version.c.item_id == trigger.origin_event_item_id,
            ),
        )
        .join(target_document, target_document.version_id == target_version.c.id)
        .where(
            trigger.version_id == MemorySearchDocument.version_id,
            trigger.competition_id == competition_id,
            target_document.competition_id == competition_id,
            sa.or_(
                sa.and_(
                    target_version.c.item_id == trigger.target_storyline_item_id,
                    target_document.kind == "storyline",
                ),
                sa.and_(
                    target_version.c.item_id == trigger.origin_event_item_id,
                    target_document.kind == "event",
                ),
            ),
            target_document.entity_keys.op("&&")(
                sa.cast(list(query.required_entity_keys), ARRAY(sa.Text()))
            ),
            *temporal_conditions(
                competition_id, query,
                season_id=target_version.c.competition_season_id,
                week=target_version.c.week,
                recorded_at=target_version.c.recorded_at,
            ),
        )
        .correlate(MemorySearchDocument)
        .exists()
    )
    return sa.and_(MemorySearchDocument.kind == "trigger", inherited)


def temporal_conditions(
    competition_id: UUID,
    query: SearchDocumentQuery,
    *,
    season_id: sa.ColumnElement[UUID | None],
    week: sa.ColumnElement[int | None],
    recorded_at: sa.ColumnElement[datetime],
) -> tuple[sa.ColumnElement[bool], ...]:
    """Bound canonical versions by the generation's season and observation clock."""
    conditions: list[sa.ColumnElement[bool]] = []
    if query.allowed_season_weeks is not None:
        conditions.append(
            sa.or_(
                season_id.is_(None),
                *(
                    sa.and_(
                        season_id == allowed_season,
                        sa.or_(week.is_(None), week <= through_week),
                    )
                    for allowed_season, through_week in query.allowed_season_weeks.items()
                ),
            )
        )
    if query.recorded_through is not None:
        conditions.append(recorded_at <= query.recorded_through)
    if query.through_competition_season_id is not None:
        boundary_year = sa.select(CompetitionSeason.season_year).where(
            CompetitionSeason.id == query.through_competition_season_id,
            CompetitionSeason.competition_id == competition_id,
        ).correlate(None).scalar_subquery()
        eligible_seasons = sa.select(CompetitionSeason.id).where(
            CompetitionSeason.competition_id == competition_id,
            CompetitionSeason.season_year <= boundary_year,
        ).correlate(None)
        conditions.append(sa.or_(season_id.is_(None), season_id.in_(eligible_seasons)))
        if query.through_week is not None:
            conditions.append(
                sa.or_(
                    season_id.is_(None),
                    season_id != query.through_competition_season_id,
                    week.is_(None),
                    week <= query.through_week,
                )
            )
    return tuple(conditions)
