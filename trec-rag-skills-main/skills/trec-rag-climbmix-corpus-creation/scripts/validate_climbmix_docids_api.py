#!/usr/bin/env python3
"""Validate generated ClimbMix docids against the hosted Pyserini REST API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from create_climbmix_corpus import compact_text, expand_inputs, iter_corpus_rows


DEFAULT_BASE_URL = "http://api.castorini.uwaterloo.ca"
DEFAULT_INDEX = "climbmix-400b"
AUTH_HEADER_RE = re.compile(r"Authorization:\s*([^\"'\n]+)", re.IGNORECASE)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def auth_header_from_curlrc(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    match = AUTH_HEADER_RE.search(text)
    if not match:
        return None
    return match.group(1).strip()


def resolve_auth_header(args: argparse.Namespace) -> str:
    if args.no_auth:
        return ""

    if args.curlrc:
        header = auth_header_from_curlrc(Path(args.curlrc))
        if header:
            return header

    token = os.environ.get(args.token_env)
    if not token and args.env_file:
        token = parse_env_file(Path(args.env_file)).get(args.token_env)

    if token:
        token = token.strip()
        if token.lower().startswith("bearer "):
            return token
        return f"Bearer {token}"

    default_curlrc = Path(".curlrc.pyserini-rest")
    header = auth_header_from_curlrc(default_curlrc)
    if header:
        return header

    raise SystemExit(
        f"no API token found. Set {args.token_env}, provide --env-file, "
        "or provide --curlrc .curlrc.pyserini-rest."
    )


def extract_doc_text(doc: Any) -> str:
    if isinstance(doc, str):
        try:
            parsed = json.loads(doc)
        except json.JSONDecodeError:
            return doc
        return extract_doc_text(parsed)
    if isinstance(doc, dict):
        for field in ("text", "contents", "content", "body", "doc"):
            value = doc.get(field)
            if isinstance(value, str):
                return value
        return json.dumps(doc, ensure_ascii=False, sort_keys=True)
    return "" if doc is None else str(doc)


def fetch_doc(base_url: str, index: str, docid: str, auth_header: str, timeout: float) -> dict:
    url = f"{base_url.rstrip('/')}/v1/{quote(index)}/doc/{quote(docid, safe='')}"
    headers = {"Accept": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:240]}") from e
    except URLError as e:
        raise RuntimeError(f"request failed: {e.reason}") from e
    return json.loads(body)


def sampled_records(args: argparse.Namespace) -> list[dict]:
    paths = expand_inputs(args.inputs)
    if not paths:
        raise SystemExit("no Parquet files found")

    only_rows = set(args.row) if args.row is not None else None
    records: list[dict] = []
    for path in paths:
        for record in iter_corpus_rows(
            path,
            preferred_id_field=args.id_field,
            preferred_text_field=args.text_field,
            only_rows=only_rows,
        ):
            records.append(record)
            if len(records) >= args.sample_size:
                return records
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spot-check locally generated ClimbMix docids/text against the hosted Pyserini REST API."
    )
    parser.add_argument("inputs", nargs="+", help="Parquet files, directories, or glob patterns.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Pyserini REST API base URL.")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Pyserini REST index name.")
    parser.add_argument("--sample-size", type=int, default=10, help="Number of local rows to check.")
    parser.add_argument("--row", type=int, action="append", help="Only sample this zero-based row number. Repeatable.")
    parser.add_argument("--id-field", default="id", help="Preferred id field before Anserini's fallback candidates.")
    parser.add_argument("--text-field", help="Text field to use locally. Defaults to text/contents/content/body.")
    parser.add_argument("--token-env", default="PYSERINI_API_TOKEN", help="Environment variable containing the API token.")
    parser.add_argument("--env-file", default=".env.local", help="Optional env file containing the API token.")
    parser.add_argument("--curlrc", help="Optional curlrc file containing an Authorization header.")
    parser.add_argument("--no-auth", action="store_true", help="Send requests without an Authorization header.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between API requests.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.sample_size <= 0:
        raise SystemExit("--sample-size must be positive")

    auth_header = resolve_auth_header(args)
    records = sampled_records(args)
    if not records:
        raise SystemExit("no sample records found")

    failures = 0
    for record in records:
        docid = record["id"]
        local_text = record["contents"]
        try:
            payload = fetch_doc(args.base_url, args.index, docid, auth_header, args.timeout)
            remote_docid = payload.get("docid")
            remote_text = extract_doc_text(payload.get("doc"))
            docid_match = remote_docid == docid
            text_match = remote_text == local_text
            compact_match = compact_text(remote_text) == compact_text(local_text)
            ok = docid_match and (text_match or compact_match)
            status = "PASS" if ok else "FAIL"
            print(
                f"{status}\t{docid}\tdocid_match={docid_match}\t"
                f"text_match={text_match}\tcompact_text_match={compact_match}"
            )
            if not ok:
                failures += 1
                print(f"  local:  {compact_text(local_text)[:160]}")
                print(f"  remote: {compact_text(remote_text)[:160]}")
        except Exception as e:
            failures += 1
            print(f"FAIL\t{docid}\terror={e}")

        if args.sleep > 0:
            time.sleep(args.sleep)

    print(f"checked={len(records)} failures={failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
