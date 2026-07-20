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
    specs: list[tuple[Path, float]],
    output: Path,
    run_id: str,
    k: int,
    hits: int,
    head_run: Path | None = None,
    head_depth: int = 0,
) -> tuple[int, int]:
    loaded = [(read_run(path), weight) for path, weight in specs]
    protected_run = read_run(head_run) if head_run is not None else None
    topics = list(loaded[0][0])
    expected = set(topics)
    for index, (run, _) in enumerate(loaded[1:], start=2):
        if set(run) != expected:
            raise RetrievalError(f"Run {index} has different topic coverage")
    if protected_run is not None and set(protected_run) != expected:
        raise RetrievalError("Head-protection run has different topic coverage")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    rows = 0
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for qid in topics:
                rankings = [[item.docid for item in run[qid]] for run, _ in loaded]
                weights = [weight for _, weight in loaded]
                fused = reciprocal_rank_fusion(rankings, k=k, weights=weights)
                protected = (
                    [item.docid for item in protected_run[qid][:head_depth]]
                    if protected_run is not None and head_depth > 0
                    else []
                )
                protected_set = set(protected)
                ranking = [*protected, *(item.docid for item in fused if item.docid not in protected_set)][:hits]
                for rank, docid in enumerate(ranking, start=1):
                    score = float(hits - rank + 1) if protected else next(
                        item.score for item in fused if item.docid == docid
                    )
                    stream.write(f"{qid} Q0 {docid} {rank} {score:.12g} {run_id}\n")
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
    parser.add_argument("--head-run", type=Path, help="Optional run whose first --head-depth documents stay fixed.")
    parser.add_argument("--head-depth", type=int, default=0)
    args = parser.parse_args(argv)
    if len(args.run) < 2:
        parser.error("provide at least two --run values")
    if args.rrf_k < 0 or args.hits <= 0:
        parser.error("--rrf-k must be non-negative and --hits positive")
    if args.head_depth < 0:
        parser.error("--head-depth must be non-negative")
    if (args.head_run is None) != (args.head_depth == 0):
        parser.error("--head-run and a positive --head-depth must be provided together")
    if not re.fullmatch(r"\S+", args.run_id):
        parser.error("--run-id must not contain whitespace")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        topics, rows = fuse(
            args.run,
            args.output,
            args.run_id,
            args.rrf_k,
            args.hits,
            args.head_run,
            args.head_depth,
        )
    except (OSError, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {rows} fused rows for {topics} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
