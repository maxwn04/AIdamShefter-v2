"""Deterministic search-document construction for canonical memory versions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from backend.resources.memory.objects import TypedMemoryVersion


SEARCH_DOCUMENT_BUILDER_VERSION = 1


@dataclass(frozen=True, slots=True)
class SearchDocument:
    """Persistence-ready projection of one immutable canonical version."""

    version_id: UUID
    item_id: UUID
    competition_id: UUID
    kind: str
    status: str | None
    salience: int | None
    competition_season_id: UUID | None
    week: int | None
    entity_keys: tuple[str, ...]
    evidence_version_ids: tuple[UUID, ...]
    related_item_ids: tuple[UUID, ...]
    tags: tuple[str, ...]
    document_text: str
    builder_version: int
    content_hash: str

    def persistence_values(self) -> dict[str, object]:
        """Return the exact mutable mapping accepted by the ORM insert."""

        return {
            "version_id": self.version_id,
            "item_id": self.item_id,
            "competition_id": self.competition_id,
            "kind": self.kind,
            "status": self.status,
            "salience": self.salience,
            "competition_season_id": self.competition_season_id,
            "week": self.week,
            "entity_keys": list(self.entity_keys),
            "evidence_version_ids": list(self.evidence_version_ids),
            "related_item_ids": list(self.related_item_ids),
            "tags": list(self.tags),
            "document_text": self.document_text,
            "builder_version": self.builder_version,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class _DocumentContent:
    status: str | None
    salience: int | None
    entity_keys: tuple[str, ...]
    evidence_version_ids: tuple[UUID, ...]
    related_item_ids: tuple[UUID, ...]
    tags: tuple[str, ...]
    text_parts: tuple[str, ...]


def build_search_document(version: TypedMemoryVersion) -> SearchDocument:
    """Build the sole derived search representation for a typed version."""

    kind = _enum_value(version.kind)
    builder = _BUILDERS.get(kind)
    if builder is None:
        raise ValueError(f"unsupported memory kind: {kind}")

    projected = builder(version)
    return SearchDocument(
        version_id=version.version_id,
        item_id=version.item_id,
        competition_id=version.competition_id,
        kind=kind,
        status=projected.status,
        salience=projected.salience,
        competition_season_id=version.competition_season_id,
        week=version.week,
        entity_keys=projected.entity_keys,
        evidence_version_ids=projected.evidence_version_ids,
        related_item_ids=projected.related_item_ids,
        tags=projected.tags,
        document_text="\n".join(projected.text_parts),
        builder_version=SEARCH_DOCUMENT_BUILDER_VERSION,
        content_hash=_content_hash(
            kind,
            version.content,
            version.context_note_identity,
            version.competition_season_id,
            version.week,
        ),
    )


def _build_storyline(version: TypedMemoryVersion) -> _DocumentContent:
    content = version.content
    entity_keys, entity_labels = _entities(content.subjects)
    evidence_ids = _sorted_uuids(reference.version_id for reference in content.evidence)
    related_ids = _sorted_uuids(
        reference.item_id for reference in content.related_storylines
    )
    tags = _normalized_strings(content.tags)
    return _DocumentContent(
        status=_enum_value(content.status),
        salience=content.salience,
        entity_keys=entity_keys,
        evidence_version_ids=evidence_ids,
        related_item_ids=related_ids,
        tags=tags,
        text_parts=_text_parts(
            content.headline,
            content.summary,
            content.arc_type,
            _enum_value(content.status),
            *tags,
            *entity_labels,
            content.callback_condition,
            content.resolution_summary,
        ),
    )


def _build_fact(version: TypedMemoryVersion) -> _DocumentContent:
    content = version.content
    entity_keys, entity_labels = _entities(content.subjects)
    evidence_ids = _sorted_uuids(content.originating_event_version_ids)
    return _DocumentContent(
        status=_enum_value(content.status),
        salience=None,
        entity_keys=entity_keys,
        evidence_version_ids=evidence_ids,
        related_item_ids=(),
        tags=(),
        text_parts=_text_parts(
            content.claim,
            content.category,
            _enum_value(content.confidence),
            _enum_value(content.status),
            _canonical_json(content.numbers),
            *entity_labels,
        ),
    )


def _build_event(version: TypedMemoryVersion) -> _DocumentContent:
    content = version.content
    entity_keys = _event_entity_keys(content.details)
    return _DocumentContent(
        status=_enum_value(content.status),
        salience=content.salience,
        entity_keys=entity_keys,
        evidence_version_ids=(),
        related_item_ids=(),
        tags=(),
        text_parts=_text_parts(
            content.headline,
            content.summary,
            _enum_value(content.event_type),
            _enum_value(content.confidence),
            _enum_value(content.status),
            _canonical_json(content.details),
            *entity_keys,
        ),
    )


def _build_trigger(version: TypedMemoryVersion) -> _DocumentContent:
    content = version.content
    related_ids = _sorted_uuids(
        item_id
        for item_id in (
            content.target_storyline_item_id,
            content.origin_event_item_id,
        )
        if item_id is not None
    )
    condition_subject = getattr(content.condition, "subject", None)
    entity_keys = tuple(
        sorted(
            {
                key
                for key in (
                    (
                        f"season:{content.target_competition_season_id}"
                        if content.target_competition_season_id is not None
                        else None
                    ),
                    (
                        entity_search_key(condition_subject)
                        if condition_subject is not None
                        else None
                    ),
                )
                if key is not None
            }
        )
    )
    return _DocumentContent(
        status=_enum_value(content.status),
        salience=None,
        entity_keys=entity_keys,
        evidence_version_ids=(),
        related_item_ids=related_ids,
        tags=(),
        text_parts=_text_parts(
            _enum_value(content.trigger_type),
            _enum_value(content.status),
            _enum_value(content.fire_policy),
            content.target_week,
            content.target_at.isoformat() if content.target_at else None,
            _canonical_json(content.condition),
            content.resolution_reason,
        ),
    )


def _build_context_note(version: TypedMemoryVersion) -> _DocumentContent:
    content = version.content
    identity = version.context_note_identity
    if identity is None:
        raise ValueError("context-note version is missing its stable identity")
    tags = _normalized_strings(content.tags)
    entity_keys = tuple(
        key
        for key in (
            (
                f"season:{identity.competition_season_id}"
                if identity.competition_season_id is not None
                else None
            ),
            (
                f"franchise:{identity.franchise_id}"
                if identity.franchise_id is not None
                else None
            ),
        )
        if key is not None
    )
    return _DocumentContent(
        status=_enum_value(content.status),
        salience=None,
        entity_keys=entity_keys,
        evidence_version_ids=(),
        related_item_ids=(),
        tags=tags,
        text_parts=_text_parts(
            content.narrative,
            content.outlook,
            _enum_value(content.status),
            _enum_value(identity.scope),
            identity.note_key,
            *entity_keys,
            *tags,
        ),
    )


_BUILDERS = {
    "storyline": _build_storyline,
    "fact": _build_fact,
    "event": _build_event,
    "trigger": _build_trigger,
    "context_note": _build_context_note,
}


def _entities(references: Sequence[Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    keys = tuple(sorted({entity_search_key(reference) for reference in references}))
    labels = tuple(
        reference.display_name or entity_search_key(reference)
        for reference in references
    )
    return keys, labels


def entity_search_key(reference: Any) -> str:
    """Return the stable projection key shared by indexing and query filters."""

    kind = _enum_value(reference.kind)
    return f"{_entity_prefix(kind)}:{reference.id}"


def _event_entity_keys(details: Any) -> tuple[str, ...]:
    values = details.model_dump(mode="python")
    keys: set[str] = set()
    _collect_event_entity_keys(values, keys)
    return tuple(sorted(keys))


def _collect_event_entity_keys(value: object, keys: set[str]) -> None:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for item in value:
            _collect_event_entity_keys(item, keys)
        return
    if not isinstance(value, dict):
        return

    kind = value.get("kind")
    entity_id = value.get("id")
    if kind in {"franchise", "player", "season_roster", "sleeper_user"} and entity_id:
        keys.add(_entity_key_from_parts(str(kind), entity_id))

    field_prefixes = {
        "franchise_id": "franchise",
        "sender_franchise_id": "franchise",
        "receiver_franchise_id": "franchise",
        "winner_franchise_id": "franchise",
        "loser_franchise_id": "franchise",
        "season_roster_id": "roster",
        "original_season_roster_id": "roster",
        "player_id": "player",
        "added_player_id": "player",
        "dropped_player_id": "player",
        "sleeper_player_id": "player",
        "sleeper_user_id": "user",
    }
    for field, nested in value.items():
        prefix = field_prefixes.get(field)
        if prefix is not None and nested is not None:
            keys.add(f"{prefix}:{nested}")
        else:
            _collect_event_entity_keys(nested, keys)


def _entity_key_from_parts(kind: str, entity_id: object) -> str:
    return f"{_entity_prefix(kind)}:{entity_id}"


def _entity_prefix(kind: str) -> str:
    return {
        "season_roster": "roster",
        "sleeper_user": "user",
        "competition_season": "season",
    }.get(kind, kind)


def _content_hash(
    kind: str,
    content: Any,
    identity: Any | None,
    competition_season_id: UUID | None,
    week: int | None,
) -> str:
    payload = {
        "kind": kind,
        "content": content.model_dump(mode="json"),
        "context_note_identity": (
            identity.model_dump(mode="json") if identity is not None else None
        ),
        "competition_season_id": (
            str(competition_season_id)
            if competition_season_id is not None
            else None
        ),
        "week": week,
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, Mapping):
        value = {key: _json_compatible(item) for key, item in value.items()}
    elif isinstance(value, (list, tuple)):
        value = [_json_compatible(item) for item in value]
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _json_compatible(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def _text_parts(*values: object | None) -> tuple[str, ...]:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        normalized = " ".join(str(value).split())
        if normalized:
            parts.append(normalized)
    return tuple(parts)


def _normalized_strings(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({" ".join(value.split()) for value in values if value.strip()}))


def _sorted_uuids(values: Any) -> tuple[UUID, ...]:
    return tuple(sorted(set(values), key=str))


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))
