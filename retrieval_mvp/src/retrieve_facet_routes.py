#!/usr/bin/env python3
"""Retrieve with diverse typed query routes generated from the topic only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from query_rewrite import _extract_json_object, _read_env_value, _tokens
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
from retrieve_multiquery import query_cache_path, read_baseline_run
from rrf import reciprocal_rank_fusion


PROMPT_VERSION = "typed-facet-routes-v1"
DEFAULT_BASELINE = MVP_ROOT / "runs" / "haerbin-bm25-dev.tsv"
DEFAULT_OUTPUT = MVP_ROOT / "runs" / "facet-routes-v1-dev.tsv"
DEFAULT_ROUTE_CACHE = MVP_ROOT / "cache" / "facet_routes"
DEFAULT_SEARCH_CACHE = MVP_ROOT / "cache" / "multiquery_search"
ALLOWED_TYPES = {"facet", "terminology", "entity_alias", "temporal", "geographic"}

PROMPT = """Generate diverse ordinary-text queries for a BM25 document retrieval system.

The routes must cover different retrieval failure modes, not paraphrase one another:
- facet: isolate one distinct information need, mechanism, consequence, argument, or evidence type;
- terminology: use technical/legal/scientific terms, acronyms, or common domain wording supported by the topic;
- entity_alias: use an explicit abbreviation, alternate name, or expanded entity form only when supported by the topic;
- temporal: isolate a date, period, chronology, historical phase, or recency need only when applicable;
- geographic: isolate a place, jurisdiction, region, or comparative geography only when applicable.

Requirements:
1. Produce 3 facet routes and 2 terminology routes.
2. Add at most one route for each of entity_alias, temporal, and geographic when it is genuinely applicable.
3. Every query must preserve the original intent and include enough topic anchors to stand alone.
4. Do not answer the topic, invent facts, or use facts not present in the topic.
5. Do not use Boolean operators, quotes, field syntax, or other Lucene syntax.
6. Avoid near-duplicate wording. Each query must target a different vocabulary or information facet.
7. Keep each query under 24 words.
8. Return JSON only.

Schema:
{{
  "routes": [
    {{"type": "facet|terminology|entity_alias|temporal|geographic", "query": "ordinary text query"}}
  ]
}}

Topic:
{narrative}
"""


@dataclass(frozen=True)
class FacetRoute:
    route_type: str
    query: str


def lexical_jaccard(left: str, right: str) -> float:
    left_terms = {token.casefold() for token in _tokens(left)}
    right_terms = {token.casefold() for token in _tokens(right)}
    union = left_terms | right_terms
    return len(left_terms & right_terms) / len(union) if union else 1.0


def validate_routes(payload: dict[str, Any]) -> list[FacetRoute]:
    raw_routes = payload.get("routes")
    if not isinstance(raw_routes, list):
        raise RetrievalError("Facet route model omitted routes.")
    routes: list[FacetRoute] = []
    seen: set[str] = set()
    type_counts: dict[str, int] = {}
    for item in raw_routes:
        if not isinstance(item, dict):
            continue
        route_type = item.get("type")
        query = item.get("query")
        if route_type not in ALLOWED_TYPES or not isinstance(query, str):
            continue
        clean = " ".join(query.split())
        key = clean.casefold()
        if not clean or len(clean.split()) > 24 or key in seen:
            continue
        if any(lexical_jaccard(clean, existing.query) >= 0.72 for existing in routes):
            continue
        if route_type in {"entity_alias", "temporal", "geographic"} and type_counts.get(route_type, 0) >= 1:
            continue
        if route_type == "facet" and type_counts.get(route_type, 0) >= 3:
            continue
        if route_type == "terminology" and type_counts.get(route_type, 0) >= 2:
            continue
        routes.append(FacetRoute(route_type=route_type, query=clean))
        seen.add(key)
        type_counts[route_type] = type_counts.get(route_type, 0) + 1
    if type_counts.get("facet", 0) < 2 or type_counts.get("terminology", 0) < 1:
        raise RetrievalError("Facet route model returned too few diverse facet/terminology routes.")
    return routes


def cache_path(cache_dir: Path, topic: Topic) -> Path:
    safe_qid = re.sub(r"[^A-Za-z0-9_.-]+", "_", topic.qid).strip("._") or "topic"
    digest = hashlib.sha256(topic.narrative.encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"{safe_qid}.{PROMPT_VERSION}.{digest}.json"


def generate_routes(topic: Topic, *, timeout: float, force: bool, cache_dir: Path) -> list[FacetRoute]:
    path = cache_path(cache_dir, topic)
    if path.is_file() and not force:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            return validate_routes(cached)
        except (OSError, json.JSONDecodeError, RetrievalError):
            pass
    base_url = _read_env_value("QUERY_REWRITE_BASE_URL")
    api_key = _read_env_value("QUERY_REWRITE_API_KEY")
    model = _read_env_value("QUERY_REWRITE_MODEL")
    if not base_url or not api_key or not model:
        raise RetrievalError("Typed route generation requires the local query rewrite API configuration.")
    prompt = PROMPT.format(narrative=topic.narrative)
    last_error: Exception | None = None
    for attempt in range(3):
        repair = "" if attempt == 0 else "\nReturn one valid JSON object only and preserve route diversity."
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return valid JSON only. Do not answer the topic."},
                {"role": "user", "content": prompt + repair},
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
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.load(response)
            content = result["choices"][0]["message"]["content"]
            payload = _extract_json_object(content)
            routes = validate_routes(payload)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"routes": [{"type": route.route_type, "query": route.query} for route in routes]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return routes
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise RetrievalError("Typed route generation authentication failed.") from exc
            last_error = exc
        except (URLError, KeyError, IndexError, TypeError, json.JSONDecodeError, RetrievalError) as exc:
            last_error = exc
    raise RetrievalError(f"Could not generate valid typed routes for topic {topic.qid}.") from last_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--baseline-run", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--route-cache", type=Path, default=DEFAULT_ROUTE_CACHE)
    parser.add_argument("--search-cache", type=Path, default=DEFAULT_SEARCH_CACHE)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--hits-per-query", type=int, default=1000)
    parser.add_argument("--output-hits", type=int, default=5000)
    parser.add_argument("--rrf-k", type=float, default=60)
    parser.add_argument("--baseline-weight", type=float, default=4)
    parser.add_argument("--facet-weight", type=float, default=1.5)
    parser.add_argument("--terminology-weight", type=float, default=1.25)
    parser.add_argument("--entity-weight", type=float, default=1)
    parser.add_argument("--temporal-weight", type=float, default=1)
    parser.add_argument("--geographic-weight", type=float, default=1)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force-routes", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--route-types",
        nargs="+",
        choices=sorted(ALLOWED_TYPES),
        help="Optional route-type subset for cached ablations; defaults to all types.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run-id", default="haerbin-facet-routes-v1")
    args = parser.parse_args(argv)
    positive = [
        args.hits_per_query,
        args.output_hits,
        args.rrf_k,
        args.baseline_weight,
        args.facet_weight,
        args.terminology_weight,
        args.entity_weight,
        args.temporal_weight,
        args.geographic_weight,
    ]
    if any(value <= 0 for value in positive):
        parser.error("hits, depths, RRF k, and weights must be positive")
    try:
        topics = read_topics(args.topics)
        if args.limit:
            topics = topics[: args.limit]
        baseline = read_baseline_run(args.baseline_run)
        token = load_token()
        routes_by_qid: dict[str, list[FacetRoute]] = {}
        for index, topic in enumerate(topics, start=1):
            routes = generate_routes(
                topic, timeout=args.timeout, force=args.force_routes, cache_dir=args.route_cache
            )
            if args.route_types:
                selected_types = set(args.route_types)
                routes = [route for route in routes if route.route_type in selected_types]
            if not routes:
                raise RetrievalError(f"No selected typed routes remain for topic {topic.qid}")
            routes_by_qid[topic.qid] = routes
            counts: dict[str, int] = {}
            for route in routes:
                counts[route.route_type] = counts.get(route.route_type, 0) + 1
            print(f"routes [{index}/{len(topics)}] qid={topic.qid} counts={counts}")

        weights_by_type = {
            "facet": args.facet_weight,
            "terminology": args.terminology_weight,
            "entity_alias": args.entity_weight,
            "temporal": args.temporal_weight,
            "geographic": args.geographic_weight,
        }

        def retrieve(topic: Topic) -> dict[str, Any]:
            rankings: list[list[str]] = [baseline[topic.qid]]
            weights: list[float] = [args.baseline_weight]
            for route_index, route in enumerate(routes_by_qid[topic.qid], start=1):
                route_topic = Topic(qid=topic.qid, narrative=route.query)
                path = query_cache_path(args.search_cache, topic.qid, route.query)
                response = None if args.no_cache else load_cached_response(path, route_topic, args.hits_per_query)
                if response is None:
                    response = search_api(
                        base_url=args.base_url,
                        index=args.index,
                        query=route.query,
                        hits=args.hits_per_query,
                        token=token,
                        timeout=args.timeout,
                        retries=args.retries,
                    )
                    if not args.no_cache:
                        save_cached_response(path, route_topic, args.hits_per_query, response)
                candidates = normalize_candidates(response, args.hits_per_query)
                rankings.append([candidate.docid for candidate in candidates])
                weights.append(weights_by_type[route.route_type])
                print(
                    f"  {topic.qid} route {route_index}/{len(routes_by_qid[topic.qid])}: "
                    f"type={route.route_type}, candidates={len(candidates)}"
                )
            fused = reciprocal_rank_fusion(
                rankings, k=args.rrf_k, limit=args.output_hits, weights=weights
            )
            return {"candidates": [{"docid": item.docid, "score": item.score} for item in fused]}

        topic_count, row_count = write_run(
            topics, args.output, args.run_id, args.output_hits, retrieve
        )
    except (OSError, RetrievalError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {row_count} rows for {topic_count} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
