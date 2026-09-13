"""Advisory draft context from executed bracket results, not authored facts."""

from dataclasses import dataclass
import json
import re

from pydantic import JsonValue

from backend.services.reporter.runner.evidence import EvidenceReader


@dataclass(frozen=True)
class BracketReviewCard:
    ref: str
    season: int | None
    week_from: int | None
    week_to: int | None
    fields: dict[str, JsonValue]
    field_paths: dict[str, str]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class BracketReview:
    outcomes: tuple[BracketReviewCard, ...]
    coverage: tuple[BracketReviewCard, ...]
    passages: tuple[str, ...]
    truncated: bool
    instruction: str = (
        "Compare these executed recorded outcomes with the draft, even when a related fact binding failed. "
        "Recorded bracket winner/loser and higher score are different claims. Check the exact bracket, teams, "
        "season and reporting period; do not infer advancement or elimination rules from score comparisons. "
        "Observed round winners are not the complete remaining field; configured playoff size is not its current size. "
        "Unknown or omitted participants remain unknown, including possible byes. These are review leads, "
        "not a prose mismatch verdict or submission gate. Passages are selected by bracket wording, not entailment."
    )


_BRACKET_LANGUAGE = re.compile(r"\b(bracket|playoff|postseason|champion\w*|advanc\w*|eliminat\w*|surviv\w*)\b", re.I)
_OUTCOME_FIELDS = ("bracket_type", "round", "matchup_id", "team_1", "team_2",
                   "recorded_winner", "recorded_loser", "status", "placement")
_COVERAGE_FIELDS = ("configured_playoff_teams", "coverage", "remaining_field_status",
                    "observed_matchup_count", "observed_participants")


def bracket_review(text: str, evidence: EvidenceReader) -> BracketReview | None:
    """Keep the source's visibility/limitations; never infer a missing team or rule."""
    paragraphs = [part for part in re.split(r"\r?\n[ \t]*\r?\n", text)
                  if _BRACKET_LANGUAGE.search(part)]
    if not paragraphs:
        return None
    outcomes: list[BracketReviewCard] = []
    coverage: list[BracketReviewCard] = []
    seen: set[str] = set()
    for record in evidence.records_for_tool("playoff_bracket"):
        if record.outcome not in {"found", "partial"}:
            continue
        fields, paths = dict(record.fields), dict(record.field_paths)
        # Old executed payloads remain reviewable with their original raw paths.
        for name in ("winner", "loser"):
            if name in fields and f"recorded_{name}" not in fields:
                fields[f"recorded_{name}"] = fields[name]
                if name in paths:
                    paths[f"recorded_{name}"] = paths[name]
        is_outcome = "round" in fields and "recorded_winner" in fields
        keys = _OUTCOME_FIELDS if is_outcome else _COVERAGE_FIELDS
        selected = {key: fields[key] for key in keys if key in fields}
        if not selected:
            continue
        signature = json.dumps([record.season, record.week_from, record.week_to, selected, record.limitations], sort_keys=True)
        if signature in seen:
            continue
        seen.add(signature)
        card = BracketReviewCard(record.ref, record.season, record.week_from, record.week_to,
                                 selected, {key: paths[key] for key in selected if key in paths}, record.limitations)
        (outcomes if is_outcome else coverage).append(card)
    if not outcomes and not coverage:
        return None
    excerpts = tuple(paragraph[:2400] for paragraph in paragraphs[:8])
    return BracketReview(tuple(outcomes[:24]), tuple(coverage[:8]), excerpts,
                         len(outcomes) > 24 or len(coverage) > 8 or len(paragraphs) > 8
                         or any(len(paragraph) > 2400 for paragraph in paragraphs[:8]))
