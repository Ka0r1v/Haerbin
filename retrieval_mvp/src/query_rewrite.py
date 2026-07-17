#!/usr/bin/env python3
"""Generate and cache BM25-oriented rewrites for long TREC RAG narratives."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from retrieve import DEFAULT_TOPICS, MVP_ROOT, REPO_ROOT, RetrievalError, Topic, read_topics


PROMPT_VERSION = "bm25-rewrite-v4"
DEFAULT_CACHE = MVP_ROOT / "cache" / "rewrites"

STOPWORDS = {
    "a", "about", "after", "against", "also", "am", "an", "and", "are", "arguments", "as", "at", "be", "because",
    "been", "before", "being", "between", "both", "but", "by", "can", "could", "did", "do",
    "deeper", "differs", "does", "doing", "explain", "for", "from", "gain", "get", "give", "given", "had", "has", "have", "having",
    "help", "hoping", "how", "i", "if", "in", "including", "into", "is", "it", "its", "just", "like", "lot", "may",
    "concerning", "i'm", "interested", "me", "more", "most", "my", "need", "of", "on", "or", "our", "particularly", "please", "should", "so",
    "some", "such", "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "sides", "this", "those", "through", "to", "understand", "understanding", "us", "want", "was", "way", "we", "were",
    "what", "when", "where", "whether", "which", "while", "who", "why", "will", "with", "would",
    "you", "your",
}

PROMPT_TEMPLATE = """You generate search queries for a BM25 document retrieval system.

Given a long user narrative:
1. Produce one concise query covering the overall information need.
2. Produce exactly {subquery_count} focused sub-queries covering distinct aspects.
3. Preserve important names, organizations, places, dates, and technical terms.
4. Use concise keyword-oriented natural language.
5. Add useful synonyms only when they preserve the original intent.
6. Do not answer the question or introduce facts not present in the narrative.
7. Do not use Lucene operators or special query syntax.
8. Return valid JSON only.

Output schema:
{{
  "compressed_query": "string",
  "sub_queries": ["string"]
}}

Narrative:
{narrative}
"""


@dataclass(frozen=True)
class Rewrite:
    qid: str
    prompt_version: str
    provider_requested: str
    provider_used: str
    model: str
    original_query: str
    compressed_query: str
    sub_queries: list[str]


def _tokens(text: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'./+-]*", text)
    return [token.strip("'./+-") for token in raw_tokens if token.strip("'./+-")]


def keyword_query(text: str, max_terms: int = 16) -> str:
    selected: list[str] = []
    seen: set[str] = set()
    for token in _tokens(text):
        key = token.casefold()
        if key in STOPWORDS or len(key) == 1 or key in seen:
            continue
        seen.add(key)
        selected.append(token)
        if len(selected) >= max_terms:
            break
    return " ".join(selected)


def _candidate_aspects(narrative: str) -> list[str]:
    normalized = re.sub(
        r"\b(?:what should we weigh about|can you help me understand|i would like to know|tell me about)\b",
        " ",
        narrative,
        flags=re.IGNORECASE,
    )
    parts = re.split(
        r"[?;,]|\.(?:\s|$)|\b(?:and whether|as well as|versus|vs\.)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    return [part.strip(" ,.:!?-") for part in parts if part.strip(" ,.:!?-")]


def _jaccard(left: str, right: str) -> float:
    left_terms = {token.casefold() for token in _tokens(left)}
    right_terms = {token.casefold() for token in _tokens(right)}
    union = left_terms | right_terms
    return len(left_terms & right_terms) / len(union) if union else 1.0


def heuristic_rewrite(topic: Topic, subquery_count: int = 5) -> Rewrite:
    compressed = keyword_query(topic.narrative, max_terms=18)
    anchor_terms = compressed.split()[:3]
    candidates: list[str] = []
    for aspect in _candidate_aspects(topic.narrative):
        aspect_query = keyword_query(aspect, max_terms=10)
        if not aspect_query:
            continue
        merged_terms: list[str] = []
        merged_seen: set[str] = set()
        for term in [*anchor_terms, *aspect_query.split()]:
            key = term.casefold()
            if key not in merged_seen:
                merged_seen.add(key)
                merged_terms.append(term)
        query = " ".join(merged_terms[:12])
        if query.casefold() == " ".join(anchor_terms).casefold():
            continue
        if query.casefold() == compressed.casefold():
            continue
        if any(_jaccard(query, existing) >= 0.75 for existing in candidates):
            continue
        candidates.append(query)

    # If the prose did not split into enough aspects, create overlapping topical views.
    compressed_terms = compressed.split()
    window = max(4, min(8, len(compressed_terms) // max(subquery_count, 1) + 3))
    step = max(2, window // 2)
    for start in range(0, len(compressed_terms), step):
        query = " ".join(compressed_terms[start : start + window])
        if len(query.split()) < 2:
            continue
        if any(_jaccard(query, existing) >= 0.75 for existing in candidates):
            continue
        candidates.append(query)
        if len(candidates) >= subquery_count:
            break

    candidates = candidates[:subquery_count]
    if not compressed:
        raise RetrievalError(f"Could not derive a query for topic {topic.qid}")
    if not candidates:
        candidates = [compressed]
    return Rewrite(
        qid=topic.qid,
        prompt_version=PROMPT_VERSION,
        provider_requested="heuristic",
        provider_used="heuristic",
        model="deterministic-keyword-v4",
        original_query=topic.narrative,
        compressed_query=compressed,
        sub_queries=candidates,
    )


def _read_env_value(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    for path in (Path.cwd() / ".env.local", MVP_ROOT / ".env.local", REPO_ROOT / ".env.local"):
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8-sig") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, raw_value = line.split("=", 1)
                if key.strip() == name:
                    clean = raw_value.strip().strip('"').strip("'")
                    return clean or None
    return None


def _extract_json_object(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
    start, end = clean.find("{"), clean.rfind("}")
    if start < 0 or end < start:
        raise RetrievalError("Rewrite model did not return a JSON object.")
    try:
        payload = json.loads(clean[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RetrievalError("Rewrite model returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RetrievalError("Rewrite model JSON must be an object.")
    return payload


def _validate_generated_queries(payload: dict[str, Any], count: int) -> tuple[str, list[str]]:
    compressed = payload.get("compressed_query")
    sub_queries = payload.get("sub_queries")
    if not isinstance(compressed, str) or not compressed.strip():
        raise RetrievalError("Rewrite model omitted compressed_query.")
    if not isinstance(sub_queries, list):
        raise RetrievalError("Rewrite model omitted sub_queries.")
    cleaned: list[str] = []
    seen = {compressed.strip().casefold()}
    for item in sub_queries:
        if not isinstance(item, str):
            continue
        query = " ".join(item.split())
        key = query.casefold()
        if not query or key in seen or len(query) > 300:
            continue
        seen.add(key)
        cleaned.append(query)
    if len(cleaned) < min(3, count):
        raise RetrievalError("Rewrite model returned too few distinct sub-queries.")
    return " ".join(compressed.split()), cleaned[:count]


def llm_rewrite(
    topic: Topic,
    *,
    subquery_count: int,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
) -> Rewrite:
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return JSON only. Never answer the user's question."},
            {
                "role": "user",
                "content": PROMPT_TEMPLATE.format(
                    subquery_count=subquery_count, narrative=topic.narrative
                ),
            },
        ],
        "temperature": 0,
    }
    request = Request(
        url,
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
    except HTTPError as exc:
        raise RetrievalError(f"Rewrite endpoint returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RetrievalError(f"Could not reach rewrite endpoint: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RetrievalError("Rewrite endpoint returned invalid JSON.") from exc
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RetrievalError("Rewrite endpoint response is missing message content.") from exc
    if not isinstance(content, str):
        raise RetrievalError("Rewrite endpoint message content must be text.")
    compressed, sub_queries = _validate_generated_queries(
        _extract_json_object(content), subquery_count
    )
    return Rewrite(
        qid=topic.qid,
        prompt_version=PROMPT_VERSION,
        provider_requested="llm",
        provider_used="llm",
        model=model,
        original_query=topic.narrative,
        compressed_query=compressed,
        sub_queries=sub_queries,
    )


def rewrite_cache_path(cache_dir: Path, qid: str, provider: str) -> Path:
    safe_qid = re.sub(r"[^A-Za-z0-9_.-]+", "_", qid).strip("._") or "topic"
    return cache_dir / f"{safe_qid}.{provider}.{PROMPT_VERSION}.json"


def load_cached_rewrite(
    path: Path, topic: Topic, provider: str, subquery_count: int
) -> Rewrite | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rewrite = Rewrite(**payload)
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if (
        rewrite.qid != topic.qid
        or rewrite.original_query != topic.narrative
        or rewrite.prompt_version != PROMPT_VERSION
        or rewrite.provider_requested != provider
        or (provider == "llm" and rewrite.provider_used != "llm")
        or len(rewrite.sub_queries) < min(3, subquery_count)
    ):
        return None
    return Rewrite(**{**asdict(rewrite), "sub_queries": rewrite.sub_queries[:subquery_count]})


def save_rewrite(path: Path, rewrite: Rewrite) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(asdict(rewrite), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def create_rewrite(
    topic: Topic,
    *,
    provider: str,
    subquery_count: int,
    llm_base_url: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
    timeout: float,
    fallback_heuristic: bool,
) -> Rewrite:
    if provider == "heuristic":
        return heuristic_rewrite(topic, subquery_count)
    if not llm_base_url or not llm_api_key or not llm_model:
        if fallback_heuristic:
            fallback = heuristic_rewrite(topic, subquery_count)
            return Rewrite(**{**asdict(fallback), "provider_requested": "llm"})
        raise RetrievalError(
            "LLM rewrite requires QUERY_REWRITE_BASE_URL, QUERY_REWRITE_API_KEY, "
            "and QUERY_REWRITE_MODEL."
        )
    try:
        return llm_rewrite(
            topic,
            subquery_count=subquery_count,
            base_url=llm_base_url,
            api_key=llm_api_key,
            model=llm_model,
            timeout=timeout,
        )
    except RetrievalError:
        if not fallback_heuristic:
            raise
        fallback = heuristic_rewrite(topic, subquery_count)
        return Rewrite(**{**asdict(fallback), "provider_requested": "llm"})


def get_or_create_rewrite(
    topic: Topic,
    *,
    cache_dir: Path,
    provider: str,
    subquery_count: int,
    force: bool,
    timeout: float,
    fallback_heuristic: bool,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> Rewrite:
    path = rewrite_cache_path(cache_dir, topic.qid, provider)
    if not force:
        cached = load_cached_rewrite(path, topic, provider, subquery_count)
        if cached is not None:
            return cached
    rewrite = create_rewrite(
        topic,
        provider=provider,
        subquery_count=subquery_count,
        llm_base_url=llm_base_url or _read_env_value("QUERY_REWRITE_BASE_URL"),
        llm_api_key=llm_api_key or _read_env_value("QUERY_REWRITE_API_KEY"),
        llm_model=llm_model or _read_env_value("QUERY_REWRITE_MODEL"),
        timeout=timeout,
        fallback_heuristic=fallback_heuristic,
    )
    save_rewrite(path, rewrite)
    return rewrite


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--provider", choices=("heuristic", "llm"), default="heuristic")
    parser.add_argument("--subqueries", type=int, default=5)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--llm-base-url")
    parser.add_argument("--llm-model")
    args = parser.parse_args(argv)
    if args.subqueries <= 0:
        parser.error("--subqueries must be positive")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        topics = read_topics(args.topics)
        if args.limit is not None:
            topics = topics[: args.limit]
        for index, topic in enumerate(topics, start=1):
            rewrite = get_or_create_rewrite(
                topic,
                cache_dir=args.cache_dir,
                provider=args.provider,
                subquery_count=args.subqueries,
                force=args.force,
                timeout=args.timeout,
                fallback_heuristic=not args.no_fallback,
                llm_base_url=args.llm_base_url,
                llm_api_key=None,
                llm_model=args.llm_model,
            )
            print(
                f"[{index}/{len(topics)}] {topic.qid}: provider={rewrite.provider_used}, "
                f"subqueries={len(rewrite.sub_queries)}"
            )
    except (OSError, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
