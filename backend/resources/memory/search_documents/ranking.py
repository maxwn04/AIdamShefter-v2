"""Compose independent relevance rankings after canonical eligibility filtering."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from backend.resources.memory.search_documents.objects import (
    SearchDocumentCandidate, SearchDocumentQuery, SearchMatchReason,
)


# A relevance floor, not a probability or evidence-confidence threshold.
MIN_SEMANTIC_SIMILARITY = 0.35
_RRF_OFFSET = 60


def rank_candidates(
    candidates: Sequence[SearchDocumentCandidate],
    query: SearchDocumentQuery,
    semantic_scores: dict[UUID, float],
) -> tuple[SearchDocumentCandidate, ...]:
    """Fuse matching strategy ranks, then keep one representative per item.

    Structured browse retains its existing salience ordering. Text discovery
    uses equal-weight reciprocal ranks so lexical and cosine scales cannot
    accidentally dominate one another. Salience breaks ties only.
    """
    structured = {
        candidate.version_id: (
            candidate.score_components.entity_overlap
            + candidate.score_components.evidence_overlap
            + candidate.score_components.related_item_overlap
            + candidate.score_components.tag_overlap
        ) for candidate in candidates
    }
    lexical = {candidate.version_id: candidate.score_components.lexical_rank
               for candidate in candidates}
    semantic = {
        candidate.version_id: semantic_scores[candidate.version_id]
        for candidate in candidates
        if semantic_scores.get(candidate.version_id, -1) >= MIN_SEMANTIC_SIMILARITY
    }
    ranks: dict[UUID, float] = {}
    if query.text:
        for strategy in (structured, lexical, semantic):
            ordered = sorted(
                (candidate for candidate in candidates
                 if strategy.get(candidate.version_id, 0) > 0),
                key=lambda candidate: (
                    -strategy[candidate.version_id], not candidate.current_at_pin,
                    -candidate.revision_number, str(candidate.version_id),
                ),
            )
            # Versions of one arc must not push unrelated items down a strategy.
            item_rank: dict[UUID, int] = {}
            for candidate in ordered:
                if candidate.item_id in item_rank:
                    continue
                rank = len(item_rank) + 1
                item_rank[candidate.item_id] = rank
                ranks[candidate.version_id] = ranks.get(candidate.version_id, 0) + 1 / (_RRF_OFFSET + rank)
    selected: list[SearchDocumentCandidate] = []
    for candidate in candidates:
        if query.text and candidate.version_id not in ranks:
            continue
        reasons = list(candidate.match_reasons)
        similarity = semantic.get(candidate.version_id, 0.0)
        if similarity:
            reasons.append(SearchMatchReason.SEMANTIC_MATCH)
        if query.has_discovery_signals and not reasons:
            continue
        components = candidate.score_components.model_copy(update={
            "semantic_similarity": similarity,
            "reciprocal_rank": ranks.get(candidate.version_id, 0.0),
        })
        selected.append(candidate.model_copy(update={
            "score": components.total, "score_components": components,
            "match_reasons": tuple(reasons),
        }))
    selected.sort(key=lambda candidate: (
        -candidate.score, not candidate.current_at_pin,
        -candidate.score_components.salience, -candidate.revision_number,
        candidate.kind.value, str(candidate.version_id),
    ))
    winners: dict[UUID, SearchDocumentCandidate] = {}
    for candidate in selected:
        winners.setdefault(candidate.item_id, candidate)
    return tuple(winners.values())[:query.limit]
