"""PostgreSQL candidate discovery over revision-visible search documents."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Session

from backend.database.models.memory import MemoryItem, MemorySearchDocument
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
