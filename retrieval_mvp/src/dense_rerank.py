#!/usr/bin/env python3
"""Fuse a sparse candidate run with bi-encoder dense similarity rankings."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from rerank import (
    DEFAULT_DOCUMENT_CACHES,
    _file_sha256,
    _safe_model_name,
    _save_json_atomic,
    load_cached_documents,
    read_run,
    write_run,
)
from retrieve import DEFAULT_TOPICS, MVP_ROOT, RetrievalError, read_topics


DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_INPUT = MVP_ROOT / "runs" / "deepseek-deep5000.tsv"
DEFAULT_OUTPUT = MVP_ROOT / "runs" / "dense-hybrid.tsv"
DEFAULT_CACHE = MVP_ROOT / "cache" / "dense_reranker"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def score_dense(
    *,
    run: dict[str, list[Any]],
    topics: dict[str, str],
    documents: dict[str, dict[str, str]],
    input_hash: str,
    model_name: str,
    depth: int,
    batch_size: int,
    device: str | None,
    max_length: int,
    cache_path: Path,
) -> dict[str, dict[str, float]]:
    metadata = {
        "input_sha256": input_hash,
        "model": model_name,
        "depth": depth,
        "max_length": max_length,
        "query_prefix": QUERY_PREFIX,
    }
    scores: dict[str, dict[str, float]] = {}
    if cache_path.is_file():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and all(payload.get(k) == v for k, v in metadata.items()):
                scores = payload.get("scores", {})
        except (OSError, json.JSONDecodeError):
            pass

    pending = [qid for qid in run if qid not in scores]
    if not pending:
        print(f"Loaded all dense scores from {cache_path}")
        return scores

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RetrievalError("sentence-transformers is required for dense reranking") from exc

    print(f"Loading dense model: {model_name}")
    model = SentenceTransformer(model_name, device=device)
    model.max_seq_length = max_length
    for index, qid in enumerate(pending, start=1):
        head = run[qid][:depth]
        query_vector = model.encode(
            [QUERY_PREFIX + topics[qid]],
            batch_size=1,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        document_vectors = model.encode(
            [documents[qid][item.docid] for item in head],
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        )
        similarities = document_vectors @ query_vector
        topic_scores = {item.docid: float(score) for item, score in zip(head, similarities)}
        if any(not math.isfinite(score) for score in topic_scores.values()):
            raise RetrievalError(f"Dense model returned a non-finite score for topic {qid}")
        scores[qid] = topic_scores
        _save_json_atomic(cache_path, {**metadata, "scores": scores})
        print(f"[{index}/{len(pending)}] dense-scored {qid}: {len(head)} documents")
    return scores


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_run", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document-cache", action="append", type=Path, dest="document_caches")
    parser.add_argument("--score-cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--depth", type=int, default=5000)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--original-weight", type=float, default=4.0)
    parser.add_argument("--dense-weight", type=float, default=1.0)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--output-hits", type=int)
    parser.add_argument("--run-id", default="haerbin-dense-hybrid")
    args = parser.parse_args(argv)
    if min(args.depth, args.max_length, args.batch_size) <= 0:
        parser.error("--depth, --max-length, and --batch-size must be positive")
    if args.output_hits is not None and args.output_hits <= 0:
        parser.error("--output-hits must be positive")
    if args.original_weight < 0 or args.dense_weight <= 0 or args.rrf_k < 0:
        parser.error("weights must be non-negative and dense weight positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run = read_run(args.input_run)
        topics = {topic.qid: topic.narrative for topic in read_topics(args.topics)}
        missing_topics = set(run) - set(topics)
        if missing_topics:
            raise RetrievalError(f"Missing topics: {', '.join(sorted(missing_topics))}")
        wanted = {qid: {item.docid for item in items[: args.depth]} for qid, items in run.items()}
        documents = load_cached_documents(args.document_caches or DEFAULT_DOCUMENT_CACHES, wanted)
        missing = sum(len(docids - set(documents.get(qid, {}))) for qid, docids in wanted.items())
        if missing:
            raise RetrievalError(f"Missing cached text for {missing} dense candidates")
        cache_name = (
            f"{args.input_run.stem}.{_safe_model_name(args.model)}."
            f"depth-{args.depth}.max-{args.max_length}.json"
        )
        scores = score_dense(
            run=run,
            topics=topics,
            documents=documents,
            input_hash=_file_sha256(args.input_run),
            model_name=args.model,
            depth=args.depth,
            batch_size=args.batch_size,
            device=args.device,
            max_length=args.max_length,
            cache_path=args.score_cache_dir / cache_name,
        )
        rows = write_run(
            args.output,
            run,
            scores,
            args.depth,
            args.original_weight,
            args.dense_weight,
            args.rrf_k,
            args.run_id,
            args.output_hits,
        )
    except (OSError, RetrievalError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {rows} dense-hybrid rows for {len(run)} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
