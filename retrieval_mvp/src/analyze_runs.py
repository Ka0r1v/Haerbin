#!/usr/bin/env python3
"""Create aggregate and per-topic comparisons for multiple TREC retrieval runs."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

from evaluate_run import read_qrels, read_run
from retrieve import RetrievalError


MVP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QRELS = sorted((MVP_ROOT / "data" / "qrels").glob("*.qrels"))
DEFAULT_OUTPUT = MVP_ROOT / "reports" / "retrieval_comparison.tsv"


def parse_run_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError("run must use LABEL=PATH")
    label, path = spec.split("=", 1)
    if not label.strip() or not path.strip():
        raise argparse.ArgumentTypeError("run must use non-empty LABEL=PATH")
    return label.strip(), Path(path.strip())


def topic_metrics(
    judgments: dict[str, int], ranked: list[str], threshold: int
) -> dict[str, float]:
    rels = [judgments.get(docid, 0) for docid in ranked]
    relevant_total = sum(value >= threshold for value in judgments.values())

    def ndcg(k: int) -> float:
        gains = [value / math.log2(rank + 1) for rank, value in enumerate(rels[:k], 1)]
        ideal_values = sorted(judgments.values(), reverse=True)[:k]
        ideal = sum(value / math.log2(rank + 1) for rank, value in enumerate(ideal_values, 1))
        return sum(gains) / ideal if ideal else 0.0

    def recall(k: int) -> float:
        found = sum(value >= threshold for value in rels[:k])
        return found / relevant_total if relevant_total else 0.0

    hits = 0
    precision_sum = 0.0
    for rank, value in enumerate(rels, 1):
        if value >= threshold:
            hits += 1
            precision_sum += hits / rank
    ap = precision_sum / relevant_total if relevant_total else 0.0
    return {
        "nDCG@10": ndcg(10),
        "nDCG@20": ndcg(20),
        "Recall@100": recall(100),
        "Recall@1000": recall(1000),
        "MAP": ap,
    }


def write_report(
    output: Path,
    qrels_paths: list[Path],
    runs: list[tuple[str, Path]],
    threshold: int,
) -> tuple[Path, list[dict[str, str | float]]]:
    loaded_runs = {label: read_run(path) for label, path in runs}
    accumulated: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    metric_names = ["nDCG@10", "nDCG@20", "Recall@100", "Recall@1000", "MAP"]
    for qrels_path in qrels_paths:
        qrels = read_qrels(qrels_path)
        for qid, judgments in qrels.items():
            for label, _ in runs:
                values = topic_metrics(judgments, loaded_runs[label].get(qid, []), threshold)
                for metric, value in values.items():
                    accumulated[(qid, label)][metric].append(value)

    rows: list[dict[str, str | float]] = []
    baseline_label = runs[0][0]
    for qid in sorted({qid for qid, _ in accumulated}, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value)):
        baseline = {
            metric: sum(accumulated[(qid, baseline_label)][metric])
            / len(accumulated[(qid, baseline_label)][metric])
            for metric in metric_names
        }
        for label, _ in runs:
            averages = {
                metric: sum(accumulated[(qid, label)][metric])
                / len(accumulated[(qid, label)][metric])
                for metric in metric_names
            }
            row: dict[str, str | float] = {"qid": qid, "run": label}
            for metric in metric_names:
                row[metric] = averages[metric]
                row[f"delta_{metric}"] = averages[metric] - baseline[metric]
            rows.append(row)

    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["qid", "run"] + [item for metric in metric_names for item in (metric, f"delta_{metric}")]
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: f"{value:.6f}" if isinstance(value, float) else value for key, value in row.items()}
            )

    markdown = output.with_suffix(".md")
    lines = [
        "# Retrieval run comparison",
        "",
        f"Averaged per topic across {len(qrels_paths)} qrels files; relevance threshold >= {threshold}.",
        "",
        "| Run | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | MAP |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, _ in runs:
        selected = [row for row in rows if row["run"] == label]
        means = {metric: sum(float(row[metric]) for row in selected) / len(selected) for metric in metric_names}
        lines.append(
            f"| {label} | {means['nDCG@10']:.4f} | {means['nDCG@20']:.4f} | "
            f"{means['Recall@100']:.4f} | {means['Recall@1000']:.4f} | {means['MAP']:.4f} |"
        )
    final_label = runs[-1][0]
    final_rows = [row for row in rows if row["run"] == final_label]
    best = sorted(final_rows, key=lambda row: float(row["delta_nDCG@10"]), reverse=True)[:5]
    worst = sorted(final_rows, key=lambda row: float(row["delta_nDCG@10"]))[:5]
    lines += ["", f"## {final_label}: largest nDCG@10 gains", ""]
    lines += [f"- Topic {row['qid']}: {float(row['delta_nDCG@10']):+.4f}" for row in best]
    lines += ["", f"## {final_label}: largest nDCG@10 losses", ""]
    lines += [f"- Topic {row['qid']}: {float(row['delta_nDCG@10']):+.4f}" for row in worst]
    markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return markdown, rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", type=parse_run_spec, required=True)
    parser.add_argument("--qrels", action="append", type=Path)
    parser.add_argument("--rel-threshold", type=int, default=2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    qrels_paths = args.qrels or DEFAULT_QRELS
    try:
        markdown, rows = write_report(args.output, qrels_paths, args.run, args.rel_threshold)
    except (OSError, RetrievalError, ValueError, ZeroDivisionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(rows)} per-topic rows to {args.output}")
    print(f"Wrote summary to {markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
