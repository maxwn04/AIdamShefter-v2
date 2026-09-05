"""Revision-scoped, bounded diagnostics over actual draft text."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from backend.services.reporter.runner.evidence import EvidenceReader
from backend.services.reporter.runner.grounding import validate_fact
from backend.services.reporter.runner.research_brief import ResearchBrief, ResearchBriefError
from backend.services.reporter.runner.schemas import ArtifactSnapshot


@dataclass(frozen=True)
class DraftDiagnostic:
    code: str
    message: str
    excerpt: str = ""
    fact_id: str | None = None
    severity: str = "DIAGNOSTIC"


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
        }


_DIRECTION = re.compile(r"\b(sent|traded away|gave up|received|acquired|got back)\b", re.I)
_SUPERLATIVE = re.compile(r"\b(longest|highest|lowest|best|worst|most|fewest|first ever|season high)\b", re.I)
_CHAMPIONSHIP = re.compile(r"\b(champion(?:ship)?|won the title|title winner)\b", re.I)
_COMPARISON = re.compile(r"\b(before|after|improved|declined|last season|previous season|year.over.year)\b", re.I)


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
    for fact in brief.facts:
        try:
            validate_fact(fact, evidence)
        except ResearchBriefError as exc:
            errors.append(f"{fact.id}: {exc.message}")
        records = [record for ref in fact.data_refs if (record := evidence.resolve(ref)) is not None]
        for record in records:
            scanned_records += 1
            if scanned_records > 100:
                continue
            relevant = [sentence for sentence in sentences if record.subject and record.subject.casefold() in sentence.casefold()]
            for sentence in relevant:
                excerpt = sentence[:300]
                if record.perspective in {"sent", "received"}:
                    asset = record.fields.get("player_name")
                    if isinstance(asset, str) and asset.casefold() in sentence.casefold():
                        asset_index = sentence.casefold().find(asset.casefold())
                        preceding = list(_DIRECTION.finditer(sentence[:asset_index]))
                        if preceding:
                            verb = preceding[-1].group().lower()
                            prose_direction = "sent" if verb in {"sent", "traded away", "gave up"} else "received"
                            if prose_direction != record.perspective:
                                diagnostics.append(DraftDiagnostic("trade_direction", f"Source lists {record.subject} {record.perspective} {asset}; review the draft's direction.", excerpt, fact.id))
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
    for sentence in sentences:
        for pattern, category in ((_SUPERLATIVE, "superlative"), (_CHAMPIONSHIP, "championship"), (_COMPARISON, "comparison"), (_DIRECTION, "transaction")):
            if pattern.search(sentence):
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
    truncated = scanned_records > 100 or len(artifact.content) > limit or len(re.split(r"(?<=[.!?])\s+|\n+", text)) > 160 or len(diagnostics) > 40
    return DraftVerification(
        artifact.path, artifact.revision, artifact.content_hash, brief.revision,
        tuple(diagnostics[:40]), tuple(dict.fromkeys(errors)), len(text), truncated,
    )
