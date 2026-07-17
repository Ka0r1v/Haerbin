#!/usr/bin/env python3
"""Listwise LLM reranking with query-aware document compression and strict repair."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from query_rewrite import STOPWORDS, _extract_json_object, _read_env_value
from rerank import DEFAULT_DOCUMENT_CACHES, _file_sha256, load_cached_documents, read_run, write_run
from retrieve import DEFAULT_TOPICS, MVP_ROOT, RetrievalError, read_topics


DEFAULT_INPUT = MVP_ROOT / "runs" / "colbert-top100-o8.tsv"
DEFAULT_OUTPUT = MVP_ROOT / "runs" / "rankllm-top20.tsv"
DEFAULT_CACHE = MVP_ROOT / "cache" / "rankllm"
COMPRESSION_VERSION = "sentence-overlap-v1"


def _terms(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", text)
        if len(token) > 1 and token.casefold() not in STOPWORDS
    }


def compress_document(query: str, document: str, max_chars: int = 900) -> str:
    clean = " ".join(document.split())
    if len(clean) <= max_chars:
        return clean
    query_terms = _terms(query)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", clean)
        if sentence.strip()
    ]
    if not sentences:
        return clean[:max_chars]
    ranked = sorted(
        enumerate(sentences),
        key=lambda pair: (
            -len(query_terms & _terms(pair[1])),
            pair[0],
        ),
    )
    selected: list[tuple[int, str]] = []
    used = 0
    for index, sentence in ranked:
        remaining = max_chars - used
        if remaining <= 0:
            break
        fragment = sentence[:remaining]
        selected.append((index, fragment))
        used += len(fragment) + 1
        if used >= max_chars:
            break
    return " ".join(sentence for _, sentence in sorted(selected))[:max_chars]


def validate_ranking(payload: dict[str, Any], labels: list[str]) -> list[str]:
    ranking = payload.get("ranking")
    if not isinstance(ranking, list):
        raise RetrievalError("RankLLM response omitted ranking array")
    allowed = set(labels)
    repaired: list[str] = []
    seen: set[str] = set()
    for value in ranking:
        label = str(value).strip().upper()
        if label in allowed and label not in seen:
            seen.add(label)
            repaired.append(label)
    repaired.extend(label for label in labels if label not in seen)
    if len(repaired) != len(labels):
        raise RetrievalError("RankLLM ranking repair failed")
    return repaired


def call_rankllm(
    *,
    query: str,
    documents: list[str],
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    retries: int,
) -> list[int]:
    labels = [f"D{index}" for index in range(1, len(documents) + 1)]
    passages = "\n\n".join(
        f"[{label}] {document}" for label, document in zip(labels, documents)
    )
    prompt = f"""Rank the candidate passages by relevance to the information need.
Judge direct topical relevance, coverage of the requested aspects, factual specificity, and usefulness as evidence.
Do not answer the question. Use every candidate label exactly once.
Return JSON only in this form: {{"ranking":["D3","D1",...]}}.

Information need:
{query}

Candidate passages:
{passages}
"""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a strict listwise retrieval reranker. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.load(response)
            content = result["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise RetrievalError("RankLLM returned non-text content")
            ranking = validate_ranking(_extract_json_object(content), labels)
            return [labels.index(label) for label in ranking]
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, RetrievalError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
    raise RetrievalError(f"RankLLM request failed after retries: {last_error}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_run", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--document-cache", action="append", type=Path, dest="document_caches")
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--max-document-chars", type=int, default=900)
    parser.add_argument("--original-weight", type=float, default=8.0)
    parser.add_argument("--rankllm-weight", type=float, default=1.0)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--run-id", default="haerbin-rankllm-top20")
    args = parser.parse_args(argv)
    if min(args.depth, args.max_document_chars) <= 0:
        parser.error("--depth and --max-document-chars must be positive")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.original_weight < 0 or args.rankllm_weight <= 0 or args.rrf_k < 0:
        parser.error("weights must be non-negative and RankLLM weight positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run = read_run(args.input_run)
        if args.limit is not None:
            run = dict(list(run.items())[: args.limit])
        topics = {topic.qid: topic.narrative for topic in read_topics(args.topics)}
        wanted = {qid: {item.docid for item in items[: args.depth]} for qid, items in run.items()}
        documents = load_cached_documents(args.document_caches or DEFAULT_DOCUMENT_CACHES, wanted)
        missing = sum(len(docids - set(documents.get(qid, {}))) for qid, docids in wanted.items())
        if missing:
            raise RetrievalError(f"Missing cached text for {missing} RankLLM candidates")
        base_url = args.base_url or _read_env_value("QUERY_REWRITE_BASE_URL")
        api_key = _read_env_value("QUERY_REWRITE_API_KEY")
        model = args.model or _read_env_value("QUERY_REWRITE_MODEL")
        if not base_url or not api_key or not model:
            raise RetrievalError("RankLLM requires the configured DeepSeek rewrite endpoint and key")

        input_hash = _file_sha256(args.input_run)
        semantic_scores: dict[str, dict[str, float]] = {}
        for index, (qid, items) in enumerate(run.items(), start=1):
            cache_key = hashlib.sha256(
                f"{input_hash}|{qid}|{model}|{args.depth}|{args.max_document_chars}|{COMPRESSION_VERSION}".encode()
            ).hexdigest()[:20]
            cache_path = args.cache_dir / qid / f"{cache_key}.json"
            ranking_indices: list[int] | None = None
            if cache_path.is_file():
                try:
                    payload = json.loads(cache_path.read_text(encoding="utf-8"))
                    candidate = payload.get("ranking_indices")
                    if isinstance(candidate, list) and sorted(candidate) == list(range(min(args.depth, len(items)))):
                        ranking_indices = candidate
                except (OSError, json.JSONDecodeError):
                    pass
            head = items[: args.depth]
            if ranking_indices is None:
                compressed = [
                    compress_document(topics[qid], documents[qid][item.docid], args.max_document_chars)
                    for item in head
                ]
                ranking_indices = call_rankllm(
                    query=topics[qid],
                    documents=compressed,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout=args.timeout,
                    retries=args.retries,
                )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({"qid": qid, "model": model, "ranking_indices": ranking_indices}),
                    encoding="utf-8",
                )
            semantic_scores[qid] = {
                head[item_index].docid: float(len(head) - rank)
                for rank, item_index in enumerate(ranking_indices)
            }
            print(f"[{index}/{len(run)}] RankLLM-ranked {qid}: {len(head)} documents")
        rows = write_run(
            args.output,
            run,
            semantic_scores,
            args.depth,
            args.original_weight,
            args.rankllm_weight,
            args.rrf_k,
            args.run_id,
        )
    except (OSError, RetrievalError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {rows} RankLLM rows for {len(run)} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
