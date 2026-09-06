from collections.abc import Sequence
from dataclasses import replace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.memory import MemorySearchDocument, MemorySearchEmbedding, MemoryVersion
from backend.database.sessions import create_session_factory
from backend.services.memory.semantic_index import (
    EmbeddingDocument, EmbeddingSpec, OpenAIEmbeddingProvider, SemanticIndex,
)
from backend.services.memory.semantic_index.provider import validated_vectors
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.memory.test_search_document_manager import _committed_bundle


class FakeProvider:
    def __init__(self, *, model: str = "offline-v1") -> None:
        self.spec = EmbeddingSpec(provider="offline", model=model, dimensions=3)
        self.calls: list[tuple[str, ...]] = []
        self.fail = False
        self.malformed = False
        self.fail_on_call: int | None = None

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.calls.append(tuple(texts))
        if self.fail or len(self.calls) == self.fail_on_call:
            raise RuntimeError("provider secret must not escape")
        return [[1.0, 0.0] if self.malformed else [1.0, 0.0, 0.0] for _ in texts]


def _fixture(engine: Engine):
    domain, _, _ = _committed_bundle(engine)
    with create_session_factory(engine)() as session:
        rows = session.scalars(sa.select(MemorySearchDocument).where(
            MemorySearchDocument.competition_id == domain.competition_id,
        )).all()
        documents = tuple(EmbeddingDocument(row.version_id, row.document_text, row.content_hash, row.builder_version) for row in rows)
    provider = FakeProvider()
    index = SemanticIndex(create_session_factory(engine), domain.competition_id, provider)
    return domain, documents, provider, index


def test_explicit_index_reuses_vectors_and_search_never_fills_missing(database_engine: Engine) -> None:
    _, documents, provider, index = _fixture(database_engine)
    with database_engine.connect() as connection:
        canonical_before = connection.execute(sa.select(MemoryVersion.__table__)).all()
    absent = index.score("trade payoff", documents)
    assert absent.status == "partial" and absent.missing_count == len(documents)
    assert provider.calls == []

    build = index.index_missing(documents[:2], batch_size=1)
    assert (build.indexed, build.reused, build.requested) == (2, 0, 2)
    assert len(provider.calls) == 2
    result = index.score("trade payoff", documents)
    assert result.status == "partial" and result.available_count == 2
    assert result.missing_count == len(documents) - 2
    assert set(result.scores) == {row.version_id for row in documents[:2]}
    assert all(score == pytest.approx(1.0) for score in result.scores.values())
    assert provider.calls[-1] == ("trade payoff",)
    repeat = index.index_missing(documents[:2])
    assert repeat.reused == 2 and repeat.indexed == 0 and len(provider.calls) == 3
    with database_engine.connect() as connection:
        assert connection.execute(sa.select(MemoryVersion.__table__)).all() == canonical_before


def test_invalid_manifest_and_foreign_competition_make_no_provider_calls(database_engine: Engine) -> None:
    _, documents, provider, index = _fixture(database_engine)
    with pytest.raises(ValueError, match="does not match"):
        index.index_missing([replace(documents[0], document_text="injected narrative")])
    foreign = SemanticIndex(create_session_factory(database_engine), uuid4(), provider)
    with pytest.raises(ValueError, match="does not match"):
        foreign.index_missing(documents)
    with pytest.raises(ValueError, match="Conflicting"):
        index.index_missing([documents[0], replace(documents[0], content_hash="0" * 64)])
    assert foreign.score("anything", documents).status == "unavailable"
    assert provider.calls == []


def test_model_change_and_source_hash_change_are_explicitly_stale(database_engine: Engine) -> None:
    domain, documents, provider, index = _fixture(database_engine)
    document = documents[0]
    index.index_missing([document])
    changed_provider = FakeProvider(model="offline-v2")
    changed = SemanticIndex(create_session_factory(database_engine), domain.competition_id, changed_provider)
    assert changed.score("query", [document]).status == "stale"
    assert changed_provider.calls == []
    changed.index_missing([document])
    assert changed.score("query", [document]).status == "ready"

    with database_engine.begin() as connection:
        connection.execute(sa.update(MemorySearchDocument).where(
            MemorySearchDocument.version_id == document.version_id,
        ).values(document_text=document.document_text + "\nnew builder content", builder_version=document.builder_version + 1))
    updated = replace(document, document_text=document.document_text + "\nnew builder content", builder_version=document.builder_version + 1)
    result = index.score("query", [updated])
    assert result.status == "stale" and result.stale_count == 1
    assert index.index_missing([updated]).indexed == 1
    assert index.score("query", [updated]).status == "ready"


def test_provider_failure_and_malformed_cache_degrade_without_index_writes(database_engine: Engine) -> None:
    _, documents, provider, index = _fixture(database_engine)
    document = documents[0]
    index.index_missing([document])
    provider.fail = True
    result = index.score("query", [document])
    assert result.status == "unavailable" and result.reason == "semantic_provider_unavailable"
    assert "secret" not in repr(result)
    provider.fail = False
    provider.malformed = True
    assert index.score("query", [document]).status == "unavailable"
    with database_engine.begin() as connection:
        connection.execute(sa.update(MemorySearchEmbedding).where(
            MemorySearchEmbedding.version_id == document.version_id,
        ).values(embedding=[0.0, 0.0, 0.0]))
    provider.calls.clear()
    assert index.score("query", [document]).status == "stale"
    assert provider.calls == []


def test_failed_batch_is_resumable_without_repeating_completed_embeddings(database_engine: Engine) -> None:
    _, documents, provider, index = _fixture(database_engine)
    provider.fail_on_call = 2
    with pytest.raises(RuntimeError):
        index.index_missing(documents, batch_size=1)
    provider.fail_on_call = None
    resumed = index.index_missing(documents)
    assert resumed.indexed == len(documents) - 1 and resumed.reused == 1
    assert documents[0].document_text not in provider.calls[-1]
    assert index.index_missing(documents).reused == len(documents)


def test_missing_index_table_degrades_and_runtime_role_has_derived_table_access(database_engine: Engine) -> None:
    domain, documents, provider, index = _fixture(database_engine)
    disabled = SemanticIndex(create_session_factory(database_engine), domain.competition_id, None)
    assert disabled.score("query", documents).status == "disabled"
    with database_engine.begin() as connection:
        assert connection.scalar(sa.text(
            "SELECT has_table_privilege('aidam_runtime', 'memory.memory_search_embeddings', 'SELECT, INSERT, UPDATE, DELETE')"
        ))
        connection.execute(sa.text("ALTER TABLE memory.memory_search_embeddings RENAME TO temporarily_unavailable_embeddings"))
    try:
        result = index.score("query", documents)
        assert result.status == "unavailable" and result.reason == "semantic_index_unavailable"
        assert provider.calls == []
    finally:
        with database_engine.begin() as connection:
            connection.execute(sa.text("ALTER TABLE memory.temporarily_unavailable_embeddings RENAME TO memory_search_embeddings"))


@pytest.mark.parametrize("vector", [[0, 0], [float("nan"), 1], [float("inf"), 1], [True, 1], [1]])
def test_embedding_boundary_rejects_malformed_vectors(vector) -> None:
    with pytest.raises(ValueError):
        validated_vectors([vector], count=1, dimensions=2)


def test_openai_adapter_orders_response_and_is_lazy() -> None:
    calls = []
    def call(**kwargs):
        calls.append(kwargs)
        return {"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]}
    provider = OpenAIEmbeddingProvider(EmbeddingSpec(dimensions=2), embedding_call=call)
    assert calls == []
    assert provider.embed(["alpha", "beta"]) == ((1.0, 0.0), (0.0, 1.0))
    assert calls[0]["num_retries"] == 0 and calls[0]["dimensions"] == 2
