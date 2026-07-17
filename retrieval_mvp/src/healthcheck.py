#!/usr/bin/env python3
"""Check the Pyserini server and, when available, the local API token."""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from retrieve import DEFAULT_BASE_URL, DEFAULT_INDEX, RetrievalError, load_token, search_api


def main() -> int:
    try:
        request = Request(f"{DEFAULT_BASE_URL}/", headers={"Accept": "application/json"})
        with urlopen(request, timeout=15) as response:
            root = json.load(response)
        if not isinstance(root, dict) or root.get("name") != "Pyserini API":
            print("ERROR: unexpected server response", file=sys.stderr)
            return 1
        print(f"Server OK: {root.get('name')} {root.get('version', '')}".rstrip())
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        print(f"ERROR: server health check failed: {exc}", file=sys.stderr)
        return 1

    try:
        token = load_token()
    except RetrievalError:
        print("Token not found: server connectivity passed; authenticated search was skipped.")
        return 0

    try:
        payload = search_api(
            base_url=DEFAULT_BASE_URL,
            index=DEFAULT_INDEX,
            query="Albert Einstein",
            hits=1,
            token=token,
            timeout=15,
            retries=0,
        )
    except RetrievalError as exc:
        print(f"ERROR: authenticated search failed: {exc}", file=sys.stderr)
        return 1
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        print("ERROR: authenticated search returned no candidates", file=sys.stderr)
        return 1
    first = candidates[0]
    print(f"Authenticated search OK: index={DEFAULT_INDEX}, first_docid={first.get('docid')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
