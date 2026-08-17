from __future__ import annotations

import hashlib
import json
from typing import Any, Final, cast

from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.search_documents.objects import (
    SearchDocumentProjection,
)
from backend.resources.memory.storylines.objects import (
    EvidenceRef,
    RelatedStorylineRef,
    StorylineContent,
    StorylineEntityRef,
)


STORYLINE_DOCUMENT_BUILDER_VERSION: Final = 1


def build_storyline_document(
    content: StorylineContent,
) -> SearchDocumentProjection:
    """Deterministically flatten complete storyline content for discovery."""

    entity_keys = tuple(sorted({_entity_key(subject) for subject in content.subjects}))
    evidence_version_ids = tuple(
        sorted({reference.version_id for reference in content.evidence}, key=str)
    )
    related_item_ids = tuple(
        sorted(
            {reference.item_id for reference in content.related_storylines},
            key=str,
        )
    )
    tags = tuple(sorted(set(content.tags)))

    text_parts = [
        content.headline,
        content.summary,
        f"status: {content.status.value}",
    ]
    if content.arc_type is not None:
        text_parts.append(f"arc type: {content.arc_type}")
    if tags:
        text_parts.append(f"tags: {' '.join(tags)}")

    participants = sorted(_participant_text(subject) for subject in content.subjects)
    if participants:
        text_parts.append(f"participants: {'; '.join(participants)}")
    if content.evidence:
        labels = sorted(_evidence_text(reference) for reference in content.evidence)
        text_parts.append(f"evidence: {'; '.join(labels)}")
    if content.related_storylines:
        labels = sorted(
            _relationship_text(reference)
            for reference in content.related_storylines
        )
        text_parts.append(f"related storylines: {'; '.join(labels)}")
    if content.callback_condition is not None:
        text_parts.append(f"callback: {content.callback_condition}")
    if content.resolution_summary is not None:
        text_parts.append(f"resolution: {content.resolution_summary}")
    if entity_keys:
        text_parts.append(f"entities: {' '.join(entity_keys)}")

    return SearchDocumentProjection(
        kind=MemoryKind.STORYLINE,
        status=content.status.value,
        salience=content.salience,
        entity_keys=entity_keys,
        evidence_version_ids=evidence_version_ids,
        related_item_ids=related_item_ids,
        tags=tags,
        document_text="\n".join(text_parts),
        builder_version=STORYLINE_DOCUMENT_BUILDER_VERSION,
        content_hash=_storyline_content_hash(content),
    )


def _entity_key(subject: StorylineEntityRef) -> str:
    prefix = "roster" if subject.kind == "season_roster" else subject.kind
    return f"{prefix}:{subject.id}"


def _participant_text(subject: StorylineEntityRef) -> str:
    label = subject.display_name or _entity_key(subject)
    return f"{subject.role.value} {label}"


def _evidence_text(reference: EvidenceRef) -> str:
    return f"{reference.role.value} {reference.kind}:{reference.version_id}"


def _relationship_text(reference: RelatedStorylineRef) -> str:
    return f"{reference.role.value} storyline:{reference.item_id}"


def _storyline_content_hash(content: StorylineContent) -> str:
    serialized = _canonical_json(_canonical_storyline_content(content)).encode(
        "utf-8"
    )
    return hashlib.sha256(serialized).hexdigest()


def _canonical_storyline_content(content: StorylineContent) -> dict[str, Any]:
    dumped = cast(dict[str, Any], content.model_dump(mode="json"))
    subjects = cast(list[dict[str, Any]], dumped["subjects"])
    dumped["subjects"] = sorted(subjects, key=_canonical_json)
    evidence = cast(list[dict[str, Any]], dumped["evidence"])
    dumped["evidence"] = sorted(evidence, key=_canonical_json)
    related = cast(list[dict[str, Any]], dumped["related_storylines"])
    dumped["related_storylines"] = sorted(related, key=_canonical_json)
    tags = cast(list[str], dumped["tags"])
    dumped["tags"] = sorted(set(tags))
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
