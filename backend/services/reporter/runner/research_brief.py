"""Typed, runtime-owned research brief state and deterministic projection."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


RESEARCH_BRIEF_PATH = "research_brief.md"
BRIEF_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
_BRIEF_ID_RE = re.compile(BRIEF_ID_PATTERN)


class ResearchBriefError(Exception):
    """Typed brief mutation failure suitable for model-facing translation."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.details}


class BriefContext(BaseModel):
    """Immutable request and league context resolved before the run."""

    model_config = ConfigDict(frozen=True)

    league_name: str = ""
    league_id: str = ""
    week_start: int = 0
    week_end: int = 0
    length_target: int = Field(default=1000, ge=1)
    evidence_policy: str = "standard"
    focus_hints: tuple[str, ...] = ()
    focus_teams: tuple[str, ...] = ()
    avoid_topics: tuple[str, ...] = ()
    custom_instructions: str = ""


class BriefStyle(BaseModel):
    """Immutable style resolved from ``ReportConfig``."""

    model_config = ConfigDict(frozen=True)

    voice: str = "sports columnist"
    snark_level: int = Field(default=1, ge=0, le=3)
    hype_level: int = Field(default=1, ge=0, le=3)
    seriousness: int = Field(default=1, ge=0, le=3)
    profanity_policy: str = "none"


class BriefBias(BaseModel):
    """Immutable framing preferences resolved from ``ReportConfig``."""

    model_config = ConfigDict(frozen=True)

    favored_teams: tuple[str, ...] = ()
    disfavored_teams: tuple[str, ...] = ()
    intensity: int = Field(default=0, ge=0, le=3)


class ClaimBinding(BaseModel):
    """A selected value from executed evidence, not a model-written citation."""

    model_config = ConfigDict(extra="forbid")
    ref: str = Field(min_length=1)
    field: str = Field(min_length=1)
    value: JsonValue
    subject: str | None
    season: int | None
    week_from: int | None
    week_to: int | None
    perspective: str | None = None


class BriefFact(BaseModel):
    id: str = Field(pattern=BRIEF_ID_PATTERN)
    claim_text: str
    data_refs: tuple[str, ...]
    numbers: dict[str, JsonValue] = Field(default_factory=dict)
    category: str = "general"
    bindings: tuple[ClaimBinding, ...] = ()
    support_status: Literal["legacy_unchecked", "traceable"] = "legacy_unchecked"
    support_diagnostics: tuple[str, ...] = ()
    superlative_direction: Literal["min", "max"] | None = None
    superlative_unique: bool = False
    revision_at_set: int = Field(ge=1)

    @field_validator("id", "claim_text", "category")
    @classmethod
    def _validate_nonblank(cls, value: str) -> str:
        return _trimmed_nonblank(value)

    @field_validator("data_refs", mode="before")
    @classmethod
    def _validate_data_refs(cls, value: Iterable[str]) -> tuple[str, ...]:
        refs = _unique_nonblank(value)
        if not refs:
            raise ValueError("data_refs must contain at least one reference")
        return refs


class BriefMemoryCallback(BaseModel):
    id: str = Field(pattern=BRIEF_ID_PATTERN)
    callback_type: str
    claim_text: str
    old_event_fact_id: str = Field(pattern=BRIEF_ID_PATTERN)
    current_event_fact_id: str = Field(pattern=BRIEF_ID_PATTERN)
    why_now: str
    interestingness_reason: str = ""
    memory_refs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    revision_at_set: int = Field(ge=1)

    @field_validator(
        "id",
        "callback_type",
        "claim_text",
        "old_event_fact_id",
        "current_event_fact_id",
        "why_now",
    )
    @classmethod
    def _validate_nonblank(cls, value: str) -> str:
        return _trimmed_nonblank(value)

    @field_validator("interestingness_reason")
    @classmethod
    def _validate_optional_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("memory_refs", "tags", mode="before")
    @classmethod
    def _validate_lists(cls, value: Iterable[str]) -> tuple[str, ...]:
        return _unique_nonblank(value)


class BriefStoryline(BaseModel):
    id: str = Field(pattern=BRIEF_ID_PATTERN)
    headline: str
    summary: str
    supporting_fact_ids: tuple[str, ...]
    priority: int = Field(default=2, ge=1, le=5)
    tags: tuple[str, ...] = ()
    revision_at_set: int = Field(ge=1)

    @field_validator("id", "headline", "summary")
    @classmethod
    def _validate_nonblank(cls, value: str) -> str:
        return _trimmed_nonblank(value)

    @field_validator("supporting_fact_ids", mode="before")
    @classmethod
    def _validate_fact_ids(cls, value: Iterable[str]) -> tuple[str, ...]:
        ids = _unique_ids(value)
        if not ids:
            raise ValueError("supporting_fact_ids must contain at least one fact id")
        return ids

    @field_validator("tags", mode="before")
    @classmethod
    def _validate_tags(cls, value: Iterable[str]) -> tuple[str, ...]:
        return _unique_nonblank(value)


class BriefOutlineSection(BaseModel):
    title: str
    bullet_points: tuple[str, ...] = ()
    required_fact_ids: tuple[str, ...] = ()
    storyline_ids: tuple[str, ...] = ()

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _trimmed_nonblank(value)

    @field_validator("bullet_points", mode="before")
    @classmethod
    def _validate_bullets(cls, value: Iterable[str]) -> tuple[str, ...]:
        return _unique_nonblank(value)

    @field_validator("required_fact_ids", "storyline_ids", mode="before")
    @classmethod
    def _validate_ids(cls, value: Iterable[str]) -> tuple[str, ...]:
        return _unique_ids(value)


class BriefOutline(BaseModel):
    sections: tuple[BriefOutlineSection, ...] = ()
    revision_at_set: int = Field(default=0, ge=0)


class BriefReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    submission_allowed: bool
    fact_count: int
    callback_count: int
    storyline_count: int
    outline_section_count: int
    stale_callback_ids: tuple[str, ...] = ()
    stale_storyline_ids: tuple[str, ...] = ()
    outline_stale: bool = False
    warnings: tuple[str, ...] = ()


class ResearchBrief(BaseModel):
    revision: int = Field(default=0, ge=0)
    context: BriefContext = Field(default_factory=BriefContext)
    style: BriefStyle = Field(default_factory=BriefStyle)
    bias: BriefBias = Field(default_factory=BriefBias)
    facts: tuple[BriefFact, ...] = ()
    memory_callbacks: tuple[BriefMemoryCallback, ...] = ()
    storylines: tuple[BriefStoryline, ...] = ()
    outline: BriefOutline = Field(default_factory=BriefOutline)

    @model_validator(mode="after")
    def _validate_references(self) -> ResearchBrief:
        fact_ids = [item.id for item in self.facts]
        callback_ids = [item.id for item in self.memory_callbacks]
        storyline_ids = [item.id for item in self.storylines]
        for label, ids in (
            ("fact", fact_ids),
            ("callback", callback_ids),
            ("storyline", storyline_ids),
        ):
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} ids must be unique")
        known_facts = set(fact_ids)
        known_storylines = set(storyline_ids)
        for callback in self.memory_callbacks:
            if {
                callback.old_event_fact_id,
                callback.current_event_fact_id,
            } - known_facts:
                raise ValueError("memory callback references unknown facts")
        for storyline in self.storylines:
            if set(storyline.supporting_fact_ids) - known_facts:
                raise ValueError("storyline references unknown facts")
        for section in self.outline.sections:
            if set(section.required_fact_ids) - known_facts:
                raise ValueError("outline references unknown facts")
            if set(section.storyline_ids) - known_storylines:
                raise ValueError("outline references unknown storylines")
        revision_values = [
            *(item.revision_at_set for item in self.facts),
            *(item.revision_at_set for item in self.memory_callbacks),
            *(item.revision_at_set for item in self.storylines),
        ]
        if self.outline.sections:
            revision_values.append(self.outline.revision_at_set)
        if any(value > self.revision for value in revision_values):
            raise ValueError("item revision cannot exceed brief revision")
        return self

    def get_fact(self, fact_id: str) -> BriefFact | None:
        return next((item for item in self.facts if item.id == fact_id), None)

    def get_callback(self, callback_id: str) -> BriefMemoryCallback | None:
        return next(
            (item for item in self.memory_callbacks if item.id == callback_id),
            None,
        )

    def get_storyline(self, storyline_id: str) -> BriefStoryline | None:
        return next(
            (item for item in self.storylines if item.id == storyline_id),
            None,
        )

    def readiness(self) -> BriefReadiness:
        facts = {item.id: item for item in self.facts}
        storylines = {item.id: item for item in self.storylines}
        stale_callbacks = tuple(
            item.id
            for item in self.memory_callbacks
            if facts[item.old_event_fact_id].revision_at_set > item.revision_at_set
            or facts[item.current_event_fact_id].revision_at_set > item.revision_at_set
        )
        stale_storylines = tuple(
            item.id
            for item in self.storylines
            if any(
                facts[fact_id].revision_at_set > item.revision_at_set
                for fact_id in item.supporting_fact_ids
            )
        )
        outline_stale = bool(
            self.outline.sections
            and (
                any(
                    facts[fact_id].revision_at_set > self.outline.revision_at_set
                    for section in self.outline.sections
                    for fact_id in section.required_fact_ids
                )
                or any(
                    storylines[storyline_id].revision_at_set
                    > self.outline.revision_at_set
                    or storyline_id in stale_storylines
                    for section in self.outline.sections
                    for storyline_id in section.storyline_ids
                )
            )
        )
        warnings: list[str] = []
        if not any(fact.support_status == "traceable" for fact in self.facts):
            warnings.append("no_traceable_facts")
        if any(fact.support_status == "legacy_unchecked" for fact in self.facts):
            warnings.append("legacy_facts_unchecked")
        if not self.storylines:
            warnings.append("no_storylines")
        if not self.outline.sections:
            warnings.append("no_outline")
        if stale_callbacks:
            warnings.append("stale_callbacks")
        if stale_storylines:
            warnings.append("stale_storylines")
        if outline_stale:
            warnings.append("stale_outline")
        return BriefReadiness(
            submission_allowed=bool(self.facts) and all(
                fact.support_status == "traceable" for fact in self.facts
            ),
            fact_count=len(self.facts),
            callback_count=len(self.memory_callbacks),
            storyline_count=len(self.storylines),
            outline_section_count=len(self.outline.sections),
            stale_callback_ids=stale_callbacks,
            stale_storyline_ids=stale_storylines,
            outline_stale=outline_stale,
            warnings=tuple(warnings),
        )


@dataclass(frozen=True, slots=True)
class BriefMutation:
    base_revision: int
    candidate: ResearchBrief
    changed: bool
    operation: str
    entity_id: str


class ResearchBriefStore(BaseModel):
    """Own one brief and atomically commit rendered candidate mutations."""

    brief: ResearchBrief = Field(default_factory=ResearchBrief)

    def prepare_fact(
        self,
        *,
        id: str,
        claim_text: str,
        data_refs: Iterable[str],
        numbers: dict[str, JsonValue] | None = None,
        category: str = "general",
        bindings: Iterable[ClaimBinding | dict[str, Any]] = (),
        support_status: Literal["legacy_unchecked", "traceable"] = "legacy_unchecked",
        support_diagnostics: Iterable[str] = (),
        superlative_direction: Literal["min", "max"] | None = None,
        superlative_unique: bool = False,
    ) -> BriefMutation:
        revision = self.brief.revision + 1
        fact = BriefFact(
            id=id,
            claim_text=claim_text,
            data_refs=tuple(data_refs),
            numbers=numbers or {},
            category=category,
            bindings=tuple(bindings),
            support_status=support_status,
            support_diagnostics=tuple(support_diagnostics),
            superlative_direction=superlative_direction,
            superlative_unique=superlative_unique,
            revision_at_set=revision,
        )
        existing = self.brief.get_fact(fact.id)
        if existing is not None and _without_revision(existing) == _without_revision(fact):
            return self._no_change("save_fact", fact.id)
        return self._replace(
            "facts",
            fact,
            operation="update_fact" if existing is not None else "save_fact",
        )

    def prepare_memory_callback(
        self,
        *,
        id: str,
        callback_type: str,
        claim_text: str,
        old_event_fact_id: str,
        current_event_fact_id: str,
        why_now: str,
        interestingness_reason: str = "",
        memory_refs: Iterable[str] = (),
        tags: Iterable[str] = (),
    ) -> BriefMutation:
        if old_event_fact_id == current_event_fact_id:
            raise ResearchBriefError(
                "invalid_callback",
                "callback fact ids must identify two different facts",
            )
        self._require_fact_ids((old_event_fact_id, current_event_fact_id))
        revision = self.brief.revision + 1
        callback = BriefMemoryCallback(
            id=id,
            callback_type=callback_type,
            claim_text=claim_text,
            old_event_fact_id=old_event_fact_id,
            current_event_fact_id=current_event_fact_id,
            why_now=why_now,
            interestingness_reason=interestingness_reason,
            memory_refs=tuple(memory_refs),
            tags=tuple(tags),
            revision_at_set=revision,
        )
        existing = self.brief.get_callback(callback.id)
        if existing is not None and _without_revision(existing) == _without_revision(
            callback
        ):
            return self._no_change("save_memory_callback", callback.id)
        return self._replace(
            "memory_callbacks",
            callback,
            operation=(
                "update_memory_callback"
                if existing is not None
                else "save_memory_callback"
            ),
        )

    def prepare_storyline(
        self,
        *,
        id: str,
        headline: str,
        summary: str,
        supporting_fact_ids: Iterable[str],
        priority: int = 2,
        tags: Iterable[str] = (),
    ) -> BriefMutation:
        fact_ids = tuple(supporting_fact_ids)
        self._require_fact_ids(fact_ids)
        revision = self.brief.revision + 1
        storyline = BriefStoryline(
            id=id,
            headline=headline,
            summary=summary,
            supporting_fact_ids=fact_ids,
            priority=priority,
            tags=tuple(tags),
            revision_at_set=revision,
        )
        existing = self.brief.get_storyline(storyline.id)
        if existing is not None and _without_revision(existing) == _without_revision(
            storyline
        ):
            return self._no_change("save_storyline", storyline.id)
        return self._replace(
            "storylines",
            storyline,
            operation=(
                "update_storyline" if existing is not None else "save_storyline"
            ),
        )

    def prepare_outline(
        self,
        *,
        sections: Iterable[BriefOutlineSection | dict[str, Any]],
    ) -> BriefMutation:
        parsed = tuple(
            item
            if isinstance(item, BriefOutlineSection)
            else BriefOutlineSection.model_validate(item)
            for item in sections
        )
        self._require_fact_ids(
            fact_id for section in parsed for fact_id in section.required_fact_ids
        )
        self._require_storyline_ids(
            storyline_id
            for section in parsed
            for storyline_id in section.storyline_ids
        )
        existing_sections = self.brief.outline.sections
        if existing_sections == parsed:
            return self._no_change("set_outline", "outline")
        revision = self.brief.revision + 1
        candidate = self.brief.model_copy(
            update={
                "revision": revision,
                "outline": BriefOutline(
                    sections=parsed,
                    revision_at_set=revision,
                ),
            },
            deep=True,
        )
        return BriefMutation(
            base_revision=self.brief.revision,
            candidate=candidate,
            changed=True,
            operation="set_outline",
            entity_id="outline",
        )

    def commit(
        self,
        mutation: BriefMutation,
        persist_projection: Callable[[str], object],
    ) -> ResearchBrief:
        if mutation.base_revision != self.brief.revision:
            raise ResearchBriefError(
                "revision_conflict",
                "brief changed after the mutation was prepared",
                expected_revision=mutation.base_revision,
                current_revision=self.brief.revision,
            )
        if not mutation.changed:
            return self.brief
        content = render_research_brief(mutation.candidate)
        persist_projection(content)
        self.brief = mutation.candidate
        return self.brief

    def _replace(
        self,
        field: str,
        item: BaseModel,
        *,
        operation: str,
    ) -> BriefMutation:
        current = getattr(self.brief, field)
        replaced = _upsert_tuple(current, item)
        candidate = self.brief.model_copy(
            update={
                "revision": self.brief.revision + 1,
                field: replaced,
            },
            deep=True,
        )
        return BriefMutation(
            base_revision=self.brief.revision,
            candidate=candidate,
            changed=True,
            operation=operation,
            entity_id=str(getattr(item, "id")),
        )

    def _no_change(self, operation: str, entity_id: str) -> BriefMutation:
        return BriefMutation(
            base_revision=self.brief.revision,
            candidate=self.brief,
            changed=False,
            operation=operation,
            entity_id=entity_id,
        )

    def _require_fact_ids(self, fact_ids: Iterable[str]) -> None:
        known = {item.id for item in self.brief.facts}
        missing = tuple(dict.fromkeys(item for item in fact_ids if item not in known))
        if missing:
            raise ResearchBriefError(
                "unknown_fact_ids",
                "brief references unknown fact ids",
                missing_fact_ids=list(missing),
            )

    def _require_storyline_ids(self, storyline_ids: Iterable[str]) -> None:
        known = {item.id for item in self.brief.storylines}
        missing = tuple(
            dict.fromkeys(item for item in storyline_ids if item not in known)
        )
        if missing:
            raise ResearchBriefError(
                "unknown_storyline_ids",
                "outline references unknown storyline ids",
                missing_storyline_ids=list(missing),
            )


def render_research_brief(brief: ResearchBrief) -> str:
    """Render one brief deterministically without creating authoritative prose."""
    readiness = brief.readiness()
    context = brief.context
    style = brief.style
    bias = brief.bias
    lines = [
        "# Research Brief",
        "",
        f"Revision: {brief.revision}",
        "",
        "## Context",
        "",
        f"- League: {context.league_name or '(unknown)'}",
        f"- League ID: {context.league_id or '(unknown)'}",
        f"- Coverage weeks: {context.week_start}-{context.week_end}",
        f"- Target length: about {context.length_target} words",
        f"- Evidence policy: {context.evidence_policy}",
        f"- Focus hints: {_list_value(context.focus_hints)}",
        f"- Focus teams: {_list_value(context.focus_teams)}",
        f"- Avoid topics: {_list_value(context.avoid_topics)}",
        f"- Custom instructions: {context.custom_instructions or '(none)'}",
        "",
        "## Style and Bias",
        "",
        f"- Voice: {style.voice}",
        f"- Snark level: {style.snark_level}",
        f"- Hype level: {style.hype_level}",
        f"- Seriousness: {style.seriousness}",
        f"- Profanity policy: {style.profanity_policy}",
        f"- Favored teams: {_list_value(bias.favored_teams)}",
        f"- Disfavored teams: {_list_value(bias.disfavored_teams)}",
        f"- Bias intensity: {bias.intensity}",
        "- Bias rule: framing only; never change facts.",
        "",
        "## Evidence-bound Facts",
        "",
    ]
    if brief.facts:
        for fact in brief.facts:
            lines.extend(
                [
                    f"### {fact.id}",
                    "",
                    f"- Claim: {fact.claim_text}",
                    f"- Category: {fact.category}",
                    f"- Superlative direction/unique: {fact.superlative_direction or '(none)'}/{fact.superlative_unique}",
                    f"- Support: {fact.support_status} (traceability is not prose entailment)",
                    f"- Bindings: {json.dumps([binding.model_dump() for binding in fact.bindings], sort_keys=True)}",
                    f"- Diagnostics: {_list_value(fact.support_diagnostics)}",
                    f"- Data refs: {_list_value(fact.data_refs)}",
                    f"- Numbers: {json.dumps(fact.numbers, sort_keys=True)}",
                    f"- Set at revision: {fact.revision_at_set}",
                    "",
                ]
            )
    else:
        lines.extend(["(none)", ""])

    lines.extend(["## Verified Callbacks", ""])
    if brief.memory_callbacks:
        for callback in brief.memory_callbacks:
            lines.extend(
                [
                    f"### {callback.id}",
                    "",
                    f"- Type: {callback.callback_type}",
                    f"- Claim: {callback.claim_text}",
                    f"- Old fact: {callback.old_event_fact_id}",
                    f"- Current fact: {callback.current_event_fact_id}",
                    f"- Why now: {callback.why_now}",
                    f"- Interestingness: {callback.interestingness_reason or '(none)'}",
                    f"- Memory refs: {_list_value(callback.memory_refs)}",
                    f"- Tags: {_list_value(callback.tags)}",
                    f"- Set at revision: {callback.revision_at_set}",
                    "",
                ]
            )
    else:
        lines.extend(["(none)", ""])

    lines.extend(["## Storylines", ""])
    if brief.storylines:
        for storyline in brief.storylines:
            lines.extend(
                [
                    f"### {storyline.id}: {storyline.headline}",
                    "",
                    storyline.summary,
                    "",
                    f"- Supporting facts: {_list_value(storyline.supporting_fact_ids)}",
                    f"- Priority: {storyline.priority}",
                    f"- Tags: {_list_value(storyline.tags)}",
                    f"- Set at revision: {storyline.revision_at_set}",
                    "",
                ]
            )
    else:
        lines.extend(["(none)", ""])

    lines.extend(["## Outline", ""])
    if brief.outline.sections:
        for section in brief.outline.sections:
            lines.extend([f"### {section.title}", ""])
            lines.extend(f"- {bullet}" for bullet in section.bullet_points)
            lines.extend(
                [
                    f"- Required facts: {_list_value(section.required_fact_ids)}",
                    f"- Storylines: {_list_value(section.storyline_ids)}",
                    "",
                ]
            )
        lines.append(f"Outline set at revision: {brief.outline.revision_at_set}")
        lines.append("")
    else:
        lines.extend(["(none)", ""])

    lines.extend(
        [
            "## Readiness",
            "",
            f"- Submission allowed: {'yes' if readiness.submission_allowed else 'no'}",
            f"- Stale callbacks: {_list_value(readiness.stale_callback_ids)}",
            f"- Stale storylines: {_list_value(readiness.stale_storyline_ids)}",
            f"- Outline stale: {'yes' if readiness.outline_stale else 'no'}",
            f"- Warnings: {_list_value(readiness.warnings)}",
            "",
        ]
    )
    return "\n".join(lines)


def _upsert_tuple(items: tuple[Any, ...], item: Any) -> tuple[Any, ...]:
    for index, existing in enumerate(items):
        if existing.id == item.id:
            return (*items[:index], item, *items[index + 1 :])
    return (*items, item)


def _without_revision(item: BaseModel) -> dict[str, Any]:
    return item.model_dump(exclude={"revision_at_set"})


def _trimmed_nonblank(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("value must be a non-empty string")
    if value != value.strip():
        raise ValueError("value cannot have surrounding whitespace")
    return value


def _unique_nonblank(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(_trimmed_nonblank(value) for value in values)
    return tuple(dict.fromkeys(normalized))


def _unique_ids(values: Iterable[str]) -> tuple[str, ...]:
    ids = _unique_nonblank(values)
    invalid = [value for value in ids if _BRIEF_ID_RE.fullmatch(value) is None]
    if invalid:
        raise ValueError(f"invalid brief ids: {', '.join(invalid)}")
    return ids


def _list_value(values: Iterable[str]) -> str:
    items = tuple(values)
    return ", ".join(items) if items else "(none)"


__all__ = [
    "BRIEF_ID_PATTERN",
    "RESEARCH_BRIEF_PATH",
    "BriefBias",
    "BriefContext",
    "BriefFact",
    "BriefMemoryCallback",
    "BriefMutation",
    "BriefOutline",
    "BriefOutlineSection",
    "BriefReadiness",
    "BriefStoryline",
    "BriefStyle",
    "ResearchBrief",
    "ResearchBriefError",
    "ResearchBriefStore",
    "render_research_brief",
]
