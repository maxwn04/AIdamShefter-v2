"""Small deterministic checks of selected evidence; never a prose truth engine."""

from __future__ import annotations

from math import isclose

from pydantic import JsonValue

from backend.services.reporter.runner.evidence import EvidenceReader, EvidenceRecord
from backend.services.reporter.runner.research_brief import BriefFact, ResearchBriefError


def _reject(message: str) -> None:
    raise ResearchBriefError("unsupported_fact", message)


def _equal(actual: JsonValue, expected: JsonValue) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return isclose(actual, expected, rel_tol=0, abs_tol=1e-9)
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _equal(value, expected[key]) for key, value in actual.items()
        )
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _equal(left, right) for left, right in zip(actual, expected, strict=True)
        )
    return type(actual) is type(expected) and actual == expected


def validate_fact(fact: BriefFact, evidence: EvidenceReader) -> tuple[str, ...]:
    """Reject unsupported structured assertions; return honest semantic caveats."""
    if not fact.bindings:
        _reject("New facts require field bindings to executed evidence; plain legacy refs are unchecked.")
    records: dict[str, EvidenceRecord] = {}
    for ref in fact.data_refs:
        record = evidence.resolve(ref)
        if record is None or record.outcome not in {"found", "partial"}:
            _reject(f"Reference {ref} does not resolve to available executed evidence.")
        records[ref] = record
    diagnostics = {"DIAGNOSTIC: field traceability does not establish that claim_text or article prose is entailed."}
    for binding in fact.bindings:
        record = records.get(binding.ref)
        if record is None:
            _reject(f"Binding {binding.ref} must be listed in data_refs.")
        if binding.field not in record.fields or not _equal(record.fields[binding.field], binding.value):
            _reject(f"Binding {binding.ref}.{binding.field} does not match the executed value.")
        for dimension in ("subject", "season", "week_from", "week_to", "perspective"):
            if getattr(binding, dimension) != getattr(record, dimension):
                _reject(f"Binding {binding.ref} has the wrong {dimension}.")
        diagnostics.update(f"LIMITATION: {limitation}" for limitation in record.limitations)
        if record.outcome == "partial":
            diagnostics.add("LIMITATION: partial source evidence; do not imply complete coverage.")
    if set(records) != {binding.ref for binding in fact.bindings}:
        _reject("Every data_ref must supply at least one selected binding.")
    for key, value in fact.numbers.items():
        if not any(binding.field == key and _equal(binding.value, value) for binding in fact.bindings):
            _reject(f"Number {key} must match a selected field binding.")

    if fact.category == "transaction":
        if not any(
            (
                record.perspective in {"sent", "received"}
                and binding.field in {"player_name", "pick_season", "pick_round", "pick_original_team_name"}
            ) or (binding.field == "net_draft_picks" and "transaction" in record.tool)
            for binding in fact.bindings
            for record in (records[binding.ref],)
        ):
            _reject("Transactions require a selected sent/received asset field or source net_draft_picks count.")
        diagnostics.add("DIAGNOSTIC: preserve each asset's sent/received direction; strategic flexibility is interpretation.")
    elif fact.category == "comparison":
        if len(fact.bindings) < 2:
            _reject("Before/after comparisons require at least two comparable bindings.")
        first = fact.bindings[0]
        source = records[first.ref]
        identity = getattr(source, "subject_id", None) or source.subject
        periods: list[tuple[int, int, int]] = []
        for binding in fact.bindings:
            record = records[binding.ref]
            other_identity = getattr(record, "subject_id", None) or record.subject
            if record.season != source.season and (
                source.subject_id is None or record.subject_id is None
            ):
                _reject("Cross-season comparisons require durable source franchise identity, not matching display names.")
            if identity is None or identity != other_identity:
                _reject("Before/after comparisons require the same supported franchise identity.")
            if binding.field != first.field or record.units.get(binding.field) != source.units.get(first.field):
                _reject("Before/after comparisons require the same field and units.")
            if binding.perspective != first.perspective or binding.season is None:
                _reject("Before/after comparisons require comparable perspectives and known seasons.")
            if (binding.week_from is None) != (first.week_from is None) or (binding.week_to is None) != (first.week_to is None):
                _reject("Before/after comparisons require comparable period specificity.")
            if binding.season != first.season and (binding.week_from, binding.week_to) != (first.week_from, first.week_to):
                _reject("Cross-season comparisons require equivalent coverage windows; narrow mismatched periods.")
            periods.append((binding.season, binding.week_from or 0, binding.week_to or 0))
        if len(set(periods)) != len(periods) or periods != sorted(periods):
            _reject("Comparison bindings must identify distinct periods in before/after order.")
    elif fact.category == "superlative":
        if fact.superlative_direction is None:
            _reject("Superlatives require an explicit min/max direction.")
        for binding in fact.bindings:
            record = records[binding.ref]
            if not record.complete or not record.population:
                _reject("Superlatives require an explicitly complete comparison population.")
            population = [
                item for item in evidence.records_for(record.source)
                if item.population == record.population and binding.field in item.fields
            ]
            if not population or any(
                not item.complete or item.outcome != "found"
                or (item.season, item.week_from, item.week_to, item.perspective, item.units.get(binding.field))
                != (record.season, record.week_from, record.week_to, record.perspective, record.units.get(binding.field))
                for item in population
            ):
                _reject("Superlative population is incomplete or mixes comparison scopes.")
            values = [item.fields[binding.field] for item in population]
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
                _reject("This superlative field lacks comparable numeric values; use a narrower claim.")
            extreme = min(values) if fact.superlative_direction == "min" else max(values)
            if not _equal(binding.value, extreme):
                _reject("Selected subject is not an extreme of the complete source population.")
            if fact.superlative_unique and sum(_equal(value, extreme) for value in values) != 1:
                _reject("Selected subject is tied; the complete population does not support a unique superlative.")
        diagnostics.add("DIAGNOSTIC: a structured extreme does not establish the scope or wording of prose.")
    elif fact.category == "championship":
        if not any(
            "playoff" in record.tool
            and record.fields.get("bracket_type") == "winners"
            and binding.field == "is_champion"
            and binding.value is True
            for binding in fact.bindings
            for record in (records[binding.ref],)
        ):
            _reject("Championship claims require explicit championship outcome evidence from playoffs.")
    return tuple(sorted(diagnostics))
