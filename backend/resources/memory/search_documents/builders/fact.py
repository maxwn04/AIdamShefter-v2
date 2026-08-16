from __future__ import annotations

import hashlib
import json
from typing import Any, Final, cast

from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.facts.objects import FactContent, FactEntityRef
from backend.resources.memory.search_documents.objects import (
    SearchDocumentProjection,
)


FACT_DOCUMENT_BUILDER_VERSION: Final = 1


def build_fact_document(content: FactContent) -> SearchDocumentProjection:
    """Deterministically flatten complete fact content for candidate discovery."""

    entity_keys = tuple(sorted({_entity_key(subject) for subject in content.subjects}))
    evidence_version_ids = tuple(
        sorted(set(content.originating_event_version_ids), key=str)
    )
    display_names = tuple(
        sorted(
            {
                subject.display_name
                for subject in content.subjects
                if subject.display_name is not None
            },
            key=lambda value: (value.casefold(), value),
        )
    )

    text_parts = [
        content.claim,
        f"category: {content.category}",
        f"status: {content.status.value}",
        f"confidence: {content.confidence.value}",
        f"numbers:{_canonical_json(content.numbers)}",
    ]
    if display_names:
        text_parts.append(f"participants: {'; '.join(display_names)}")
    if entity_keys:
        text_parts.append(f"entities: {' '.join(entity_keys)}")

    return SearchDocumentProjection(
        kind=MemoryKind.FACT,
        status=content.status.value,
        entity_keys=entity_keys,
        evidence_version_ids=evidence_version_ids,
        document_text="\n".join(text_parts),
        builder_version=FACT_DOCUMENT_BUILDER_VERSION,
        content_hash=_fact_content_hash(content),
    )


def _entity_key(subject: FactEntityRef) -> str:
    prefix = "roster" if subject.kind == "season_roster" else subject.kind
    return f"{prefix}:{subject.id}"


def _fact_content_hash(content: FactContent) -> str:
    serialized = _canonical_json(_canonical_fact_content(content)).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _canonical_fact_content(content: FactContent) -> dict[str, Any]:
    dumped = cast(dict[str, Any], content.model_dump(mode="json"))
    subjects = cast(list[dict[str, Any]], dumped["subjects"])
    dumped["subjects"] = sorted(
        subjects,
        key=lambda subject: (
            str(subject["kind"]),
            str(subject["id"]),
            str(subject["role"]),
            str(subject.get("display_name") or ""),
        ),
    )
    originating_ids = cast(list[str], dumped["originating_event_version_ids"])
    dumped["originating_event_version_ids"] = sorted(originating_ids)
    return {
        "memory_kind": content.memory_kind.value,
        "content": dumped,
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
