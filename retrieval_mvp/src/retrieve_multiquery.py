#!/usr/bin/env python3
"""Retrieve with original/rewritten queries and fuse rankings with RRF."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from query_rewrite import DEFAULT_CACHE as DEFAULT_REWRITE_CACHE
from query_rewrite import Rewrite, get_or_create_rewrite
from retrieve import (
    DEFAULT_BASE_URL,
    DEFAULT_INDEX,
    DEFAULT_TOPICS,
    MVP_ROOT,
    RetrievalError,
    Topic,
    load_cached_response,
    load_token,
    normalize_candidates,
    read_topics,
    save_cached_response,
    search_api,
    write_run,
)
from rrf import reciprocal_rank_fusion


DEFAULT_OUTPUT = MVP_ROOT / "runs" / "haerbin-multiquery-rrf-dev.tsv"
DEFAULT_SEARCH_CACHE = MVP_ROOT / "cache" / "multiquery_search"


def build_query_routes(rewrite: Rewrite, mode: str) -> list[tuple[str, str]]:
    if mode == "original":
        candidates = [("original", rewrite.original_query)]
    elif mode == "compressed":
        candidates = [("compressed", rewrite.compressed_query)]
    elif mode == "subqueries":
        candidates = [("subquery", query) for query in rewrite.sub_queries]
    elif mode == "all":
        candidates = [
            ("original", rewrite.original_query),
            ("compressed", rewrite.compressed_query),
            *(("subquery", query) for query in rewrite.sub_queries),
        ]
    else:
        raise ValueError(f"Unknown query mode: {mode}")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for route, query in candidates:
        clean = " ".join(query.split())
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append((route, clean))
    if not result:
        raise RetrievalError(f"No usable queries for topic {rewrite.qid}")
    return result


def build_queries(rewrite: Rewrite, mode: str) -> list[str]:
    """Backward-compatible text-only view used by callers and tests."""
    return [query for _, query in build_query_routes(rewrite, mode)]


def query_cache_path(cache_dir: Path, qid: str, query: str) -> Path:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    safe_qid = "".join(character if character.isalnum() or character in "_.-" else "_" for character in qid)
    return cache_dir / safe_qid / f"{digest}.json"


def read_baseline_run(path: Path) -> dict[str, list[str]]:
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            fields = line.split()
            if len(fields) != 6:
                raise RetrievalError(f"{path}:{line_number}: expected 6 run fields")
            qid, _, docid, rank_text, _, _ = fields
            try:
                rank = int(rank_text)
            except ValueError as exc:
                raise RetrievalError(f"{path}:{line_number}: invalid rank") from exc
            grouped[qid].append((rank, docid))
    return {
        qid: [docid for _, docid in sorted(rows)] for qid, rows in grouped.items()
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rewrite-cache-dir", type=Path, default=DEFAULT_REWRITE_CACHE)
    parser.add_argument("--search-cache-dir", type=Path, default=DEFAULT_SEARCH_CACHE)
    parser.add_argument("--provider", choices=("heuristic", "llm"), default="heuristic")
    parser.add_argument("--query-mode", choices=("original", "compressed", "subqueries", "all"), default="all")
    parser.add_argument("--subqueries", type=int, default=5)
    parser.add_argument("--hits-per-query", type=int, default=200)
    parser.add_argument("--output-hits", type=int, default=1000)
    parser.add_argument("--rrf-k", type=float, default=60.0)
    parser.add_argument("--baseline-run", type=Path, help="Optional full BM25 run used as a weighted safety ranking.")
    parser.add_argument("--baseline-weight", type=float, default=1.0)
    parser.add_argument("--rewrite-weight", type=float, default=1.0)
    parser.add_argument(
        "--compressed-weight",
        type=float,
        help="Optional RRF weight for the compressed query; defaults to --rewrite-weight.",
    )
    parser.add_argument(
        "--subquery-weight",
        type=float,
        help="Optional RRF weight for each decomposed subquery; defaults to --rewrite-weight.",
    )
    parser.add_argument("--run-id", default="haerbin-multiquery-rrf")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--force-rewrite", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--llm-base-url")
    parser.add_argument("--llm-model")
    args = parser.parse_args(argv)
    for name in ("subqueries", "hits_per_query", "output_hits"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.rrf_k <= 0:
        parser.error("--rrf-k must be positive")
    if args.baseline_weight <= 0 or args.rewrite_weight <= 0:
        parser.error("RRF weights must be positive")
    if args.compressed_weight is not None and args.compressed_weight <= 0:
        parser.error("--compressed-weight must be positive")
    if args.subquery_weight is not None and args.subquery_weight <= 0:
        parser.error("--subquery-weight must be positive")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        topics = read_topics(args.topics)
        if args.limit is not None:
            topics = topics[: args.limit]
        token = load_token()
        baseline_rankings = read_baseline_run(args.baseline_run) if args.baseline_run else {}
        rewrite_by_qid: dict[str, Rewrite] = {}

        for index, topic in enumerate(topics, start=1):
            rewrite = get_or_create_rewrite(
                topic,
                cache_dir=args.rewrite_cache_dir,
                provider=args.provider,
                subquery_count=args.subqueries,
                force=args.force_rewrite,
                timeout=args.timeout,
                fallback_heuristic=not args.no_fallback,
                llm_base_url=args.llm_base_url,
                llm_api_key=None,
                llm_model=args.llm_model,
            )
            rewrite_by_qid[topic.qid] = rewrite
            print(
                f"rewrite [{index}/{len(topics)}] {topic.qid}: "
                f"provider={rewrite.provider_used}, queries={len(build_queries(rewrite, args.query_mode))}"
            )

        def retrieve_and_fuse(topic: Topic) -> dict[str, Any]:
            rewrite = rewrite_by_qid[topic.qid]
            routes = build_query_routes(rewrite, args.query_mode)
            rankings: list[list[str]] = []
            weights: list[float] = []
            baseline_ranking = baseline_rankings.get(topic.qid)
            if baseline_ranking:
                rankings.append(baseline_ranking)
                weights.append(args.baseline_weight)
                if args.query_mode in ("original", "all"):
                    routes = [
                        (route, query)
                        for route, query in routes
                        if query.casefold() != rewrite.original_query.casefold()
                    ]
            route_weights = {
                "original": args.rewrite_weight,
                "compressed": args.compressed_weight or args.rewrite_weight,
                "subquery": args.subquery_weight or args.rewrite_weight,
            }
            for query_index, (route, query) in enumerate(routes, start=1):
                query_topic = Topic(qid=topic.qid, narrative=query)
                cache_path = query_cache_path(args.search_cache_dir, topic.qid, query)
                response = None
                if not args.no_cache:
                    response = load_cached_response(
                        cache_path, query_topic, args.hits_per_query
                    )
                if response is None:
                    response = search_api(
                        base_url=args.base_url,
                        index=args.index,
                        query=query,
                        hits=args.hits_per_query,
                        token=token,
                        timeout=args.timeout,
                        retries=args.retries,
                    )
                    if not args.no_cache:
                        save_cached_response(
                            cache_path, query_topic, args.hits_per_query, response
                        )
                candidates = normalize_candidates(response, args.hits_per_query)
                rankings.append([candidate.docid for candidate in candidates])
                weights.append(route_weights[route])
                print(
                    f"  {topic.qid} query {query_index}/{len(routes)}: "
                    f"route={route}, weight={route_weights[route]:g}, "
                    f"candidates={len(candidates)}"
                )
            fused = reciprocal_rank_fusion(
                rankings, k=args.rrf_k, limit=args.output_hits, weights=weights
            )
            return {
                "candidates": [
                    {"docid": item.docid, "score": item.score} for item in fused
                ]
            }

        topic_count, row_count = write_run(
            topics,
            args.output,
            args.run_id,
            args.output_hits,
            retrieve_and_fuse,
        )
    except (OSError, RetrievalError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {row_count} fused rows for {topic_count} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
