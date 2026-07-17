#!/usr/bin/env python3
"""Evaluate a run with the NIST trec_eval binary built under WSL."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from evaluate_run import DEFAULT_QRELS, evaluate, read_qrels, read_run


MVP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BINARY = MVP_ROOT / "tools" / "trec_eval" / "trec_eval"
DEFAULT_CACHE = MVP_ROOT / "cache" / "official_eval"


def wsl_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name != "nt":
        return resolved
    drive, rest = resolved[0].lower(), resolved[2:].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def threshold_qrels(source: Path, destination: Path, threshold: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with source.open("r", encoding="utf-8-sig") as input_stream, temporary.open(
        "w", encoding="utf-8", newline="\n"
    ) as output_stream:
        for line_number, line in enumerate(input_stream, start=1):
            fields = line.split()
            if len(fields) != 4:
                raise ValueError(f"{source}:{line_number}: expected four qrels fields")
            fields[3] = "1" if int(fields[3]) >= threshold else "0"
            output_stream.write(" ".join(fields) + "\n")
    temporary.replace(destination)


def run_measure(binary: Path, qrels: Path, run: Path, measure: str) -> float:
    if os.name == "nt":
        command = ["wsl", wsl_path(binary), "-m", measure, wsl_path(qrels), wsl_path(run)]
    else:
        command = [str(binary), "-m", measure, str(qrels), str(run)]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    rows = [line.split() for line in completed.stdout.splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"trec_eval returned no output for {measure}")
    return float(rows[-1][-1])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--rel-threshold", type=int, default=2, choices=range(1, 5))
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if not args.binary.is_file():
            raise ValueError(
                "trec_eval is not built. Clone usnistgov/trec_eval under "
                "retrieval_mvp/tools/trec_eval and run make in WSL."
            )
        thresholded = DEFAULT_CACHE / f"{args.qrels.stem}.threshold-{args.rel_threshold}.qrels"
        threshold_qrels(args.qrels, thresholded, args.rel_threshold)
        metrics = {
            "nDCG@10": run_measure(args.binary, args.qrels, args.run, "ndcg_cut.10"),
            "nDCG@20": run_measure(args.binary, args.qrels, args.run, "ndcg_cut.20"),
            "Recall@100": run_measure(args.binary, thresholded, args.run, "recall.100"),
            "Recall@1000": run_measure(args.binary, thresholded, args.run, "recall.1000"),
            "Recall@5000": run_measure(args.binary, thresholded, args.run, "recall.5000"),
            "MAP": run_measure(args.binary, thresholded, args.run, "map"),
        }
        local = evaluate(read_qrels(args.qrels), read_run(args.run), args.rel_threshold, "linear")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"evaluator=NIST trec_eval qrels={args.qrels}")
    print(f"rel_threshold={args.rel_threshold} ndcg_gain=linear")
    for name, value in metrics.items():
        print(f"{name:<12} {value:.4f} local_delta={local[name] - value:+.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
