#!/usr/bin/env python3
"""Late-interaction reranking with the official ColBERTv2 checkpoint."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from rerank import (
    DEFAULT_DOCUMENT_CACHES,
    _file_sha256,
    _save_json_atomic,
    load_cached_documents,
    read_run,
    write_run,
)
from retrieve import DEFAULT_TOPICS, MVP_ROOT, RetrievalError, read_topics


DEFAULT_MODEL = "colbert-ir/colbertv2.0"
DEFAULT_TOKENIZER = "BAAI/bge-small-en-v1.5"
DEFAULT_INPUT = MVP_ROOT / "runs" / "hybrid-final-b8-d1.tsv"
DEFAULT_OUTPUT = MVP_ROOT / "runs" / "colbert-reranked.tsv"
DEFAULT_CACHE = MVP_ROOT / "cache" / "colbert_reranker"


def load_colbert(
    model_name: str, tokenizer_name: str, device: str, dtype: str
) -> tuple[Any, Any, Any, Any]:
    try:
        import torch
        import torch.nn.functional as functional
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file
        from transformers import AutoConfig, AutoTokenizer, BertModel
    except ImportError as exc:
        raise RetrievalError("torch, transformers, huggingface-hub and safetensors are required") from exc

    print(f"Loading ColBERT config/tokenizer: {model_name}", flush=True)
    config = AutoConfig.from_pretrained(model_name, local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, local_files_only=True)
    if len(tokenizer) != config.vocab_size:
        raise RetrievalError(
            f"Tokenizer vocab {len(tokenizer)} does not match ColBERT vocab {config.vocab_size}"
        )
    print("Loading ColBERT safetensors checkpoint", flush=True)
    checkpoint = load_file(
        hf_hub_download(model_name, "model.safetensors", local_files_only=True), device="cpu"
    )
    print("Constructing BERT and projection layers", flush=True)
    bert = BertModel(config, add_pooling_layer=False)
    bert_state = {
        key.removeprefix("bert."): value
        for key, value in checkpoint.items()
        if key.startswith("bert.") and not key.startswith("bert.pooler.")
    }
    missing, unexpected = bert.load_state_dict(bert_state, strict=False)
    meaningful_unexpected = [key for key in unexpected if key != "embeddings.position_ids"]
    if meaningful_unexpected or [key for key in missing if not key.startswith("pooler.")]:
        raise RetrievalError(f"Unexpected ColBERT checkpoint keys: missing={missing}, extra={unexpected}")
    projection = torch.nn.Linear(config.hidden_size, checkpoint["linear.weight"].shape[0], bias=False)
    projection.weight.data.copy_(checkpoint["linear.weight"])
    print(f"Moving ColBERT to {device} ({dtype})", flush=True)
    bert.eval().to(device)
    projection.eval().to(device)
    if dtype == "float16":
        bert.half()
        projection.half()
    print("ColBERT model is ready", flush=True)
    return tokenizer, bert, projection, functional


def _marker_id(tokenizer: Any, token: str) -> int:
    value = tokenizer.convert_tokens_to_ids(token)
    if value is None or value == tokenizer.unk_token_id:
        raise RetrievalError(f"Tokenizer does not provide {token}")
    return int(value)


def score_colbert(
    *,
    run: dict[str, list[Any]],
    topics: dict[str, str],
    documents: dict[str, dict[str, str]],
    input_hash: str,
    model_name: str,
    tokenizer_name: str,
    depth: int,
    query_length: int,
    document_length: int,
    batch_size: int,
    device: str,
    dtype: str,
    cache_path: Path,
) -> dict[str, dict[str, float]]:
    metadata = {
        "input_sha256": input_hash,
        "model": model_name,
        "tokenizer": tokenizer_name,
        "depth": depth,
        "query_length": query_length,
        "document_length": document_length,
        "dtype": dtype,
    }
    scores: dict[str, dict[str, float]] = {}
    if cache_path.is_file():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and all(payload.get(k) == v for k, v in metadata.items()):
                scores = payload.get("scores", {})
        except (OSError, json.JSONDecodeError):
            pass
    pending = [qid for qid in run if qid not in scores]
    if not pending:
        print(f"Loaded all ColBERT scores from {cache_path}")
        return scores

    import torch

    tokenizer, bert, projection, functional = load_colbert(
        model_name, tokenizer_name, device, dtype
    )
    query_marker = _marker_id(tokenizer, "[unused0]")
    document_marker = _marker_id(tokenizer, "[unused1]")

    def encode(inputs: dict[str, Any]) -> Any:
        tensors = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            embeddings = projection(bert(**tensors).last_hidden_state)
            return functional.normalize(embeddings, p=2, dim=-1)

    for topic_index, qid in enumerate(pending, start=1):
        query_inputs = tokenizer(
            topics[qid],
            max_length=query_length,
            truncation=True,
            padding="max_length",
            return_tensors="pt",
        )
        query_inputs["input_ids"][:, 1] = query_marker
        query_inputs["input_ids"][query_inputs["input_ids"] == tokenizer.pad_token_id] = tokenizer.mask_token_id
        query_inputs["attention_mask"].fill_(1)
        query_embeddings = encode(query_inputs)[0]

        head = run[qid][:depth]
        topic_scores: dict[str, float] = {}
        for start in range(0, len(head), batch_size):
            batch = head[start : start + batch_size]
            document_inputs = tokenizer(
                [documents[qid][item.docid] for item in batch],
                max_length=document_length,
                truncation=True,
                padding="max_length",
                return_tensors="pt",
            )
            document_inputs["input_ids"][:, 1] = document_marker
            document_mask = document_inputs["attention_mask"].to(device).bool()
            document_embeddings = encode(document_inputs)
            similarities = torch.einsum("qd,bkd->bqk", query_embeddings, document_embeddings)
            similarities = similarities.masked_fill(~document_mask[:, None, :], -1e4)
            values = similarities.max(dim=2).values.sum(dim=1).float().cpu().tolist()
            topic_scores.update({item.docid: float(score) for item, score in zip(batch, values)})
        if any(not math.isfinite(score) for score in topic_scores.values()):
            raise RetrievalError(f"ColBERT returned a non-finite score for topic {qid}")
        scores[qid] = topic_scores
        _save_json_atomic(cache_path, {**metadata, "scores": scores})
        print(f"[{topic_index}/{len(pending)}] ColBERT-scored {qid}: {len(head)} documents")
    return scores


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_run", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document-cache", action="append", type=Path, dest="document_caches")
    parser.add_argument("--score-cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--tokenizer", default=DEFAULT_TOKENIZER)
    parser.add_argument("--depth", type=int, default=100)
    parser.add_argument("--query-length", type=int, default=64)
    parser.add_argument("--document-length", type=int, default=180)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dtype", choices=("float16", "float32"), default="float16")
    parser.add_argument("--original-weight", type=float, default=4.0)
    parser.add_argument("--colbert-weight", type=float, default=1.0)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--output-hits", type=int)
    parser.add_argument("--run-id", default="haerbin-colbert")
    args = parser.parse_args(argv)
    if min(args.depth, args.query_length, args.document_length, args.batch_size) <= 0:
        parser.error("lengths, depth, and batch size must be positive")
    if args.output_hits is not None and args.output_hits <= 0:
        parser.error("--output-hits must be positive")
    if args.original_weight < 0 or args.colbert_weight <= 0 or args.rrf_k < 0:
        parser.error("weights must be non-negative and ColBERT weight positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run = read_run(args.input_run)
        topics = {topic.qid: topic.narrative for topic in read_topics(args.topics)}
        wanted = {qid: {item.docid for item in items[: args.depth]} for qid, items in run.items()}
        documents = load_cached_documents(args.document_caches or DEFAULT_DOCUMENT_CACHES, wanted)
        missing = sum(len(docids - set(documents.get(qid, {}))) for qid, docids in wanted.items())
        if missing:
            raise RetrievalError(f"Missing cached text for {missing} ColBERT candidates")
        cache_name = (
            f"{args.input_run.stem}.colbertv2.depth-{args.depth}."
            f"q-{args.query_length}.d-{args.document_length}.dtype-{args.dtype}.json"
        )
        scores = score_colbert(
            run=run,
            topics=topics,
            documents=documents,
            input_hash=_file_sha256(args.input_run),
            model_name=args.model,
            tokenizer_name=args.tokenizer,
            depth=args.depth,
            query_length=args.query_length,
            document_length=args.document_length,
            batch_size=args.batch_size,
            device=args.device,
            dtype=args.dtype,
            cache_path=args.score_cache_dir / cache_name,
        )
        rows = write_run(
            args.output,
            run,
            scores,
            args.depth,
            args.original_weight,
            args.colbert_weight,
            args.rrf_k,
            args.run_id,
            args.output_hits,
        )
    except (OSError, RetrievalError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {rows} ColBERT rows for {len(run)} topics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
