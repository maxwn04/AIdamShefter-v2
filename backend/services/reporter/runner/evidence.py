"""Run-local executed evidence contract; durable execution identity stays private."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import JsonValue

EVIDENCE_VERSION = "1"
EvidenceOutcome = Literal["found", "partial", "not_found", "unavailable"]


@dataclass(frozen=True)
class EvidenceRecord:
    """One selected source object, never a model-authored assertion.

    Fields retain source keys and typed values. Paths are JSON pointers into the
    private raw response. Subject and period are inherited only within that
    source object's nesting. Completeness refers to population, not truth.
    """

    ref: str
    source: str
    tool: str
    outcome: EvidenceOutcome
    subject: str | None = None
    subject_id: str | None = None
    season: int | None = None
    week_from: int | None = None
    week_to: int | None = None
    perspective: str | None = None
    temporal_kind: Literal["interval", "observation", "unknown"] = "interval"
    fields: dict[str, JsonValue] = field(default_factory=dict)
    field_paths: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    complete: bool = False
    population: str | None = None
    limitations: tuple[str, ...] = ()


class EvidenceReader(Protocol):
    def resolve(self, ref: str) -> EvidenceRecord | None: ...

    def records_for(self, source: str) -> tuple[EvidenceRecord, ...]: ...

    def records_for_tool(self, tool: str) -> tuple[EvidenceRecord, ...]: ...


class EvidenceCatalog:
    """Immutable registrations with defensive reads, usable without a recorder."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}
        self._sources: dict[str, tuple[EvidenceRecord, ...]] = {}

    def register(self, source: str, records: tuple[EvidenceRecord, ...]) -> None:
        if source in self._sources:
            raise ValueError(f"Evidence invocation already registered: {source}")
        if any(record.source != source for record in records):
            raise ValueError("Evidence records must belong to their invocation")
        refs = [record.ref for record in records]
        if len(set(refs)) != len(refs) or set(refs) & self._records.keys():
            raise ValueError("Evidence references must be unique")
        stored = deepcopy(records)
        self._sources[source] = stored
        self._records.update((record.ref, record) for record in stored)

    def resolve(self, ref: str) -> EvidenceRecord | None:
        return deepcopy(self._records.get(ref))

    def records_for(self, source: str) -> tuple[EvidenceRecord, ...]:
        return deepcopy(self._sources.get(source, ()))

    def records_for_tool(self, tool: str) -> tuple[EvidenceRecord, ...]:
        """Inspect executed evidence, including sources without accepted facts."""
        return deepcopy(tuple(record for record in self._records.values() if record.tool == tool))
