"""Package-internal persistence for derived search documents."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.database.models.memory import MemorySearchDocument, MemoryVersion
from backend.resources.memory.search_documents.objects import SearchDocumentProjection


def insert_search_document(
    session: Session,
    version: MemoryVersion,
    projection: SearchDocumentProjection,
) -> None:
    """Attach one projection row to an already-created version in the transaction."""

    session.add(
        MemorySearchDocument(
            version_id=version.id,
            item_id=version.item_id,
            competition_id=version.competition_id,
            kind=projection.kind.value,
            status=projection.status,
            salience=projection.salience,
            competition_season_id=version.competition_season_id,
            week=version.week,
            entity_keys=list(projection.entity_keys),
            evidence_version_ids=list(projection.evidence_version_ids),
            related_item_ids=list(projection.related_item_ids),
            tags=list(projection.tags),
            document_text=projection.document_text,
            builder_version=projection.builder_version,
            content_hash=projection.content_hash,
        )
    )
