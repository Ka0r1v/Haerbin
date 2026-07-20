#!/usr/bin/env python3
"""Analyze per-topic relevant-document coverage and sampled retrieval misses."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from query_rewrite import _extract_json_object, _read_env_value
from retrieve import (
    DEFAULT_BASE_URL,
    DEFAULT_INDEX,
    DEFAULT_TOPICS,
    MVP_ROOT,
    RetrievalError,
    fetch_document_api,
    load_token,
    read_topics,
)
from rerank import extract_document_text


DEFAULT_QRELS = (
    MVP_ROOT
    / "data"
    / "qrels"
    / "rag25-climbmix-umbrela-codex-gpt5.5-medium-reasoning-v1.qrels"
)
DEFAULT_TSV = MVP_ROOT / "reports" / "topic_recall_analysis.tsv"
DEFAULT_REPORT = MVP_ROOT / "reports" / "topic_miss_analysis.md"
DEFAULT_DOC_CACHE = MVP_ROOT / "cache" / "missed_documents"
DEFAULT_LLM_CACHE = MVP_ROOT / "cache" / "missed_facet_analysis"
DEFAULT_RUNS = [
    f"BM25={MVP_ROOT / 'runs' / 'haerbin-bm25-dev.tsv'}",
    f"V2={MVP_ROOT / 'runs' / 'haerbin-balanced-v2-deep-dev.tsv'}",
    f"V3={MVP_ROOT / 'runs' / 'haerbin-hybrid-v3-dev.tsv'}",
]

FACET_PROMPT = """Analyze why a BM25/multi-query retrieval system may have missed the sampled relevant documents.

Use only the query and excerpts below. Do not assume the sample represents every missed document.
Return JSON only with this schema:
{{
  "entity_aliases": ["specific alias/name mismatch visible in the evidence"],
  "temporal": ["date, period, chronology, or recency mismatch"],
  "locations": ["place, jurisdiction, region, or geographic mismatch"],
  "terminology": ["technical, legal, scientific, acronym, or paraphrase mismatch"],
  "missing_facets": ["distinct information need present in the missed evidence"],
  "recommended_routes": [
    {{"type": "entity_alias|temporal|geographic|terminology|facet", "query": "short ordinary-text BM25 query"}}
  ],
  "confidence": "low|medium|high",
  "notes": "one concise limitation note"
}}

Rules:
- Recommend diverse ordinary-text queries, not Lucene syntax.
- Do not merely shorten or repeat the original query.
- Do not invent aliases, dates, places, or facts absent from the supplied text.
- Keep at most 2 items per category and at most 6 recommended routes.

Topic {qid}:
{query}

Sampled relevant documents missed from Top-{depth}:
{documents}
"""


def parse_run_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("run must be NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("run must be NAME=PATH")
    return name.strip(), Path(raw_path.strip())


def read_qrels(path: Path, threshold: int) -> tuple[dict[str, dict[str, int]], dict[str, set[str]]]:
    grades: dict[str, dict[str, int]] = defaultdict(dict)
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            fields = line.split()
            if len(fields) != 4:
                raise RetrievalError(f"{path}:{line_number}: expected 4 qrels fields")
            qid, _, docid, raw_grade = fields
            try:
                grade = int(raw_grade)
            except ValueError as exc:
                raise RetrievalError(f"{path}:{line_number}: invalid grade") from exc
            grades[qid][docid] = max(grade, grades[qid].get(docid, grade))
    relevant = {
        qid: {docid for docid, grade in documents.items() if grade >= threshold}
        for qid, documents in grades.items()
    }
    return dict(grades), relevant


def read_run(path: Path) -> dict[str, list[str]]:
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            fields = line.split()
            if len(fields) != 6:
                raise RetrievalError(f"{path}:{line_number}: expected 6 run fields")
            qid, _, docid, raw_rank, _, _ = fields
            try:
                rank = int(raw_rank)
            except ValueError as exc:
                raise RetrievalError(f"{path}:{line_number}: invalid rank") from exc
            grouped[qid].append((rank, docid))
    return {qid: [docid for _, docid in sorted(items)] for qid, items in grouped.items()}


def safe_docid(docid: str) -> str:
    return "".join(character if character.isalnum() or character in "_.-" else "_" for character in docid)


def cached_document_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    text = payload.get("text") if isinstance(payload, dict) else None
    return text if isinstance(text, str) and text.strip() else None


def fetch_sample_texts(
    docids: list[str],
    *,
    cache_dir: Path,
    base_url: str,
    index: str,
    timeout: float,
    retries: int,
    max_workers: int,
) -> dict[str, str]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    texts: dict[str, str] = {}
    missing: list[str] = []
    for docid in docids:
        cached = cached_document_text(cache_dir / f"{safe_docid(docid)}.json")
        if cached is None:
            missing.append(docid)
        else:
            texts[docid] = cached
    if not missing:
        return texts
    token = load_token()

    def fetch(docid: str) -> tuple[str, str]:
        payload = fetch_document_api(
            base_url=base_url,
            index=index,
            docid=docid,
            token=token,
            timeout=timeout,
            retries=retries,
        )
        text = extract_document_text(payload.get("doc"))
        if not text:
            raise RetrievalError(f"Document endpoint returned no text for {docid}")
        cache_path = cache_dir / f"{safe_docid(docid)}.json"
        cache_path.write_text(
            json.dumps({"docid": docid, "text": text}, ensure_ascii=False), encoding="utf-8"
        )
        return docid, text

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch, docid): docid for docid in missing}
        for future in as_completed(futures):
            docid = futures[future]
            try:
                fetched_docid, text = future.result()
            except Exception as exc:  # report individual failures without exposing credentials
                print(f"WARNING: could not fetch {docid}: {exc}", file=sys.stderr)
                continue
            texts[fetched_docid] = text
    return texts


def call_facet_analyzer(
    *, qid: str, query: str, depth: int, documents: list[tuple[str, int, str]], cache_dir: Path
) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{qid}.json"
    fingerprint = json.dumps(
        {"qid": qid, "query": query, "depth": depth, "docs": [(d, g) for d, g, _ in documents]},
        ensure_ascii=False,
        sort_keys=True,
    )
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("fingerprint") == fingerprint and isinstance(cached.get("analysis"), dict):
                return cached["analysis"]
        except (OSError, json.JSONDecodeError):
            pass
    base_url = _read_env_value("QUERY_REWRITE_BASE_URL")
    api_key = _read_env_value("QUERY_REWRITE_API_KEY")
    model = _read_env_value("QUERY_REWRITE_MODEL")
    if not base_url or not api_key or not model:
        raise RetrievalError("Facet analysis requires the local query rewrite API configuration.")
    excerpts = "\n\n".join(
        f"[{index}] docid={docid}, grade={grade}\n{text[:1600]}"
        for index, (docid, grade, text) in enumerate(documents, start=1)
    )
    prompt = FACET_PROMPT.format(qid=qid, query=query, depth=depth, documents=excerpts)
    analysis: dict[str, Any] | None = None
    last_error: Exception | None = None
    for attempt in range(3):
        repair = "" if attempt == 0 else "\nYour previous response was not valid JSON. Return one JSON object only."
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return one valid JSON object only."},
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
            with urlopen(request, timeout=180) as response:
                result = json.load(response)
            content = result["choices"][0]["message"]["content"]
            analysis = _extract_json_object(content)
            break
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise RetrievalError("Facet analysis authentication failed.") from exc
            last_error = exc
        except (URLError, KeyError, IndexError, TypeError, json.JSONDecodeError, RetrievalError) as exc:
            last_error = exc
    if analysis is None:
        raise RetrievalError("Facet analysis failed to return valid JSON after 3 attempts.") from last_error
    cache_path.write_text(
        json.dumps({"fingerprint": fingerprint, "analysis": analysis}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return analysis


def markdown_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "—"
    cleaned = [str(value).replace("|", "\\|").replace("\n", " ") for value in values[:2]]
    return "；".join(cleaned)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", type=parse_run_spec)
    parser.add_argument("--focus-run", default="V3")
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--threshold", type=int, default=2)
    parser.add_argument("--depths", type=int, nargs="+", default=[100, 1000, 5000])
    parser.add_argument("--sample-misses", type=int, default=5)
    parser.add_argument("--fetch-samples", action="store_true")
    parser.add_argument("--analyze-facets", action="store_true")
    parser.add_argument("--doc-cache", type=Path, default=DEFAULT_DOC_CACHE)
    parser.add_argument("--llm-cache", type=Path, default=DEFAULT_LLM_CACHE)
    parser.add_argument("--output-tsv", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    if any(depth <= 0 for depth in args.depths) or args.sample_misses <= 0 or args.workers <= 0:
        parser.error("depths, sample count, and workers must be positive")
    run_specs = args.run or [parse_run_spec(value) for value in DEFAULT_RUNS]
    run_paths = dict(run_specs)
    if args.focus_run not in run_paths:
        parser.error(f"--focus-run must name one of: {', '.join(run_paths)}")

    try:
        topics = {topic.qid: topic.narrative for topic in read_topics(args.topics)}
        grades, relevant = read_qrels(args.qrels, args.threshold)
        runs = {name: read_run(path) for name, path in run_specs}
        rows: list[dict[str, Any]] = []
        sample_by_qid: dict[str, list[tuple[str, int]]] = {}
        focus_depth = max(args.depths)
        for qid in sorted(topics, key=lambda value: int(value) if value.isdigit() else value):
            rel = relevant.get(qid, set())
            row: dict[str, Any] = {"qid": qid, "relevant_total": len(rel)}
            for name, ranking_by_qid in runs.items():
                ranking = ranking_by_qid.get(qid, [])
                for depth in args.depths:
                    hits = len(rel & set(ranking[:depth]))
                    row[f"{name}_hit@{depth}"] = hits
                    row[f"{name}_recall@{depth}"] = hits / len(rel) if rel else 0.0
                    row[f"{name}_miss@{depth}"] = len(rel) - hits
            focus_docs = set(runs[args.focus_run].get(qid, [])[:focus_depth])
            missing = sorted(
                rel - focus_docs,
                key=lambda docid: (-grades.get(qid, {}).get(docid, 0), docid),
            )
            sample_by_qid[qid] = [
                (docid, grades.get(qid, {}).get(docid, 0)) for docid in missing[: args.sample_misses]
            ]
            rows.append(row)

        fieldnames = list(rows[0])
        args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
        args.output_tsv.write_text(
            "\t".join(fieldnames)
            + "\n"
            + "\n".join(
                "\t".join(
                    f"{row[field]:.6f}" if isinstance(row[field], float) else str(row[field])
                    for field in fieldnames
                )
                for row in rows
            )
            + "\n",
            encoding="utf-8",
        )

        selected_docids = [docid for samples in sample_by_qid.values() for docid, _ in samples]
        texts: dict[str, str] = {}
        if args.fetch_samples or args.analyze_facets:
            texts = fetch_sample_texts(
                selected_docids,
                cache_dir=args.doc_cache,
                base_url=args.base_url,
                index=args.index,
                timeout=args.timeout,
                retries=args.retries,
                max_workers=args.workers,
            )
        analyses: dict[str, dict[str, Any]] = {}
        if args.analyze_facets:
            for index, qid in enumerate(sorted(topics, key=lambda x: int(x)), start=1):
                documents = [
                    (docid, grade, texts[docid])
                    for docid, grade in sample_by_qid[qid]
                    if docid in texts
                ]
                if documents:
                    analyses[qid] = call_facet_analyzer(
                        qid=qid,
                        query=topics[qid],
                        depth=focus_depth,
                        documents=documents,
                        cache_dir=args.llm_cache,
                    )
                print(f"facet analysis [{index}/{len(topics)}] qid={qid}")

        report = [
            "# Topic Recall 与 Top-5000 漏检分析",
            "",
            f"qrels：`{args.qrels.name}`；相关阈值：`>={args.threshold}`；focus run：`{args.focus_run}`。",
            "",
            "## 逐 topic 覆盖",
            "",
            "| qid | 相关总数 | BM25 R@100 | BM25 R@1000 | V2 R@100 | V2 R@1000 | V2 R@5000 | V3 R@100 | V3 R@1000 | V3 R@5000 | V3 漏检@5000 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        by_qid = {row["qid"]: row for row in rows}
        for qid in sorted(by_qid, key=lambda x: int(x)):
            row = by_qid[qid]
            report.append(
                f"| {qid} | {row['relevant_total']} | {row.get('BM25_recall@100', 0):.3f} | "
                f"{row.get('BM25_recall@1000', 0):.3f} | {row.get('V2_recall@100', 0):.3f} | "
                f"{row.get('V2_recall@1000', 0):.3f} | {row.get('V2_recall@5000', 0):.3f} | "
                f"{row.get('V3_recall@100', 0):.3f} | {row.get('V3_recall@1000', 0):.3f} | "
                f"{row.get('V3_recall@5000', 0):.3f} | {row.get('V3_miss@5000', 0)} |"
            )
        totals = sorted(row["relevant_total"] for row in rows)
        report += [
            "",
            "已知相关文档不是每题只有几十篇："
            f"最少 `{totals[0]}`，中位数 `{totals[len(totals)//2]}`，最多 `{totals[-1]}`。",
            "",
        ]
        if analyses:
            report += [
                "## 漏检样本中的查询缺口",
                "",
                f"每题从 `{args.focus_run}` Top-{focus_depth} 之外按 qrels grade 优先抽样最多 {args.sample_misses} 篇。"
                "以下结论只代表样本，不代表该 topic 的全部漏检文档。",
                "",
                "| qid | 实体/别名 | 时间 | 地点 | 术语 | 未覆盖 facet | 建议路由 | 置信度 |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
            for qid in sorted(analyses, key=lambda x: int(x)):
                analysis = analyses[qid]
                routes = analysis.get("recommended_routes", [])
                route_text = "；".join(
                    f"{item.get('type', '?')}: {item.get('query', '')}"
                    for item in routes[:4]
                    if isinstance(item, dict)
                ) or "—"
                report.append(
                    f"| {qid} | {markdown_list(analysis.get('entity_aliases'))} | "
                    f"{markdown_list(analysis.get('temporal'))} | {markdown_list(analysis.get('locations'))} | "
                    f"{markdown_list(analysis.get('terminology'))} | {markdown_list(analysis.get('missing_facets'))} | "
                    f"{route_text.replace('|', '\\|')} | {analysis.get('confidence', '—')} |"
                )
            type_counts = Counter(
                str(route.get("type"))
                for analysis in analyses.values()
                for route in analysis.get("recommended_routes", [])
                if isinstance(route, dict) and route.get("type")
            )
            report += [
                "",
                "建议路由类型频次："
                + "、".join(f"`{name}`={count}" for name, count in type_counts.most_common()),
                "",
            ]
        report += [
            "## 方法限制",
            "",
            "- qrels 是池化/LLM judgment，不是对 ClimbMix 全库的穷举人工标注。",
            "- 漏检文本分析使用每题少量高 grade 样本，适合发现模式，不适合估计模式占比。",
            "- V2/V3 的 dense、ColBERT 和 RankLLM 都只处理已有候选，不能恢复未进入 Top-5000 的文档。",
            "",
        ]
        args.output_report.write_text("\n".join(report), encoding="utf-8")
    except (OSError, RetrievalError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output_tsv}")
    print(f"Wrote {args.output_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
