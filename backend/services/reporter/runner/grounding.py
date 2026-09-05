"""Small deterministic checks of selected evidence; never a prose truth engine."""

from __future__ import annotations

from math import isclose
from typing import Any

from pydantic import JsonValue

from backend.services.reporter.runner.evidence import EvidenceReader, EvidenceRecord
from backend.services.reporter.runner.research_brief import (
    BriefFact, ClaimBinding, ResearchBriefError,
)


def _reject(message: str, **details: Any) -> None:
    raise ResearchBriefError("unsupported_fact", message, **details)


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


def resolve_bindings(
    selections: list[dict[str, Any]], evidence: EvidenceReader,
) -> tuple[ClaimBinding, ...]:
    """Hydrate source dimensions, checking supplied legacy dimensions if present."""
    bindings: dict[tuple[str, str], ClaimBinding] = {}
    dimensions = ("subject", "season", "week_from", "week_to", "perspective")
    for selection in selections:
        binding = ClaimBinding.model_validate(selection)
        record = evidence.resolve(binding.ref)
        if record is None or record.outcome not in {"found", "partial"}:
            _reject(
                f"Reference {binding.ref} does not resolve to available executed evidence.",
                ref=binding.ref,
                outcome=record.outcome if record else "unknown_reference",
                repair={"action": "select_available_evidence", "instruction": "Select a ref returned by an executed data tool with outcome found or partial. Unavailable evidence cannot support this fact; narrow the claim or research the missing support."},
            )
        if binding.field not in record.fields:
            _reject(
                f"Binding {binding.ref}.{binding.field} does not match the executed value.",
                ref=binding.ref, field=binding.field,
                available_fields=list(record.fields)[:12],
                fields_truncated=len(record.fields) > 12,
                repair={"action": "select_executed_field", "instruction": "Select an exact field from this record and its executed value. The bounded field list describes only this record; use read_evidence for further source detail."},
            )
        if not _equal(record.fields[binding.field], binding.value):
            _reject(
                f"Binding {binding.ref}.{binding.field} does not match the executed value.",
                ref=binding.ref, field=binding.field,
                expected_value=record.fields[binding.field],
                repair={"action": "match_executed_value", "instruction": "Use the exact executed value and revise the claim to match its support, or select different executed evidence. This rejection saved no fact."},
            )
        for dimension in dimensions:
            if dimension in binding.model_fields_set and getattr(binding, dimension) != getattr(record, dimension):
                _reject(
                    f"Binding {binding.ref} has the wrong {dimension}.",
                    ref=binding.ref, dimension=dimension,
                    expected_value=getattr(record, dimension),
                    repair={"action": "use_compact_binding", "instruction": "Send only ref, field, value. The runtime derives source subject, season, period and perspective; ensure the claim describes that source."},
                )
        bindings[(binding.ref, binding.field)] = binding.model_copy(update={
            dimension: getattr(record, dimension) for dimension in dimensions
        })
    return tuple(bindings.values())


def binding_numbers(bindings: tuple[ClaimBinding, ...]) -> dict[str, JsonValue]:
    """Derive an unambiguous numeric summary from the authoritative selections."""
    numeric = [binding for binding in bindings if isinstance(binding.value, (int, float)) and not isinstance(binding.value, bool)]
    repeated = {binding.field for binding in numeric if sum(other.field == binding.field for other in numeric) > 1}
    return {
        f"{binding.ref}.{binding.field}" if binding.field in repeated else binding.field: binding.value
        for binding in numeric
    }


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
        if not any(key in {binding.field, f"{binding.ref}.{binding.field}"} and _equal(binding.value, value) for binding in fact.bindings):
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
        if source.temporal_kind == "unknown":
            _reject("Unknown temporal semantics cannot support a structured before/after comparison; narrow the claim.")
        observation = source.temporal_kind == "observation"
        if observation and first.field != "roster_members":
            _reject("Only listed roster_members observations support point-state comparisons; narrow other observation claims.")
        identity = getattr(source, "subject_id", None) or source.subject
        periods: list[tuple[int, int, int]] = []
        for binding in fact.bindings:
            record = records[binding.ref]
            if record.temporal_kind != source.temporal_kind:
                _reject("Before/after comparisons cannot mix interval aggregates and point observations.")
            if observation and (record.subject_id is None or source.subject_id is None):
                _reject("Roster observation comparisons require durable source franchise identity.")
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
            if observation:
                if record.tool != "roster_at_cutoff" or not isinstance(binding.value, list) or not all(isinstance(member, str) for member in binding.value):
                    _reject("Roster observation comparisons require source-listed membership from roster_at_cutoff.")
                if binding.week_to is None:
                    _reject("Roster observations require explicit cutoff weeks.")
                periods.append((binding.season, binding.week_to, binding.week_to))
                continue
            if (binding.week_from is None) != (first.week_from is None) or (binding.week_to is None) != (first.week_to is None):
                _reject("Before/after comparisons require comparable period specificity.")
            if binding.season != first.season and (binding.week_from, binding.week_to) != (first.week_from, first.week_to):
                _reject("Cross-season comparisons require equivalent coverage windows; narrow mismatched periods.")
            periods.append((binding.season, binding.week_from or 0, binding.week_to or 0))
        if len(set(periods)) != len(periods) or periods != sorted(periods):
            _reject("Comparison bindings must identify distinct periods in before/after order.")
        if observation:
            diagnostics.add("DIAGNOSTIC: listed roster membership at ordered cutoffs does not establish acquisition timing or method, or completeness beyond the source observations.")
    elif fact.category == "superlative":
        if fact.superlative_direction is None:
            _reject("Superlatives require an explicit min/max direction.")
        metrics = fact.bindings
        if fact.superlative_binding is not None:
            metrics = tuple(binding for binding in fact.bindings if (
                binding.ref == fact.superlative_binding.ref
                and binding.field == fact.superlative_binding.field
            ))
            if not metrics:
                _reject("The asserted superlative metric must be selected in bindings.")
        for binding in metrics:
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
