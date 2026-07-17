#!/usr/bin/env python3
"""Validate a TREC RAG 2026 Retrieval runfile."""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from retrieve import DEFAULT_TOPICS, RetrievalError, read_topics


@dataclass(frozen=True)
class Row:
    line: int
    qid: str
    docid: str
    rank: int
    score: float
    run_id: str


def validate(
    run_path: Path,
    topics_path: Path,
    *,
    allow_subset: bool,
    expected_hits: int | None,
) -> tuple[list[str], int, int]:
    expected_qids = [topic.qid for topic in read_topics(topics_path)]
    expected_set = set(expected_qids)
    grouped: dict[str, list[Row]] = defaultdict(list)
    errors: list[str] = []
    seen_order: list[str] = []
    closed: set[str] = set()
    current_qid: str | None = None
    run_ids: set[str] = set()

    with run_path.open("r", encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.strip()
            if not line:
                errors.append(f"line {line_number}: blank lines are not allowed")
                continue
            fields = line.split()
            if len(fields) != 6:
                errors.append(f"line {line_number}: expected 6 fields, found {len(fields)}")
                continue
            qid, q0, docid, rank_text, score_text, run_id = fields
            if q0 != "Q0":
                errors.append(f"line {line_number}: second field must be Q0")
            if qid not in expected_set:
                errors.append(f"line {line_number}: unknown qid {qid!r}")
            try:
                rank = int(rank_text)
            except ValueError:
                errors.append(f"line {line_number}: rank is not an integer")
                continue
            try:
                score = float(score_text)
            except ValueError:
                errors.append(f"line {line_number}: score is not numeric")
                continue
            if not math.isfinite(score):
                errors.append(f"line {line_number}: score must be finite")
            if not docid.startswith("shard_"):
                errors.append(f"line {line_number}: unexpected ClimbMix docid {docid!r}")
            if current_qid != qid:
                if current_qid is not None:
                    closed.add(current_qid)
                if qid in closed:
                    errors.append(f"line {line_number}: qid {qid!r} is not contiguous")
                current_qid = qid
                seen_order.append(qid)
            grouped[qid].append(Row(line_number, qid, docid, rank, score, run_id))
            run_ids.add(run_id)

    if not grouped:
        errors.append("runfile contains no valid rows")
    if len(run_ids) > 1:
        errors.append(f"run_id must be stable; found {sorted(run_ids)}")
    actual_set = set(grouped)
    if allow_subset:
        if not actual_set.issubset(expected_set):
            errors.append("runfile contains qids outside the topic file")
    elif actual_set != expected_set:
        missing = [qid for qid in expected_qids if qid not in actual_set]
        extra = sorted(actual_set - expected_set)
        if missing:
            errors.append(f"missing topics: {', '.join(missing[:10])}")
        if extra:
            errors.append(f"unexpected topics: {', '.join(extra[:10])}")

    for qid, rows in grouped.items():
        ranks = [row.rank for row in rows]
        wanted = list(range(1, len(rows) + 1))
        if ranks != wanted:
            errors.append(f"{qid}: ranks must be consecutive from 1")
        docids = [row.docid for row in rows]
        if len(docids) != len(set(docids)):
            errors.append(f"{qid}: duplicate docids")
        if any(left.score < right.score for left, right in zip(rows, rows[1:])):
            errors.append(f"{qid}: scores must be non-increasing")
        if expected_hits is not None and len(rows) != expected_hits:
            errors.append(f"{qid}: expected {expected_hits} rows, found {len(rows)}")
    return errors, len(grouped), sum(len(rows) for rows in grouped.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--allow-subset", action="store_true")
    parser.add_argument("--expected-hits", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        errors, topics, rows = validate(
            args.run,
            args.topics,
            allow_subset=args.allow_subset,
            expected_hits=args.expected_hits,
        )
    except (OSError, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors[:30]:
            print(f"ERROR: {error}", file=sys.stderr)
        if len(errors) > 30:
            print(f"ERROR: ... and {len(errors) - 30} more", file=sys.stderr)
        return 1
    print(f"Valid runfile: {topics} topics, {rows} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
