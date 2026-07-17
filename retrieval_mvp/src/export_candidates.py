#!/usr/bin/env python3
"""Export a TREC run plus cached document text as Ragnarök/RankLLM-style JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rerank import DEFAULT_DOCUMENT_CACHES, load_cached_documents, read_run
from retrieve import DEFAULT_TOPICS, RetrievalError, read_topics


MVP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = MVP_ROOT / "runs" / "haerbin-balanced-ensemble-dev.tsv"
DEFAULT_OUTPUT = MVP_ROOT / "candidates" / "haerbin-balanced-top100.jsonl"


def export(
    run_path: Path,
    topics_path: Path,
    output: Path,
    cache_dirs: list[Path],
    topk: int,
) -> int:
    run = read_run(run_path)
    topics = {topic.qid: topic.narrative for topic in read_topics(topics_path)}
    missing_topics = set(run) - set(topics)
    if missing_topics:
        raise RetrievalError(f"Missing topics: {', '.join(sorted(missing_topics))}")
    wanted = {qid: {item.docid for item in items[:topk]} for qid, items in run.items()}
    documents = load_cached_documents(cache_dirs, wanted)
    missing = sum(len(docids - set(documents.get(qid, {}))) for qid, docids in wanted.items())
    if missing:
        raise RetrievalError(f"Missing cached text for {missing} candidate documents")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for qid, items in run.items():
                payload = {
                    "query": {"text": topics[qid], "qid": qid},
                    "candidates": [
                        {
                            "docid": item.docid,
                            "score": item.score,
                            "doc": {"segment": documents[qid][item.docid]},
                        }
                        for item in items[:topk]
                    ],
                }
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return len(run)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", nargs="?", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document-cache", action="append", type=Path, dest="document_caches")
    parser.add_argument("--topk", type=int, default=100)
    args = parser.parse_args(argv)
    if args.topk <= 0:
        parser.error("--topk must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        topics = export(
            args.run,
            args.topics,
            args.output,
            args.document_caches or DEFAULT_DOCUMENT_CACHES,
            args.topk,
        )
    except (OSError, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {topics} candidate requests with Top-{args.topk} to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
