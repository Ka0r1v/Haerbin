---
name: trec-rag-climbmix-corpus-creation
description: Use when creating, reproducing, validating, or indexing the TREC RAG ClimbMix corpus from karpathy/climbmix-400b-shuffle, especially when official TREC RAG document IDs are required for evaluation-compatible retrieval outputs.
metadata:
  version: v0.1.0
---

# TREC RAG ClimbMix Corpus Creation

Use this skill when the user wants to create a local TREC RAG ClimbMix corpus, generate evaluation-compatible ClimbMix document IDs, validate ClimbMix docid parity, or build a custom index over `karpathy/climbmix-400b-shuffle`.

The critical requirement is docid compatibility with TREC RAG evaluation. `karpathy/climbmix-400b-shuffle` does not provide stable document IDs, so custom indexes must assign document IDs using the same semantics used by Anserini's `FineWebCollection`.

## Core Rule

Use `scripts/create_climbmix_corpus.py` as the authoritative implementation for generating ClimbMix docids.

Do not invent document IDs. Do not use Hugging Face row IDs, hashes, UUIDs, URLs, or custom sequential IDs for TREC RAG ClimbMix retrieval outputs.

Do not reshuffle, repartition, deduplicate, filter, or reorder documents before assigning docids. Docids depend on the source Parquet filename and zero-based row number when no ID field is present.

## Standard Workflow

The script requires Python with `pyarrow` installed.

1. Download or locate the `karpathy/climbmix-400b-shuffle` Parquet shards.
2. Generate either a ClimbMix docid manifest or a ready-to-index corpus JSONL with the bundled script.
3. Build the corpus or search index using the generated `docid` as the external document ID.
4. Validate docid parity before using the index for TREC RAG runs.
5. For retrieval submissions, output these generated docids exactly.

Example:

```bash
python skills/trec-rag-climbmix-corpus-creation/scripts/create_climbmix_corpus.py \
  /path/to/climbmix-parquet \
  -o climbmix-docids.jsonl \
  --format jsonl
```

For a ready-to-index JSONL corpus with `id` and `contents` fields:

```bash
python skills/trec-rag-climbmix-corpus-creation/scripts/create_climbmix_corpus.py \
  /path/to/climbmix-parquet \
  -o climbmix-corpus.jsonl \
  --format corpus-jsonl
```

For a text-only docid list:

```bash
python skills/trec-rag-climbmix-corpus-creation/scripts/create_climbmix_corpus.py \
  /path/to/climbmix-parquet \
  -o climbmix-docids.txt \
  --format text
```

## Validation

If stage1 candidate files are available, use the script's spot-check mode:

```bash
python skills/trec-rag-climbmix-corpus-creation/scripts/create_climbmix_corpus.py \
  /path/to/climbmix-parquet \
  --check-stage1 /path/to/stage1_candidates.jsonl \
  --max-checks 20
```

For optional live validation of the local docid-generation rule against the hosted Pyserini REST API, use:

```bash
python skills/trec-rag-climbmix-corpus-creation/scripts/validate_climbmix_docids_api.py \
  /path/to/climbmix-parquet \
  --sample-size 20
```

This checks that the bundled script's generated docids and local Parquet row text match the official hosted `climbmix-400b` API. It does not validate a downstream dense, sparse, hybrid, or chunked index after that index has been built.

This requires Pyserini REST API access and a local token mechanism such as `PYSERINI_API_TOKEN`, `.env.local`, or `.curlrc.pyserini-rest`. Do not print tokens, authorization headers, `.env.local`, or `.curlrc.pyserini-rest`.

Before treating a custom corpus or index as TREC-compatible, verify:

- Generated docids have the expected format for ClimbMix shards, such as `shard_01789_3390`.
- Known stage1 candidates match both generated docids and source text.
- Optional API spot checks pass against `/v1/climbmix-400b/doc/{docid}` when API access is available. These spot checks validate corpus/docid generation, not a custom index built later.
- The indexing pipeline stores the generated docid as the retrievable external document ID.
- Retrieval run files use the generated ClimbMix docids exactly.

## What to Read

For the exact docid semantics, examples, output formats, and validation behavior, read [references/docid-contract.md](references/docid-contract.md).

For TREC RAG 2026 task/submission format requirements, use the `trec-rag-2026-track-guidelines` skill. For hosted Pyserini REST access to the official index, use the `pyserini-rest-api` skill.
