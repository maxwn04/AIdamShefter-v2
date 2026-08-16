"""Derived search-document contracts shared by per-kind builders."""

from backend.resources.memory.search_documents.builders.fact import (
    FACT_DOCUMENT_BUILDER_VERSION,
    build_fact_document,
)
from backend.resources.memory.search_documents.objects import SearchDocumentProjection

__all__ = [
    "FACT_DOCUMENT_BUILDER_VERSION",
    "SearchDocumentProjection",
    "build_fact_document",
]
