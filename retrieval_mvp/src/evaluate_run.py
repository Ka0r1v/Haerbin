#!/usr/bin/env python3
"""Compute dependency-free diagnostic Retrieval metrics."""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path


MVP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QRELS = (
    MVP_ROOT
    / "data"
    / "qrels"
    / "rag25-climbmix-umbrela-codex-gpt5.5-medium-reasoning-v1.qrels"
)


def read_qrels(path: Path) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            fields = line.split()
            if len(fields) != 4:
                raise ValueError(f"{path}:{line_number}: expected 4 qrels fields")
            qid, _, docid, relevance = fields
            qrels[qid][docid] = int(relevance)
    return dict(qrels)


def read_run(path: Path) -> dict[str, list[str]]:
    run: dict[str, list[tuple[int, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            fields = line.split()
            if len(fields) != 6:
                raise ValueError(f"{path}:{line_number}: expected 6 run fields")
            qid, _, docid, rank, _, _ = fields
            run[qid].append((int(rank), docid))
    return {qid: [docid for _, docid in sorted(rows)] for qid, rows in run.items()}


def dcg(relevances: list[int], cutoff: int, gain: str = "linear") -> float:
    def value(relevance: int) -> float:
        return float(relevance) if gain == "linear" else float(2**relevance - 1)

    return sum(
        value(relevance) / math.log2(rank + 1)
        for rank, relevance in enumerate(relevances[:cutoff], start=1)
    )


def average_precision(relevances: list[int], relevant_total: int, threshold: int) -> float:
    if relevant_total == 0:
        return 0.0
    hits = 0
    total = 0.0
    for rank, relevance in enumerate(relevances, start=1):
        if relevance >= threshold:
            hits += 1
            total += hits / rank
    return total / relevant_total


def evaluate(
    qrels: dict[str, dict[str, int]],
    run: dict[str, list[str]],
    threshold: int,
    gain: str = "linear",
) -> dict[str, float]:
    sums = {
        "nDCG@10": 0.0,
        "nDCG@20": 0.0,
        "Recall@100": 0.0,
        "Recall@1000": 0.0,
        "Recall@5000": 0.0,
        "MAP": 0.0,
    }
    for qid, judgments in qrels.items():
        ranked_docids = run.get(qid, [])
        relevances = [judgments.get(docid, 0) for docid in ranked_docids]
        ideal = sorted(judgments.values(), reverse=True)
        for cutoff in (10, 20):
            ideal_dcg = dcg(ideal, cutoff, gain)
            sums[f"nDCG@{cutoff}"] += dcg(relevances, cutoff, gain) / ideal_dcg if ideal_dcg else 0.0
        relevant_total = sum(relevance >= threshold for relevance in judgments.values())
        for cutoff in (100, 1000, 5000):
            retrieved = sum(relevance >= threshold for relevance in relevances[:cutoff])
            sums[f"Recall@{cutoff}"] += retrieved / relevant_total if relevant_total else 0.0
        sums["MAP"] += average_precision(relevances, relevant_total, threshold)
    topic_count = len(qrels)
    return {name: value / topic_count for name, value in sums.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--rel-threshold", type=int, default=1, choices=range(1, 5))
    parser.add_argument(
        "--gain",
        choices=("linear", "exponential"),
        default="linear",
        help="nDCG gain. linear matches the default NIST trec_eval ndcg_cut measure.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        qrels = read_qrels(args.qrels)
        run = read_run(args.run)
        metrics = evaluate(qrels, run, args.rel_threshold, args.gain)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"qrels={args.qrels}")
    print(f"topics={len(qrels)} rel_threshold={args.rel_threshold} ndcg_gain={args.gain}")
    for name, value in metrics.items():
        print(f"{name:<12} {value:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
