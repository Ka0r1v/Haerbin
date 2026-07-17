"""Reciprocal Rank Fusion for multiple document rankings."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class FusedDocument:
    docid: str
    score: float


def reciprocal_rank_fusion(
    rankings: Iterable[Iterable[str]],
    *,
    k: float = 60.0,
    limit: int | None = None,
    weights: Sequence[float] | None = None,
) -> list[FusedDocument]:
    if k <= 0:
        raise ValueError("RRF k must be positive")
    ranking_lists = [list(ranking) for ranking in rankings]
    if weights is None:
        weights = [1.0] * len(ranking_lists)
    if len(weights) != len(ranking_lists):
        raise ValueError("RRF weights must match the number of rankings")
    if any(weight <= 0 for weight in weights):
        raise ValueError("RRF weights must be positive")
    scores: dict[str, float] = defaultdict(float)
    best_rank: dict[str, int] = {}
    for ranking, weight in zip(ranking_lists, weights):
        seen_in_ranking: set[str] = set()
        for rank, docid in enumerate(ranking, start=1):
            if docid in seen_in_ranking:
                continue
            seen_in_ranking.add(docid)
            scores[docid] += weight / (k + rank)
            best_rank[docid] = min(best_rank.get(docid, rank), rank)
    ordered = sorted(scores, key=lambda docid: (-scores[docid], best_rank[docid], docid))
    if limit is not None:
        ordered = ordered[:limit]
    return [FusedDocument(docid=docid, score=scores[docid]) for docid in ordered]
