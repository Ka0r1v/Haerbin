#!/usr/bin/env python3
"""Semantically rerank a TREC run using document text cached from Pyserini."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from retrieve import DEFAULT_TOPICS, RetrievalError, read_topics


MVP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = MVP_ROOT / "runs" / "haerbin-deepseek-rrf-dev.tsv"
DEFAULT_OUTPUT = MVP_ROOT / "runs" / "haerbin-semantic-rerank-dev.tsv"
DEFAULT_SCORE_CACHE = MVP_ROOT / "cache" / "reranker"
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_DOCUMENT_CACHES = [MVP_ROOT / "cache" / "search", MVP_ROOT / "cache" / "multiquery_search"]
DEFAULT_DOCUMENT_STORE = MVP_ROOT / "cache" / "docstore.sqlite3"


@dataclass(frozen=True)
class RunItem:
    docid: str
    rank: int
    score: float


def read_run(path: Path) -> dict[str, list[RunItem]]:
    grouped: dict[str, list[RunItem]] = {}
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            fields = raw_line.split()
            if len(fields) != 6:
                raise RetrievalError(f"{path}:{line_number}: expected six TREC fields")
            qid, _, docid, rank_text, score_text, _ = fields
            try:
                rank, score = int(rank_text), float(score_text)
            except ValueError as exc:
                raise RetrievalError(f"{path}:{line_number}: invalid rank or score") from exc
            grouped.setdefault(qid, []).append(RunItem(docid, rank, score))
    for qid, items in grouped.items():
        items.sort(key=lambda item: item.rank)
        if len({item.docid for item in items}) != len(items):
            raise RetrievalError(f"Input run contains duplicate docids for topic {qid}")
    if not grouped:
        raise RetrievalError(f"No run rows found in {path}")
    return grouped


def extract_document_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        for key in ("contents", "segment", "text", "body"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
    return None


def load_cached_documents(
    cache_dirs: list[Path], wanted: dict[str, set[str]]
) -> dict[str, dict[str, str]]:
    documents: dict[str, dict[str, str]] = {qid: {} for qid in wanted}
    if DEFAULT_DOCUMENT_STORE.is_file():
        all_docids = sorted(set().union(*wanted.values())) if wanted else []
        with sqlite3.connect(DEFAULT_DOCUMENT_STORE) as connection:
            for start in range(0, len(all_docids), 500):
                batch = all_docids[start : start + 500]
                placeholders = ",".join("?" for _ in batch)
                for docid, document_text in connection.execute(
                    f"SELECT docid, text FROM documents WHERE docid IN ({placeholders})", batch
                ):
                    for qid, qid_wanted in wanted.items():
                        if docid in qid_wanted:
                            documents[qid][docid] = document_text
        if all(len(documents[qid]) == len(docids) for qid, docids in wanted.items()):
            return documents
    for cache_dir in cache_dirs:
        if not cache_dir.is_dir():
            continue
        for path in cache_dir.rglob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            qid = str(record.get("qid", ""))
            if qid not in wanted:
                continue
            response = record.get("response", record)
            if not isinstance(response, dict):
                continue
            candidates = response.get("candidates")
            if not isinstance(candidates, list):
                continue
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                docid = candidate.get("docid")
                if (
                    not isinstance(docid, str)
                    or docid not in wanted[qid]
                    or docid in documents[qid]
                ):
                    continue
                text = extract_document_text(candidate.get("doc"))
                if text:
                    documents[qid].setdefault(docid, text)
    return documents


def fused_order(
    items: list[RunItem],
    semantic_scores: dict[str, float],
    depth: int,
    original_weight: float,
    semantic_weight: float,
    rrf_k: int,
) -> list[RunItem]:
    head = items[:depth]
    tail = items[depth:]
    semantic = sorted(
        head,
        key=lambda item: (-semantic_scores[item.docid], item.rank, item.docid),
    )
    semantic_rank = {item.docid: rank for rank, item in enumerate(semantic, start=1)}
    fused = sorted(
        head,
        key=lambda item: (
            -(
                original_weight / (rrf_k + item.rank)
                + semantic_weight / (rrf_k + semantic_rank[item.docid])
            ),
            item.rank,
            item.docid,
        ),
    )
    return fused + tail


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_model_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model).strip("._") or "model"


def _save_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    for attempt in range(8):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 7:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.1 * (2**attempt))


def score_candidates(
    *,
    run: dict[str, list[RunItem]],
    topics: dict[str, str],
    documents: dict[str, dict[str, str]],
    input_hash: str,
    model_name: str,
    depth: int,
    max_length: int,
    batch_size: int,
    device: str | None,
    dtype: str,
    cache_path: Path,
) -> dict[str, dict[str, float]]:
    metadata = {
        "input_sha256": input_hash,
        "model": model_name,
        "depth": depth,
        "max_length": max_length,
    }
    cached: dict[str, Any] = {}
    if cache_path.is_file():
        try:
            candidate = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(candidate, dict) and all(candidate.get(k) == v for k, v in metadata.items()):
                cached = candidate
        except (OSError, json.JSONDecodeError):
            pass
    scores: dict[str, dict[str, float]] = cached.get("scores", {}) if cached else {}

    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RetrievalError(
            "sentence-transformers is missing. Run: "
            "python -m pip install -r retrieval_mvp/requirements-rerank.txt"
        ) from exc

    pending = [qid for qid in run if qid not in scores]
    if not pending:
        print(f"Loaded all semantic scores from {cache_path}")
        return scores

    kwargs: dict[str, Any] = {"max_length": max_length}
    if device:
        kwargs["device"] = device
    if dtype != "auto":
        try:
            import torch
        except ImportError as exc:
            raise RetrievalError("PyTorch is required for an explicit --dtype.") from exc
        kwargs["model_kwargs"] = {
            "torch_dtype": torch.float16 if dtype == "float16" else torch.float32
        }
    print(f"Loading reranker model: {model_name}")
    model = CrossEncoder(model_name, **kwargs)
    for index, qid in enumerate(pending, start=1):
        head = run[qid][:depth]
        pairs = [(topics[qid], documents[qid][item.docid]) for item in head]
        predictions = model.predict(
            pairs,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        topic_scores = {item.docid: float(score) for item, score in zip(head, predictions)}
        if any(not math.isfinite(score) for score in topic_scores.values()):
            raise RetrievalError(f"Model returned a non-finite score for topic {qid}")
        scores[qid] = topic_scores
        _save_json_atomic(cache_path, {**metadata, "scores": scores})
        print(f"[{index}/{len(pending)}] scored topic {qid}: {len(head)} documents")
    return scores


def write_run(
    output: Path,
    run: dict[str, list[RunItem]],
    scores: dict[str, dict[str, float]],
    depth: int,
    original_weight: float,
    semantic_weight: float,
    rrf_k: int,
    run_id: str,
    output_hits: int | None = None,
) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    rows = 0
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for qid, items in run.items():
                ordered = fused_order(
                    items, scores[qid], min(depth, len(items)), original_weight, semantic_weight, rrf_k
                )
                if output_hits is not None:
                    ordered = ordered[:output_hits]
                total = len(ordered)
                for rank, item in enumerate(ordered, start=1):
                    stream.write(f"{qid} Q0 {item.docid} {rank} {total - rank + 1:.8f} {run_id}\n")
                    rows += 1
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_run", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document-cache", action="append", type=Path, dest="document_caches")
    parser.add_argument("--score-cache-dir", type=Path, default=DEFAULT_SCORE_CACHE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--depth", type=int, default=1000)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", help="For example cuda, cuda:0, or cpu; default is automatic.")
    parser.add_argument(
        "--dtype",
        choices=("auto", "float16", "float32"),
        default="auto",
        help="Model precision. Use float16 for larger rerankers on an NVIDIA GPU.",
    )
    parser.add_argument("--original-weight", type=float, default=1.0)
    parser.add_argument("--semantic-weight", type=float, default=1.0)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument(
        "--output-hits",
        type=int,
        help="Write at most this many documents per topic; scores are still cached at --depth.",
    )
    parser.add_argument("--run-id", default="haerbin-semantic-rerank")
    args = parser.parse_args(argv)
    if args.depth <= 0 or args.max_length <= 0 or args.batch_size <= 0:
        parser.error("--depth, --max-length, and --batch-size must be positive")
    if args.output_hits is not None and args.output_hits <= 0:
        parser.error("--output-hits must be positive")
    if args.rrf_k < 0:
        parser.error("--rrf-k cannot be negative")
    if args.original_weight < 0 or args.semantic_weight <= 0:
        parser.error("weights require original >= 0 and semantic > 0")
    if not re.fullmatch(r"\S+", args.run_id):
        parser.error("--run-id must not contain whitespace")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run = read_run(args.input_run)
        topics = {topic.qid: topic.narrative for topic in read_topics(args.topics)}
        missing_topics = sorted(set(run) - set(topics))
        if missing_topics:
            raise RetrievalError(f"Topics file is missing qids: {', '.join(missing_topics)}")
        depth = args.depth
        wanted = {qid: {item.docid for item in items[:depth]} for qid, items in run.items()}
        cache_dirs = args.document_caches or DEFAULT_DOCUMENT_CACHES
        documents = load_cached_documents(cache_dirs, wanted)
        missing = {
            qid: sorted(docids - set(documents.get(qid, {})))
            for qid, docids in wanted.items()
            if docids - set(documents.get(qid, {}))
        }
        if missing:
            sample_qid = next(iter(missing))
            raise RetrievalError(
                f"Missing cached text for {sum(map(len, missing.values()))} documents; "
                f"example topic {sample_qid}, docid {missing[sample_qid][0]}. "
                "Run retrieval with caching enabled first."
            )
        cache_name = (
            f"{args.input_run.stem}.{_safe_model_name(args.model)}."
            f"depth-{depth}.max-{args.max_length}.dtype-{args.dtype}.json"
        )
        score_cache = args.score_cache_dir / cache_name
        scores = score_candidates(
            run=run,
            topics=topics,
            documents=documents,
            input_hash=_file_sha256(args.input_run),
            model_name=args.model,
            depth=depth,
            max_length=args.max_length,
            batch_size=args.batch_size,
            device=args.device,
            dtype=args.dtype,
            cache_path=score_cache,
        )
        rows = write_run(
            args.output,
            run,
            scores,
            depth,
            args.original_weight,
            args.semantic_weight,
            args.rrf_k,
            args.run_id,
            args.output_hits,
        )
    except (OSError, RetrievalError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {rows} reranked rows for {len(run)} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
