#!/usr/bin/env python3
"""Fuse multiple six-column TREC runs with weighted reciprocal rank fusion."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from rerank import read_run
from retrieve import RetrievalError
from rrf import reciprocal_rank_fusion


MVP_ROOT = Path(__file__).resolve().parents[1]


def run_spec(value: str) -> tuple[Path, float]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("run must use PATH=WEIGHT")
    path, weight = value.rsplit("=", 1)
    try:
        numeric = float(weight)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("run weight must be numeric") from exc
    if not path.strip() or numeric <= 0:
        raise argparse.ArgumentTypeError("run path must be non-empty and weight positive")
    return Path(path.strip()), numeric


def fuse(
    specs: list[tuple[Path, float]], output: Path, run_id: str, k: int, hits: int
) -> tuple[int, int]:
    loaded = [(read_run(path), weight) for path, weight in specs]
    topics = list(loaded[0][0])
    expected = set(topics)
    for index, (run, _) in enumerate(loaded[1:], start=2):
        if set(run) != expected:
            raise RetrievalError(f"Run {index} has different topic coverage")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    rows = 0
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for qid in topics:
                rankings = [[item.docid for item in run[qid]] for run, _ in loaded]
                weights = [weight for _, weight in loaded]
                ranking = reciprocal_rank_fusion(rankings, k=k, weights=weights)[:hits]
                for rank, item in enumerate(ranking, start=1):
                    stream.write(f"{qid} Q0 {item.docid} {rank} {item.score:.12g} {run_id}\n")
                    rows += 1
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return len(topics), rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", type=run_spec, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="haerbin-run-fusion")
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--hits", type=int, default=1000)
    args = parser.parse_args(argv)
    if len(args.run) < 2:
        parser.error("provide at least two --run values")
    if args.rrf_k < 0 or args.hits <= 0:
        parser.error("--rrf-k must be non-negative and --hits positive")
    if not re.fullmatch(r"\S+", args.run_id):
        parser.error("--run-id must not contain whitespace")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        topics, rows = fuse(args.run, args.output, args.run_id, args.rrf_k, args.hits)
    except (OSError, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {rows} fused rows for {topics} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
