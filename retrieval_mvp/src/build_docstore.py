#!/usr/bin/env python3
"""Build a reusable SQLite docid-to-text store from cached Pyserini responses."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from rerank import (
    DEFAULT_DOCUMENT_CACHES,
    DEFAULT_DOCUMENT_STORE,
    extract_document_text,
    read_run,
)
from retrieve import MVP_ROOT, RetrievalError


DEFAULT_RUN = MVP_ROOT / "runs" / "deepseek-deep5000.tsv"


def build_store(run_path: Path, cache_dirs: list[Path], database: Path) -> tuple[int, int]:
    run = read_run(run_path)
    wanted = {item.docid for items in run.values() for item in items}
    database.parent.mkdir(parents=True, exist_ok=True)
    scanned = 0
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS documents (docid TEXT PRIMARY KEY, text TEXT NOT NULL)"
        )
        existing = {row[0] for row in connection.execute("SELECT docid FROM documents")}
        remaining = wanted - existing
        for cache_dir in cache_dirs:
            if not remaining or not cache_dir.is_dir():
                continue
            for path in cache_dir.rglob("*.json"):
                if not remaining:
                    break
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                response = payload.get("response", payload) if isinstance(payload, dict) else None
                candidates = response.get("candidates") if isinstance(response, dict) else None
                if not isinstance(candidates, list):
                    continue
                batch: list[tuple[str, str]] = []
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    docid = candidate.get("docid")
                    if not isinstance(docid, str) or docid not in remaining:
                        continue
                    text = extract_document_text(candidate.get("doc"))
                    if text:
                        batch.append((docid, text))
                        remaining.discard(docid)
                if batch:
                    connection.executemany(
                        "INSERT OR IGNORE INTO documents(docid, text) VALUES (?, ?)", batch
                    )
                    connection.commit()
                scanned += 1
                if scanned % 50 == 0:
                    print(
                        f"scanned={scanned} stored={len(wanted) - len(remaining)}/{len(wanted)}",
                        flush=True,
                    )
        stored = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    if remaining:
        raise RetrievalError(f"Could not find text for {len(remaining)} run documents")
    return stored, scanned


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", nargs="?", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--database", type=Path, default=DEFAULT_DOCUMENT_STORE)
    parser.add_argument("--document-cache", action="append", type=Path, dest="document_caches")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        stored, scanned = build_store(
            args.run, args.document_caches or DEFAULT_DOCUMENT_CACHES, args.database
        )
    except (OSError, sqlite3.Error, RetrievalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Document store ready: {stored} documents, {scanned} cache files scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
