#!/usr/bin/env python3
"""Generate ClimbMix docids exactly as Anserini's FineWebCollection does.

Anserini pointer:
  io.anserini.collection.FineWebCollection

Relevant rule:
  1. Use the first string id-like Parquet field, in this order:
     id, docid, doc_id, document_id, then any field containing "id".
  2. If no such field exists, generate:
       <parquet filename without .parquet>_<zero-based row number>

For karpathy/climbmix-400b-shuffle, shards are named like
``shard_01789.parquet`` and contain only a ``text`` column, so row 3390 in
that file is indexed as ``shard_01789_3390``.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, TextIO


ID_FIELD_CANDIDATES = ("id", "docid", "doc_id", "document_id")
TEXT_FIELD_CANDIDATES = ("text", "contents", "content", "body")
DOCID_RE = re.compile(r"^(.+)_(\d+)$")


def parquet_module() -> Any:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as e:
        raise SystemExit(
            "missing dependency: pyarrow. Install it with `python -m pip install pyarrow` "
            "in the environment used to run this script."
        ) from e
    return pq


def parquet_stem(path: Path) -> str:
    """Match FineWebCollection's segment-name logic."""
    name = path.name
    if name.endswith(".parquet"):
        return name[: -len(".parquet")]
    return path.stem


def expand_inputs(inputs: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        matches = [Path(p) for p in glob.glob(raw)]
        if not matches:
            matches = [Path(raw)]
        for path in matches:
            if path.is_dir():
                paths.extend(sorted(path.rglob("*.parquet")))
            elif path.is_file() and path.name.endswith(".parquet"):
                paths.append(path)
            else:
                raise SystemExit(f"not a Parquet file or directory: {path}")
    return sorted(dict.fromkeys(paths))


def id_field_candidates(field_names: list[str], preferred_id_field: str) -> list[str]:
    fields = set(field_names)
    ordered = [preferred_id_field, *ID_FIELD_CANDIDATES]
    out: list[str] = []
    for field in ordered:
        if field in fields and field not in out:
            out.append(field)
    for field in field_names:
        if "id" in field.lower() and field not in out:
            out.append(field)
    return out


def text_field(field_names: list[str]) -> str | None:
    fields = set(field_names)
    for field in TEXT_FIELD_CANDIDATES:
        if field in fields:
            return field
    return None


def selected_text_field(field_names: list[str], preferred_text_field: str | None) -> str | None:
    if preferred_text_field:
        if preferred_text_field not in set(field_names):
            raise SystemExit(f"text field not found in Parquet schema: {preferred_text_field}")
        return preferred_text_field
    return text_field(field_names)


def stringify_id(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value if value else None
    return None


def iter_docid_rows(
    path: Path,
    *,
    preferred_id_field: str = "id",
    only_rows: set[int] | None = None,
    batch_size: int = 8192,
) -> Iterator[dict]:
    pq = parquet_module()
    pf = pq.ParquetFile(path)
    field_names = pf.schema_arrow.names
    id_fields = id_field_candidates(field_names, preferred_id_field)
    stem = parquet_stem(path)
    total_rows = pf.metadata.num_rows

    if not id_fields:
        row_iter: Iterable[int] = sorted(only_rows) if only_rows is not None else range(total_rows)
        for row_number in row_iter:
            if row_number < 0 or row_number >= total_rows:
                continue
            yield {
                "docid": f"{stem}_{row_number}",
                "source_file": str(path),
                "row_number": row_number,
                "mode": "generated_segment_row",
            }
        return

    offset = 0
    for batch in pf.iter_batches(columns=id_fields, batch_size=batch_size):
        columns = {name: batch.column(i) for i, name in enumerate(id_fields)}
        for local_i in range(batch.num_rows):
            row_number = offset + local_i
            if only_rows is not None and row_number not in only_rows:
                continue
            docid = None
            mode = None
            for field in id_fields:
                docid = stringify_id(columns[field][local_i].as_py())
                if docid:
                    mode = f"field:{field}"
                    break
            if not docid:
                docid = f"{stem}_{row_number}"
                mode = "generated_segment_row"
            yield {
                "docid": docid,
                "source_file": str(path),
                "row_number": row_number,
                "mode": mode,
            }
        offset += batch.num_rows


def iter_corpus_rows(
    path: Path,
    *,
    preferred_id_field: str = "id",
    preferred_text_field: str | None = None,
    only_rows: set[int] | None = None,
    batch_size: int = 8192,
) -> Iterator[dict]:
    pq = parquet_module()
    pf = pq.ParquetFile(path)
    field_names = pf.schema_arrow.names
    id_fields = id_field_candidates(field_names, preferred_id_field)
    text_name = selected_text_field(field_names, preferred_text_field)
    if text_name is None:
        raise SystemExit(f"no text field found in Parquet schema: {path}")

    stem = parquet_stem(path)
    columns_to_read = [*id_fields, text_name]
    offset = 0

    for batch in pf.iter_batches(columns=columns_to_read, batch_size=batch_size):
        columns = {name: batch.column(i) for i, name in enumerate(columns_to_read)}
        for local_i in range(batch.num_rows):
            row_number = offset + local_i
            if only_rows is not None and row_number not in only_rows:
                continue

            docid = None
            mode = None
            for field in id_fields:
                docid = stringify_id(columns[field][local_i].as_py())
                if docid:
                    mode = f"field:{field}"
                    break
            if not docid:
                docid = f"{stem}_{row_number}"
                mode = "generated_segment_row"

            text_value = columns[text_name][local_i].as_py()
            yield {
                "id": docid,
                "contents": "" if text_value is None else str(text_value),
                "docid": docid,
                "source_file": str(path),
                "row_number": row_number,
                "mode": mode,
            }
        offset += batch.num_rows


def write_record(record: dict, fmt: str, out: TextIO) -> None:
    if fmt in {"jsonl", "corpus-jsonl"}:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
    elif fmt == "tsv":
        out.write(
            f"{record['docid']}\t{record['source_file']}\t"
            f"{record['row_number']}\t{record['mode']}\n"
        )
    elif fmt == "text":
        out.write(f"{record['docid']}\n")
    else:
        raise ValueError(f"unknown output format: {fmt}")


def candidate_docs(row: dict) -> list[dict]:
    docs = row.get("candidates")
    if isinstance(docs, list):
        return docs
    docs = row.get("candidate_docs")
    if isinstance(docs, list):
        return docs
    return []


def collect_stage1_checks(
    stage1_paths: Iterable[Path],
    stems: set[str],
    max_checks: int,
) -> dict[str, dict]:
    checks: dict[str, dict] = {}
    for path in stage1_paths:
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                row = json.loads(line)
                for cand_index, cand in enumerate(candidate_docs(row)):
                    docid = str(cand.get("docid", ""))
                    match = DOCID_RE.match(docid)
                    if not match:
                        continue
                    stem, row_number_raw = match.groups()
                    if stem not in stems or docid in checks:
                        continue
                    doc_text = cand.get("doc")
                    if doc_text is None:
                        doc_text = cand.get("doc_text")
                    if not isinstance(doc_text, str):
                        continue
                    checks[docid] = {
                        "docid": docid,
                        "stem": stem,
                        "row_number": int(row_number_raw),
                        "expected_text": doc_text,
                        "stage1_path": str(path),
                        "stage1_line": line_no,
                        "candidate_index": cand_index,
                        "qid": row.get("qid"),
                    }
                    if len(checks) >= max_checks:
                        return checks
    return checks


def read_text_rows(path: Path, rows: set[int], batch_size: int = 8192) -> dict[int, str]:
    if not rows:
        return {}
    pq = parquet_module()
    pf = pq.ParquetFile(path)
    field = text_field(pf.schema_arrow.names)
    if field is None:
        return {}
    wanted = set(rows)
    found: dict[int, str] = {}
    offset = 0
    for batch in pf.iter_batches(columns=[field], batch_size=batch_size):
        start = offset
        end = offset + batch.num_rows
        overlap = [row for row in wanted if start <= row < end]
        if overlap:
            column = batch.column(0)
            for row_number in overlap:
                value = column[row_number - start].as_py()
                found[row_number] = "" if value is None else str(value)
            wanted.difference_update(overlap)
            if not wanted:
                break
        offset = end
    return found

def compact_text(text: str) -> str:
    return " ".join(text.split())


def run_stage1_checks(paths: list[Path], stage1_paths: list[Path], max_checks: int) -> list[dict]:
    stems = {parquet_stem(path) for path in paths}
    checks = collect_stage1_checks(stage1_paths, stems, max_checks)
    checks_by_stem: dict[str, list[dict]] = {}
    for check in checks.values():
        checks_by_stem.setdefault(check["stem"], []).append(check)

    results: list[dict] = []
    for path in paths:
        stem = parquet_stem(path)
        stem_checks = checks_by_stem.get(stem, [])
        rows = {int(check["row_number"]) for check in stem_checks}
        generated = {
            record["row_number"]: record["docid"]
            for record in iter_docid_rows(path, only_rows=rows)
        }
        texts = read_text_rows(path, rows)
        for check in stem_checks:
            row_number = int(check["row_number"])
            expected_text = check["expected_text"]
            actual_text = texts.get(row_number, "")
            text_match = actual_text == expected_text
            compact_match = compact_text(actual_text) == compact_text(expected_text)
            results.append({
                "docid": check["docid"],
                "generated_docid": generated.get(row_number),
                "row_number": row_number,
                "qid": check.get("qid"),
                "stage1_path": check["stage1_path"],
                "stage1_line": check["stage1_line"],
                "candidate_index": check["candidate_index"],
                "docid_match": generated.get(row_number) == check["docid"],
                "text_match": text_match,
                "compact_text_match": compact_match,
                "expected_prefix": compact_text(expected_text)[:160],
                "actual_prefix": compact_text(actual_text)[:160],
            })
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ClimbMix/FineWeb Parquet docids using Anserini FineWebCollection semantics."
    )
    parser.add_argument("inputs", nargs="+", help="Parquet files, directories, or glob patterns.")
    parser.add_argument("-o", "--output", help="Output path. Defaults to stdout.")
    parser.add_argument("--format", choices=("jsonl", "tsv", "text", "corpus-jsonl"), default="jsonl")
    parser.add_argument("--id-field", default="id", help="Preferred id field before Anserini's fallback candidates.")
    parser.add_argument("--text-field", help="Text field to use for corpus-jsonl. Defaults to text/contents/content/body.")
    parser.add_argument("--row", type=int, action="append", help="Only emit this zero-based row number. Repeatable.")
    parser.add_argument("--limit", type=int, help="Stop after this many emitted docids.")
    parser.add_argument(
        "--check-stage1",
        action="append",
        default=[],
        help="Stage1 candidates JSONL file to use for spot-checking generated ids/text. Repeatable.",
    )
    parser.add_argument("--max-checks", type=int, default=10, help="Maximum stage1 spot checks.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = expand_inputs(args.inputs)
    if not paths:
        raise SystemExit("no Parquet files found")

    only_rows = set(args.row) if args.row is not None else None
    emitted = 0
    out_cm = open(args.output, "w", encoding="utf-8") if args.output else None
    out = out_cm or sys.stdout
    try:
        for path in paths:
            if args.format == "corpus-jsonl":
                records = iter_corpus_rows(
                    path,
                    preferred_id_field=args.id_field,
                    preferred_text_field=args.text_field,
                    only_rows=only_rows,
                )
            else:
                records = iter_docid_rows(path, preferred_id_field=args.id_field, only_rows=only_rows)
            for record in records:
                write_record(record, args.format, out)
                emitted += 1
                if args.limit is not None and emitted >= args.limit:
                    break
            if args.limit is not None and emitted >= args.limit:
                break
    finally:
        if out_cm is not None:
            out_cm.close()

    if args.check_stage1:
        stage1_paths = expand_stage1_inputs(args.check_stage1)
        results = run_stage1_checks(paths, stage1_paths, args.max_checks)
        print(f"spot_checks={len(results)}", file=sys.stderr)
        for result in results:
            ok = result["docid_match"] and (result["text_match"] or result["compact_text_match"])
            status = "PASS" if ok else "FAIL"
            print(
                f"{status}\t{result['docid']}\tgenerated={result['generated_docid']}\t"
                f"docid_match={result['docid_match']}\ttext_match={result['text_match']}\t"
                f"compact_text_match={result['compact_text_match']}\t"
                f"stage1={result['stage1_path']}:{result['stage1_line']}",
                file=sys.stderr,
            )
            if not ok:
                print(f"  expected: {result['expected_prefix']}", file=sys.stderr)
                print(f"  actual:   {result['actual_prefix']}", file=sys.stderr)


def expand_stage1_inputs(inputs: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        matches = [Path(p) for p in glob.glob(raw)]
        if not matches:
            matches = [Path(raw)]
        for path in matches:
            if path.is_dir():
                paths.extend(sorted(path.rglob("stage1_candidates.jsonl")))
            elif path.is_file():
                paths.append(path)
            else:
                raise SystemExit(f"not a stage1 JSONL file or directory: {path}")
    return sorted(dict.fromkeys(paths))


if __name__ == "__main__":
    main()
