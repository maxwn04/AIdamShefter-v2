"""Derived search-document contracts shared by per-kind builders."""

from backend.resources.memory.search_documents.builders.event import (
    EVENT_DOCUMENT_BUILDER_VERSION,
    build_event_document,
)
from backend.resources.memory.search_documents.builders.fact import (
    FACT_DOCUMENT_BUILDER_VERSION,
    build_fact_document,
)
from backend.resources.memory.search_documents.builders.storyline import (
    STORYLINE_DOCUMENT_BUILDER_VERSION,
    build_storyline_document,
)
from backend.resources.memory.search_documents.objects import SearchDocumentProjection

__all__ = [
    "EVENT_DOCUMENT_BUILDER_VERSION",
    "FACT_DOCUMENT_BUILDER_VERSION",
    "SearchDocumentProjection",
    "STORYLINE_DOCUMENT_BUILDER_VERSION",
    "build_event_document",
    "build_fact_document",
    "build_storyline_document",
]
