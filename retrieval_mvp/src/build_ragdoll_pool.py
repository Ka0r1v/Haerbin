#!/usr/bin/env python3
"""Build a stable-id shallow RAGDoll pool from multiple TREC runs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from rerank import DEFAULT_DOCUMENT_CACHES, load_cached_documents, read_run
from retrieve import DEFAULT_TOPICS, MVP_ROOT, RetrievalError, read_topics


DEFAULT_OUTPUT = MVP_ROOT / "candidates" / "ragdoll-bm25-v2-v3-top10-pool.jsonl"


def run_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("run must be NAME=PATH")
    name, path = value.split("=", 1)
    if not name.strip() or not path.strip():
        raise argparse.ArgumentTypeError("run must be NAME=PATH")
    return name.strip(), Path(path.strip())


def build_pool(
    specs: list[tuple[str, Path]],
    *,
    topics_path: Path,
    output: Path,
    cache_dirs: list[Path],
    topk: int,
) -> tuple[int, int, dict[str, int]]:
    topics = {topic.qid: topic.narrative for topic in read_topics(topics_path)}
    runs = {name: read_run(path) for name, path in specs}
    wanted: dict[str, set[str]] = defaultdict(set)
    membership: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for name, run in runs.items():
        if set(run) != set(topics):
            raise RetrievalError(f"Run {name} does not match topic coverage")
        for qid, items in run.items():
            for rank, item in enumerate(items[:topk], start=1):
                wanted[qid].add(item.docid)
                membership[(qid, item.docid)][name] = rank
    documents = load_cached_documents(cache_dirs, dict(wanted))
    missing = sum(len(docids - set(documents.get(qid, {}))) for qid, docids in wanted.items())
    if missing:
        raise RetrievalError(f"Missing cached text for {missing} pooled candidate documents")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    counts = {name: 0 for name in runs}
    rows = 0
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for qid in topics:
                ordered = sorted(
                    wanted[qid],
                    key=lambda docid: (
                        min(membership[(qid, docid)].values()),
                        docid,
                    ),
                )
                for docid in ordered:
                    systems = membership[(qid, docid)]
                    for name in systems:
                        counts[name] += 1
                    payload = {
                        "task_id": f"{qid}:{docid}",
                        "query": {"qid": qid, "text": topics[qid]},
                        "candidates": [
                            {
                                "docid": docid,
                                "doc": {"segment": documents[qid][docid]},
                                "systems": systems,
                            }
                        ],
                    }
                    stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    rows += 1
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return len(topics), rows, counts


def seed_judgments(source: Path, output: Path) -> int:
    seeded: dict[tuple[str, str], dict] = {}
    with source.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            qid, docid = row.get("qid"), row.get("docid")
            if qid is None or docid is None or row.get("status") != "completed":
                continue
            row = dict(row)
            row["task_id"] = f"{qid}:{docid}"
            seeded[(str(qid), str(docid))] = row
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in seeded.values()),
        encoding="utf-8",
    )
    return len(seeded)


def build_tiebreak_pool(pool: Path, judgments: Path, output: Path) -> int:
    grades: dict[tuple[str, str], set[int]] = defaultdict(set)
    with judgments.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("status") == "completed" and int(row.get("judgment", -1)) >= 0:
                grades[(str(row["qid"]), str(row["docid"]))].add(int(row["judgment"]))
    conflicts = {key for key, values in grades.items() if len(values) > 1}
    selected = []
    with pool.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            candidate = row["candidates"][0]
            key = (str(row["query"]["qid"]), str(candidate["docid"]))
            if key in conflicts:
                row["task_id"] = f"tiebreak:{key[0]}:{key[1]}"
                selected.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )
    return len(selected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", type=run_spec, required=True)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document-cache", action="append", dest="document_caches", type=Path)
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--seed-source", type=Path)
    parser.add_argument("--seed-output", type=Path)
    parser.add_argument("--tiebreak-judgments", type=Path)
    parser.add_argument("--tiebreak-output", type=Path)
    args = parser.parse_args(argv)
    if args.topk <= 0:
        parser.error("--topk must be positive")
    if (args.seed_source is None) != (args.seed_output is None):
        parser.error("--seed-source and --seed-output must be provided together")
    if (args.tiebreak_judgments is None) != (args.tiebreak_output is None):
        parser.error("--tiebreak-judgments and --tiebreak-output must be provided together")
    try:
        topics, rows, counts = build_pool(
            args.run,
            topics_path=args.topics,
            output=args.output,
            cache_dirs=args.document_caches or DEFAULT_DOCUMENT_CACHES,
            topk=args.topk,
        )
        seeded = seed_judgments(args.seed_source, args.seed_output) if args.seed_source else 0
        tiebreaks = (
            build_tiebreak_pool(args.output, args.tiebreak_judgments, args.tiebreak_output)
            if args.tiebreak_judgments
            else 0
        )
    except (OSError, json.JSONDecodeError, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote pool: topics={topics}, unique_pairs={rows}, memberships={counts}")
    if args.seed_source:
        print(f"Seeded {seeded} existing judgments into {args.seed_output}")
    if args.tiebreak_judgments:
        print(f"Wrote {tiebreaks} conflict tiebreak tasks to {args.tiebreak_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
