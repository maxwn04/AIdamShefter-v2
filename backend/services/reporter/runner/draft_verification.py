"""Revision-scoped, bounded diagnostics over actual draft text."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from pydantic import JsonValue

from backend.services.reporter.runner.bracket_review import BracketReview, bracket_review
from backend.services.reporter.runner.evidence import EvidenceReader, EvidenceRecord
from backend.services.reporter.runner.grounding import validate_fact
from backend.services.reporter.runner.research_brief import BriefFact, ResearchBrief, ResearchBriefError
from backend.services.reporter.runner.schemas import ArtifactSnapshot


@dataclass(frozen=True)
class DraftDiagnostic:
    code: str
    message: str
    excerpt: str = ""
    fact_id: str | None = None
    severity: str = "DIAGNOSTIC"


@dataclass(frozen=True)
class DirectionalAsset:
    ref: str
    identity: dict[str, JsonValue]
    status: str | None
    occurred_at: str | None
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class DirectionalReviewCard:
    fact_id: str
    source_team: str
    season: int | None
    sent: tuple[DirectionalAsset, ...]
    received: tuple[DirectionalAsset, ...]
    passage_ids: tuple[str, ...]
    truncated: bool


@dataclass(frozen=True)
class DirectionalReviewPassage:
    id: str
    text: str
    truncated: bool


@dataclass(frozen=True)
class DraftVerification:
    path: str
    article_revision: int
    content_hash: str
    brief_revision: int
    diagnostics: tuple[DraftDiagnostic, ...]
    traceability_errors: tuple[str, ...]
    checked_characters: int
    truncated: bool
    directional_review_cards: tuple[DirectionalReviewCard, ...] = ()
    directional_review_passages: tuple[DirectionalReviewPassage, ...] = ()
    bracket_review: BracketReview | None = None

    def is_current(self, artifact: ArtifactSnapshot, brief: ResearchBrief) -> bool:
        return (
            self.path == artifact.path and self.article_revision == artifact.revision
            and self.content_hash == artifact.content_hash and self.brief_revision == brief.revision
        )

    def as_dict(self) -> dict:
        return {
            **asdict(self),
            "status": "TRACEABILITY_ERROR" if self.traceability_errors else "DIAGNOSTIC",
            "submission_blocking": False,
            "scope": "Selected field traceability and bounded draft patterns; not proof of prose entailment.",
            "directional_review_instruction": (
                "Before finalizing, compare who sends and receives every selected asset against the full draft context, "
                "including pronouns and counterparties. Cards come from executed source fields, not saved claim_text. "
                "They list selected movements, not necessarily a complete transaction. Passage retrieval uses literal player names; "
                "empty or matching passages establish neither absence nor entailment. Inspect unmatched assets and truncated context "
                "in the draft/source. Correct reversals; no card is a mismatch verdict or submission gate. "
                "Unknown status does not establish completed movement; occurred_at alone does not establish postgame motive."
            ) if self.directional_review_cards else None,
        }


_DIRECTION = re.compile(r"\b(sent|traded away|gave up|received|acquired|got back)\b", re.I)
_SUPERLATIVE = re.compile(r"\b(longest|highest|lowest|best|worst|most|fewest|first ever|season high)\b", re.I)
_CHAMPIONSHIP = re.compile(r"\b(champion(?:ship)?|won the title|title winner)\b", re.I)
_COMPARISON = re.compile(r"\b(before|after|improved|declined|last season|previous season|year.over.year)\b", re.I)

_ASSET_FIELDS = ("player_name", "pick_season", "pick_round", "pick_original_team_name")


def _directional_reviews(
    selected: list[tuple[BriefFact, EvidenceRecord]], text: str, text_truncated: bool,
) -> tuple[tuple[DirectionalReviewCard, ...], tuple[DirectionalReviewPassage, ...], set[str], bool]:
    """Retrieve context, never infer prose roles. Bound the extra review payload."""
    groups: dict[tuple[str, str, str, int | None], list[EvidenceRecord]] = {}
    for fact, record in selected:
        if not record.subject or record.perspective not in {"sent", "received"}:
            continue
        if not any(binding.ref == record.ref and binding.field in _ASSET_FIELDS for binding in fact.bindings):
            continue
        key = (fact.id, record.source, record.subject, record.season)
        members = groups.setdefault(key, [])
        if not any(member.ref == record.ref for member in members):
            members.append(record)

    paragraphs = [part for part in re.split(r"\r?\n[ \t]*\r?\n", text) if part.strip()]
    cards: list[DirectionalReviewCard] = []
    passages: dict[str, DirectionalReviewPassage] = {}
    covered: set[str] = set()
    truncated = len(groups) > 12
    remaining_characters = 12_000
    for (fact_id, _source, team, season), records in list(groups.items())[:12]:
        card_truncated = len(records) > 12
        records = records[:12]
        names = [record.fields["player_name"].casefold() for record in records
                 if isinstance(record.fields.get("player_name"), str) and record.fields["player_name"]]
        matches = list(dict.fromkeys(paragraph for paragraph in paragraphs
                                     if any(name in paragraph.casefold() for name in names)))
        card_truncated |= len(matches) > 2
        passage_ids: list[str] = []
        for paragraph in matches[:2]:
            passage = passages.get(paragraph)
            if passage is None:
                if len(passages) >= 8 or remaining_characters <= 0:
                    card_truncated = True
                    continue
                excerpt = paragraph[:min(2400, remaining_characters)]
                passage = DirectionalReviewPassage(
                    f"p{len(passages) + 1}", excerpt,
                    len(excerpt) < len(paragraph) or (text_truncated and text.endswith(paragraph)),
                )
                passages[paragraph] = passage
                remaining_characters -= len(excerpt)
            passage_ids.append(passage.id)
            card_truncated |= passage.truncated
            # Suppress generic transaction warnings only for context actually delivered.
            covered.add(passage.text)

        def assets(direction: str) -> tuple[DirectionalAsset, ...]:
            return tuple(DirectionalAsset(
                record.ref,
                {field: record.fields[field] for field in _ASSET_FIELDS if field in record.fields},
                record.fields.get("status") if isinstance(record.fields.get("status"), str) else None,
                record.fields.get("occurred_at") if isinstance(record.fields.get("occurred_at"), str) else None,
                record.limitations,
            ) for record in records if record.perspective == direction)

        cards.append(DirectionalReviewCard(fact_id, team, season, assets("sent"), assets("received"), tuple(passage_ids), card_truncated))
        truncated |= card_truncated
    return tuple(cards), tuple(passages.values()), covered, truncated


def verify_draft(
    artifact: ArtifactSnapshot, brief: ResearchBrief, evidence: EvidenceReader,
) -> DraftVerification:
    """Never calls a model. Ambiguous natural language is deliberately advisory."""
    limit = 30_000
    text = artifact.content[:limit]
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)[:160]
    diagnostics: list[DraftDiagnostic] = []
    errors: list[str] = []
    scanned_records = 0
    selected: list[tuple[BriefFact, EvidenceRecord]] = []
    for fact in brief.facts:
        valid = True
        try:
            validate_fact(fact, evidence)
        except ResearchBriefError as exc:
            errors.append(f"{fact.id}: {exc.message}")
            valid = False
        records = [record for ref in fact.data_refs if (record := evidence.resolve(ref)) is not None]
        for record in records:
            scanned_records += 1
            if scanned_records > 100:
                continue
            if valid:
                selected.append((fact, record))
            relevant = [sentence for sentence in sentences if record.subject and record.subject.casefold() in sentence.casefold()]
            for sentence in relevant:
                excerpt = sentence[:300]
                net = record.fields.get("net_draft_picks")
                if isinstance(net, (int, float)) and net > 0 and re.search(r"\b(spent|spending|sacrificed|mortgaged)\b.*\b(future|flexibility|capital|picks)\b", sentence, re.I):
                    diagnostics.append(DraftDiagnostic("draft_capital_framing", "Source shows a net gain in draft picks; review claims of spending future flexibility (pick count does not establish pick value).", excerpt, fact.id))
                wins, losses = record.fields.get("wins"), record.fields.get("losses")
                if isinstance(wins, int) and isinstance(losses, int):
                    for match in re.finditer(r"\b(\d+)-(\d+)(?:-(\d+))?\b", sentence):
                        if (int(match[1]), int(match[2])) != (wins, losses):
                            diagnostics.append(DraftDiagnostic("team_record_attribution", f"Source record for {record.subject} is {wins}-{losses}; check team and period attribution.", excerpt, fact.id))
                if record.limitations and not any(word in sentence.casefold() for word in ("available", "partial", "unknown", "incomplete", "among", "through", "could", "may")):
                    diagnostics.append(DraftDiagnostic("source_limitation", "Meaningful source limitations may need to be visible: " + "; ".join(record.limitations), excerpt, fact.id))
    cards, passages, covered, review_truncated = _directional_reviews(selected, text, len(artifact.content) > limit)
    bracket = bracket_review(text, evidence)
    for sentence in sentences:
        for pattern, category in ((_SUPERLATIVE, "superlative"), (_CHAMPIONSHIP, "championship"), (_COMPARISON, "comparison"), (_DIRECTION, "transaction")):
            if pattern.search(sentence):
                if category == "transaction" and any(sentence in paragraph for paragraph in covered):
                    continue
                candidates = [fact for fact in brief.facts if fact.category == category and any(binding.subject and binding.subject.casefold() in sentence.casefold() for binding in fact.bindings)]
                diagnostics.append(DraftDiagnostic(
                    f"{category}_wording",
                    "Review wording, subject and scope against specialized bindings; matches are advisory."
                    if candidates else f"No subject-matched {category} binding was found for this passage; narrow the claim or obtain the corresponding evidence.",
                    sentence[:300],
                ))
    for ref in re.findall(r"\b(?:e\d+_\d+|direct\d+)\.r\d+\b", artifact.content):
        if evidence.resolve(ref) is None:
            errors.append(f"Visible reference {ref} does not resolve to this generation's evidence.")
    truncated = review_truncated or bool(bracket and bracket.truncated) or scanned_records > 100 or len(artifact.content) > limit or len(re.split(r"(?<=[.!?])\s+|\n+", text)) > 160 or len(diagnostics) > 40
    return DraftVerification(
        artifact.path, artifact.revision, artifact.content_hash, brief.revision,
        tuple(diagnostics[:40]), tuple(dict.fromkeys(errors)), len(text), truncated,
        cards, passages, bracket,
    )
