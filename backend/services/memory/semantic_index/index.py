"""Explicit derived indexing and read-only scoring of caller-scoped versions."""

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import math
from uuid import UUID

from pgvector import Vector as VectorValue
from pgvector.sqlalchemy import Vector
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


def _native_vectors(
    vectors: Sequence[Sequence[float]], *, count: int, dimensions: int,
) -> tuple[tuple[float, ...], ...]:
    """Validate provider values before and after pgvector's float32 conversion."""
    checked = validated_vectors(vectors, count=count, dimensions=dimensions)
    return validated_vectors(
        [VectorValue(vector).to_list() for vector in checked],
        count=count, dimensions=dimensions,
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
                cached, stale = self._cached(session, documents, self._provider.spec)
        except (SQLAlchemyError, ValueError):
            return SemanticSearchResult(status="unavailable", total_count=total, reason="semantic_index_unavailable")
        missing = total - len(cached) - stale
        if not cached:
            return SemanticSearchResult(
                status="stale" if stale else "partial", total_count=total,
                missing_count=missing, stale_count=stale,
                reason="semantic_index_requires_rebuild",
            )
        try:
            query_vector, = _native_vectors(
                self._provider.embed([query]), count=1, dimensions=self._provider.spec.dimensions,
            )
        except Exception:
            # Provider exceptions may contain credentials or request bodies. A
            # stable reason is sufficient to explain lexical fallback safely.
            return SemanticSearchResult(
                status="unavailable", total_count=total, available_count=len(cached),
                missing_count=missing, stale_count=stale, reason="semantic_provider_unavailable",
            )
        try:
            with read_only_session(self._sessions) as session:
                # Query embedding happens outside the transaction. Recheck the
                # projection before evaluating its matching stored vectors.
                self._validate_documents(session, documents)
                cached, stale = self._cached(session, documents, self._provider.spec)
                distance = sa.func.public.cosine_distance(
                    MemorySearchEmbedding.embedding,
                    sa.literal(query_vector, type_=Vector()), type_=sa.Float,
                )
                rows = session.execute(sa.select(
                    MemorySearchEmbedding.version_id,
                    (1.0 - distance).label("similarity"),
                ).where(self._matching_embeddings(documents, self._provider.spec)).order_by(
                    distance, MemorySearchEmbedding.version_id,
                ))
                scores = {version_id: similarity for version_id, similarity in rows}
                # Native float32 arithmetic can still overflow or underflow
                # for finite, nonzero inputs. Never expose NaN as a match.
                if any(not math.isfinite(score) for score in scores.values()):
                    raise ValueError("Native cosine similarity is not finite")
        except (SQLAlchemyError, ValueError):
            return SemanticSearchResult(
                status="unavailable", total_count=total, reason="semantic_index_unavailable",
            )
        missing = total - len(cached) - stale
        return SemanticSearchResult(
            scores=scores, status="ready" if len(scores) == total else "partial",
            total_count=total, available_count=len(scores), missing_count=missing,
            stale_count=stale, reason=None if len(scores) == total else "semantic_index_incomplete",
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
            vectors = _native_vectors(
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
    def _matching_embeddings(
        documents: Sequence[EmbeddingDocument], spec: EmbeddingSpec,
    ) -> sa.ColumnElement[bool]:
        """The native distance query can only see compatible eligible versions."""
        embedding = MemorySearchEmbedding
        return sa.and_(
            embedding.provider == spec.provider,
            embedding.model == spec.model,
            embedding.dimensions == spec.dimensions,
            embedding.text_format_version == spec.text_format_version,
            sa.tuple_(
                embedding.version_id, embedding.document_builder_version,
                embedding.source_content_hash, embedding.text_hash,
            ).in_([
                (document.version_id, document.builder_version,
                 document.content_hash, text_hash(document))
                for document in documents
            ]),
            sa.func.public.vector_norm(embedding.embedding) > 0,
        )

    @classmethod
    def _cached(
        cls, session: Session, documents: Sequence[EmbeddingDocument], spec: EmbeddingSpec,
    ) -> tuple[set[UUID], int]:
        """Read coverage identifiers only; vector storage and arithmetic stay in PostgreSQL."""
        if not documents:
            return set(), 0
        seen = set(session.scalars(sa.select(MemorySearchEmbedding.version_id).where(
            MemorySearchEmbedding.version_id.in_([document.version_id for document in documents]),
        )))
        matching = set(session.scalars(sa.select(MemorySearchEmbedding.version_id).where(
            cls._matching_embeddings(documents, spec),
        )))
        return matching, len(seen - matching)
