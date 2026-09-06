"""Explicit derived indexing and read-only scoring of caller-scoped versions."""

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import math
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database.models.memory import MemorySearchDocument, MemorySearchEmbedding
from backend.database.sessions import SessionFactory, read_only_session, transaction_session
from backend.resources.memory.search_documents.semantic import EmbeddingDocument, SemanticSearchResult
from backend.services.memory.semantic_index.provider import (
    EmbeddingProvider, EmbeddingSpec, validated_vectors,
)


def text_hash(document: EmbeddingDocument) -> str:
    """Format 1 embeds the complete existing projection without rewriting it."""
    return hashlib.sha256(document.document_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IndexBuildResult:
    indexed: int
    reused: int
    requested: int
    spec: EmbeddingSpec


class SemanticIndex:
    def __init__(
        self, session_factory: SessionFactory, competition_id: UUID,
        provider: EmbeddingProvider | None,
    ) -> None:
        self._sessions = session_factory
        self._competition_id = competition_id
        self._provider = provider

    def score(
        self, query: str, documents: Sequence[EmbeddingDocument],
    ) -> SemanticSearchResult:
        """Score only eligible supplied documents; never fill the index here."""
        documents = self._unique(documents)
        total = len(documents)
        if self._provider is None:
            return SemanticSearchResult(status="disabled", total_count=total, reason="semantic_provider_disabled")
        if not documents:
            return SemanticSearchResult(status="ready")
        try:
            with read_only_session(self._sessions) as session:
                self._validate_documents(session, documents)
                vectors, stale = self._cached(session, documents, self._provider.spec)
        except (SQLAlchemyError, ValueError):
            return SemanticSearchResult(status="unavailable", total_count=total, reason="semantic_index_unavailable")
        missing = total - len(vectors) - stale
        if not vectors:
            return SemanticSearchResult(
                status="stale" if stale else "partial", total_count=total,
                missing_count=missing, stale_count=stale,
                reason="semantic_index_requires_rebuild",
            )
        try:
            query_vector, = validated_vectors(
                self._provider.embed([query]), count=1, dimensions=self._provider.spec.dimensions,
            )
        except Exception:
            # Provider exceptions may contain credentials or request bodies. A
            # stable reason is sufficient to explain lexical fallback safely.
            return SemanticSearchResult(
                status="unavailable", total_count=total, available_count=len(vectors),
                missing_count=missing, stale_count=stale, reason="semantic_provider_unavailable",
            )
        query_norm = math.hypot(*query_vector)
        scores: dict[UUID, float] = {}
        for version_id, vector in vectors.items():
            norm = math.hypot(*vector)
            scores[version_id] = max(-1.0, min(1.0, sum(
                (a / query_norm) * (b / norm)
                for a, b in zip(query_vector, vector, strict=True)
            )))
        return SemanticSearchResult(
            scores=scores, status="ready" if len(vectors) == total else "partial",
            total_count=total, available_count=len(vectors), missing_count=missing,
            stale_count=stale, reason=None if len(vectors) == total else "semantic_index_incomplete",
        )

    def index_missing(
        self, documents: Sequence[EmbeddingDocument], *, batch_size: int = 64,
    ) -> IndexBuildResult:
        """Explicit paid-capable indexing; all inputs verified before any call.

        Batches commit independently, making an interrupted run resumable. A
        provider failure leaves completed derived batches and canonical history
        untouched. Existing matching vectors are reused on the next invocation.
        """
        if self._provider is None:
            raise ValueError("An explicit embedding provider is required for indexing")
        if batch_size < 1 or batch_size > 256:
            raise ValueError("batch_size must be between 1 and 256")
        documents = self._unique(documents)
        spec = self._provider.spec
        with read_only_session(self._sessions) as session:
            self._validate_documents(session, documents)
            cached, _ = self._cached(session, documents, spec)
        missing = [document for document in documents if document.version_id not in cached]
        indexed = 0
        for offset in range(0, len(missing), batch_size):
            batch = missing[offset:offset + batch_size]
            vectors = validated_vectors(
                self._provider.embed([document.document_text for document in batch]),
                count=len(batch), dimensions=spec.dimensions,
            )
            with transaction_session(self._sessions) as session:
                # A projection rebuild while the provider was running must not
                # install stale data under the updated projection's identity.
                self._validate_documents(session, batch)
                for document, vector in zip(batch, vectors, strict=True):
                    statement = insert(MemorySearchEmbedding).values(
                        version_id=document.version_id, provider=spec.provider,
                        model=spec.model, dimensions=spec.dimensions,
                        text_format_version=spec.text_format_version,
                        document_builder_version=document.builder_version,
                        source_content_hash=document.content_hash,
                        text_hash=text_hash(document), embedding=list(vector),
                    )
                    session.execute(statement.on_conflict_do_update(
                        index_elements=["version_id", "provider", "model", "dimensions", "text_format_version"],
                        set_={
                            "document_builder_version": statement.excluded.document_builder_version,
                            "source_content_hash": statement.excluded.source_content_hash,
                            "text_hash": statement.excluded.text_hash,
                            "embedding": statement.excluded.embedding, "indexed_at": sa.func.now(),
                        },
                    ))
            indexed += len(batch)
        return IndexBuildResult(indexed=indexed, reused=len(cached), requested=len(documents), spec=spec)

    def validate_documents(self, documents: Sequence[EmbeddingDocument]) -> None:
        """Preview an explicit rebuild manifest without provider calls or writes."""
        documents = self._unique(documents)
        with read_only_session(self._sessions) as session:
            self._validate_documents(session, documents)

    @staticmethod
    def _unique(documents: Sequence[EmbeddingDocument]) -> tuple[EmbeddingDocument, ...]:
        unique: dict[UUID, EmbeddingDocument] = {}
        for document in documents:
            if document.version_id in unique and unique[document.version_id] != document:
                raise ValueError("Conflicting documents for one version")
            unique[document.version_id] = document
        return tuple(unique.values())

    def _validate_documents(self, session: Session, documents: Sequence[EmbeddingDocument]) -> None:
        if not documents:
            return
        rows = session.scalars(sa.select(MemorySearchDocument).where(
            MemorySearchDocument.competition_id == self._competition_id,
            MemorySearchDocument.version_id.in_([document.version_id for document in documents]),
        ))
        canonical = {row.version_id: row for row in rows}
        for document in documents:
            row = canonical.get(document.version_id)
            if row is None or (
                row.content_hash != document.content_hash
                or row.builder_version != document.builder_version
                or row.document_text != document.document_text
            ):
                raise ValueError("Embedding input does not match this competition's current search projection")

    @staticmethod
    def _cached(
        session: Session, documents: Sequence[EmbeddingDocument], spec: EmbeddingSpec,
    ) -> tuple[dict[UUID, tuple[float, ...]], int]:
        if not documents:
            return {}, 0
        by_id = {document.version_id: document for document in documents}
        rows = session.scalars(sa.select(MemorySearchEmbedding).where(
            MemorySearchEmbedding.version_id.in_(by_id),
        ))
        seen: set[UUID] = set()
        vectors: dict[UUID, tuple[float, ...]] = {}
        for row in rows:
            seen.add(row.version_id)
            document = by_id[row.version_id]
            if (
                (row.provider, row.model, row.dimensions, row.text_format_version)
                != (spec.provider, spec.model, spec.dimensions, spec.text_format_version)
                or row.document_builder_version != document.builder_version
                or row.source_content_hash != document.content_hash
                or row.text_hash != text_hash(document)
            ):
                continue
            try:
                vector, = validated_vectors([row.embedding], count=1, dimensions=spec.dimensions)
            except (ValueError, TypeError, OverflowError):
                continue
            vectors[row.version_id] = vector
        return vectors, len(seen - vectors.keys())
