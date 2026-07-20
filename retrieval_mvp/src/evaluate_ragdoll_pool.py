#!/usr/bin/env python3
"""Evaluate multiple Top-K TREC runs on one completed RAGDoll judgment pool."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from build_ragdoll_pool import run_spec
from rerank import read_run
from retrieve import MVP_ROOT, RetrievalError


DEFAULT_JUDGMENTS = MVP_ROOT / "candidates" / "ragdoll-bm25-v2-v3-top10.judgments.jsonl"
DEFAULT_REPORT = MVP_ROOT / "reports" / "ragdoll_bm25_v2_v3_pool.md"


def dcg(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades))


def load_judgments(paths: list[Path]) -> tuple[dict[str, dict[str, int]], Counter[int], int, int]:
    observed: dict[tuple[str, str], list[int]] = defaultdict(list)
    failures = 0
    for path in paths:
        with path.open("r", encoding="utf-8-sig") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("status") != "completed" or int(row.get("judgment", -1)) < 0:
                    failures += 1
                    continue
                key = (str(row["qid"]), str(row["docid"]))
                observed[key].append(int(row["judgment"]))
    conflicts = sum(len(set(values)) > 1 for values in observed.values())
    unresolved = [key for key, values in observed.items() if len(set(values)) > 1 and len(values) % 2 == 0]
    if unresolved:
        raise RetrievalError(f"{len(unresolved)} conflicting judgments still need an odd tiebreak vote")
    judgments: dict[str, dict[str, int]] = defaultdict(dict)
    distribution: Counter[int] = Counter()
    for (qid, docid), values in observed.items():
        grade = int(statistics.median(values))
        judgments[qid][docid] = grade
        distribution[grade] += 1
    return dict(judgments), distribution, failures, conflicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", type=run_spec, required=True)
    parser.add_argument("--judgments", action="append", type=Path)
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--relevant-grade", type=int, default=2)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    try:
        judgment_paths = args.judgments or [DEFAULT_JUDGMENTS]
        judgments, distribution, failures, conflicts = load_judgments(judgment_paths)
        results = []
        for name, path in args.run:
            run = read_run(path)
            topic_scores = []
            relevant = judged = 0
            for qid, items in run.items():
                grades = []
                for item in items[: args.topk]:
                    if item.docid not in judgments.get(qid, {}):
                        raise RetrievalError(f"Missing pooled judgment for {name} {qid} {item.docid}")
                    grade = judgments[qid][item.docid]
                    grades.append(grade)
                    judged += 1
                    relevant += grade >= args.relevant_grade
                ideal = dcg(sorted(judgments[qid].values(), reverse=True)[: args.topk])
                topic_scores.append(dcg(grades) / ideal if ideal else 0.0)
            results.append(
                {
                    "name": name,
                    "ndcg": sum(topic_scores) / len(topic_scores),
                    "relevant_rate": relevant / judged,
                    "relevant": relevant,
                    "judged": judged,
                }
            )
        report = [
            "# BM25 / V2 / V3 统一 RAGDoll Shallow-Pool 对比",
            "",
            "统一判断池："
            + "、".join(f"`{path.name}`" for path in judgment_paths)
            + f"；每个系统评估 Top-{args.topk}。",
            "",
            "| Run | pooled nDCG@10 | grade>=2 | judged |",
            "| --- | ---: | ---: | ---: |",
        ]
        for result in results:
            report.append(
                f"| {result['name']} | {result['ndcg']:.4f} | "
                f"{result['relevant_rate']:.2%} ({result['relevant']}/{result['judged']}) | {result['judged']} |"
            )
        report += [
            "",
            "Judgment distribution："
            + "、".join(f"grade {grade}={count}" for grade, count in sorted(distribution.items())),
            f"；failed={failures}；resolved conflicts={conflicts}。",
            "",
            "这是同一 BM25/V2/V3 Top-10 并集上的 shallow-pool LLM judgment，适合比较三个系统的 Top-10。"
            "它仍然不是全库 qrels，不能计算可信的 Recall@1000/5000 或正式排行榜成绩。",
            "",
        ]
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text("\n".join(report), encoding="utf-8")
    except (OSError, json.JSONDecodeError, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
