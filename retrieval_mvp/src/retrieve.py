#!/usr/bin/env python3
"""Run the unmodified hosted Pyserini/ClimbMix retrieval baseline."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MVP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MVP_ROOT.parent
DEFAULT_TOPICS = MVP_ROOT / "data" / "topics" / "rag25-topics-dev.tsv"
DEFAULT_OUTPUT = MVP_ROOT / "runs" / "haerbin-bm25-dev.tsv"
DEFAULT_CACHE = MVP_ROOT / "cache" / "search"
DEFAULT_BASE_URL = "http://api.castorini.uwaterloo.ca"
DEFAULT_INDEX = "climbmix-400b"


class RetrievalError(RuntimeError):
    """A safe-to-display retrieval failure."""


@dataclass(frozen=True)
class Topic:
    qid: str
    narrative: str


@dataclass(frozen=True)
class Candidate:
    docid: str
    score: float


def read_topics(path: Path) -> list[Topic]:
    topics: list[Topic] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            if "\t" not in line:
                raise RetrievalError(f"{path}:{line_number}: expected qid<TAB>narrative")
            qid, narrative = line.split("\t", 1)
            qid, narrative = qid.strip(), narrative.strip()
            if not qid or not narrative:
                raise RetrievalError(f"{path}:{line_number}: qid and narrative must be non-empty")
            if qid in seen:
                raise RetrievalError(f"{path}:{line_number}: duplicate qid {qid!r}")
            seen.add(qid)
            topics.append(Topic(qid=qid, narrative=narrative))
    if not topics:
        raise RetrievalError(f"No topics found in {path}")
    return topics


def _read_token_from_env_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8-sig") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "PYSERINI_API_TOKEN":
                value = value.strip().strip('"').strip("'")
                return value or None
    return None


def load_token() -> str:
    token = os.environ.get("PYSERINI_API_TOKEN", "").strip()
    if token:
        return token
    candidates = [Path.cwd() / ".env.local", MVP_ROOT / ".env.local", REPO_ROOT / ".env.local"]
    checked: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in checked:
            continue
        checked.add(resolved)
        token = _read_token_from_env_file(resolved)
        if token:
            return token
    raise RetrievalError(
        "PYSERINI_API_TOKEN is missing. Put it in the repository-root .env.local; "
        "do not commit or print the token."
    )


def request_json(url: str, token: str, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "haerbin-retrieval-mvp/1.0",
            "X-API-Key": token,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RetrievalError("Pyserini authentication failed; the local token is missing or invalid.") from exc
        raise RetrievalError(f"Pyserini returned HTTP {exc.code} for the search request.") from exc
    except URLError as exc:
        raise RetrievalError(f"Could not reach Pyserini: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RetrievalError("Pyserini returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RetrievalError("Pyserini response must be a JSON object.")
    return payload


def search_api(
    *,
    base_url: str,
    index: str,
    query: str,
    hits: int,
    token: str,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    params = urlencode({"query": query, "hits": hits})
    url = f"{base_url.rstrip('/')}/v1/{index}/search?{params}"
    for attempt in range(retries + 1):
        try:
            return request_json(url, token, timeout)
        except RetrievalError:
            if attempt >= retries:
                raise
            time.sleep(min(2**attempt, 8))
    raise AssertionError("unreachable")


def normalize_candidates(payload: dict[str, Any], hits: int) -> list[Candidate]:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise RetrievalError("Pyserini response is missing a candidates array.")
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_candidates, start=1):
        if not isinstance(item, dict):
            raise RetrievalError(f"Candidate {index} is not an object.")
        docid = item.get("docid")
        score = item.get("score")
        if not isinstance(docid, str) or not docid or any(char.isspace() for char in docid):
            raise RetrievalError(f"Candidate {index} has an invalid docid.")
        if docid in seen:
            continue
        try:
            numeric_score = float(score)
        except (TypeError, ValueError) as exc:
            raise RetrievalError(f"Candidate {index} has an invalid score.") from exc
        seen.add(docid)
        candidates.append(Candidate(docid=docid, score=numeric_score))
        if len(candidates) >= hits:
            break
    if not candidates:
        raise RetrievalError("Pyserini returned no candidates.")
    return candidates


def _cache_path(cache_dir: Path, qid: str) -> Path:
    safe_qid = re.sub(r"[^A-Za-z0-9_.-]+", "_", qid).strip("._") or "topic"
    return cache_dir / f"{safe_qid}.json"


def load_cached_response(cache_path: Path, topic: Topic, hits: int) -> dict[str, Any] | None:
    if not cache_path.is_file():
        return None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(cached, dict):
        return None
    if cached.get("qid") != topic.qid or cached.get("query") != topic.narrative:
        return None
    if int(cached.get("hits", 0)) < hits:
        return None
    response = cached.get("response")
    return response if isinstance(response, dict) else None


def save_cached_response(
    cache_path: Path, topic: Topic, hits: int, response: dict[str, Any]
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"qid": topic.qid, "query": topic.narrative, "hits": hits, "response": response},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(cache_path)


SearchFunction = Callable[[Topic], dict[str, Any]]


def write_run(
    topics: Iterable[Topic],
    output: Path,
    run_id: str,
    hits: int,
    search: SearchFunction,
) -> tuple[int, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    topic_count = 0
    row_count = 0
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for topic in topics:
                candidates = normalize_candidates(search(topic), hits)
                for rank, candidate in enumerate(candidates, start=1):
                    stream.write(
                        f"{topic.qid} Q0 {candidate.docid} {rank} "
                        f"{candidate.score:.12g} {run_id}\n"
                    )
                    row_count += 1
                topic_count += 1
                print(f"[{topic_count}] {topic.qid}: {len(candidates)} candidates")
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return topic_count, row_count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--run-id", default="haerbin-bm25")
    parser.add_argument("--hits", type=int, default=1000)
    parser.add_argument("--limit", type=int, help="Only run the first N topics (smoke tests).")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)
    if args.hits <= 0:
        parser.error("--hits must be positive")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.retries < 0:
        parser.error("--retries cannot be negative")
    if not re.fullmatch(r"\S+", args.run_id):
        parser.error("--run-id must not contain whitespace")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        topics = read_topics(args.topics)
        if args.limit is not None:
            topics = topics[: args.limit]
        token = load_token()

        def retrieve(topic: Topic) -> dict[str, Any]:
            cache_path = _cache_path(args.cache_dir, topic.qid)
            if not args.no_cache:
                cached = load_cached_response(cache_path, topic, args.hits)
                if cached is not None:
                    return cached
            response = search_api(
                base_url=args.base_url,
                index=args.index,
                query=topic.narrative,
                hits=args.hits,
                token=token,
                timeout=args.timeout,
                retries=args.retries,
            )
            if not args.no_cache:
                save_cached_response(cache_path, topic, args.hits, response)
            return response

        topic_count, row_count = write_run(topics, args.output, args.run_id, args.hits, retrieve)
    except (OSError, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {row_count} rows for {topic_count} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
