"""Optional semantic scoring with explicit, rebuildable derived indexing."""

from backend.resources.memory.search_documents.semantic import (
    EmbeddingDocument, SemanticScorer, SemanticSearchResult,
)
from backend.services.memory.semantic_index.index import IndexBuildResult, SemanticIndex
from backend.services.memory.semantic_index.provider import (
    EmbeddingProvider, EmbeddingSpec, OpenAIEmbeddingProvider,
)

__all__ = [
    "EmbeddingDocument", "EmbeddingProvider", "EmbeddingSpec", "IndexBuildResult",
    "OpenAIEmbeddingProvider", "SemanticIndex", "SemanticScorer", "SemanticSearchResult",
]
