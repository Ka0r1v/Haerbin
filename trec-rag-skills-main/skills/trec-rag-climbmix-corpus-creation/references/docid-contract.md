# ClimbMix Docid Contract

Use this reference when reasoning about TREC RAG ClimbMix docid generation, debugging mismatched document IDs, or adapting the corpus creation script to a custom indexing pipeline.

## Source Dataset

The TREC RAG ClimbMix corpus source is:

```text
karpathy/climbmix-400b-shuffle
```

The dataset is distributed as Parquet shards. For the ClimbMix shards used here, files are named like:

```text
shard_01789.parquet
```

and contain a `text` column without a stable string document ID column.

## Anserini FineWebCollection Semantics

> **Naming note:** `FineWebCollection` is the Anserini reader name from the NanoKnow SIGIR work. Since ClimbMix reuses the same shuffled-Parquet docid convention as `karpathy/fineweb-edu-100b-shuffle`, we reuse those semantics here.

The bundled script implements Anserini `FineWebCollection` document ID behavior:

1. Look for the first string ID-like Parquet field in this order: `id`, `docid`, `doc_id`, `document_id`, then any field containing `id`.
2. If no usable ID field exists for a row, generate:

```text
<parquet filename without .parquet>_<zero-based row number>
```

For `karpathy/climbmix-400b-shuffle`, this means row `3390` in `shard_01789.parquet` becomes:

```text
shard_01789_3390
```

## Script Output

The authoritative script is:

```text
scripts/create_climbmix_corpus.py
```

It requires Python with `pyarrow` installed:

```bash
python -m pip install pyarrow
```

It accepts Parquet files, directories, or glob patterns. Directories are expanded recursively to `*.parquet` files and processed in sorted path order.

Supported output formats:

- `jsonl`: one JSON object per row, including `docid`, `source_file`, `row_number`, and `mode`.
- `tsv`: `docid`, `source_file`, `row_number`, and `mode`.
- `text`: one docid per line.
- `corpus-jsonl`: one JSON object per row with `id`, `contents`, `docid`, `source_file`, `row_number`, and `mode`.

Use `corpus-jsonl` when building dense, sparse, or hybrid indexes with tools that consume JSONL records. Use `jsonl` when building or debugging a separate mapping because it preserves source path and row metadata without copying document text. Use `text` only when a downstream tool needs a plain docid list.

Example `corpus-jsonl` record:

```json
{"id":"shard_01789_3390","contents":"...","docid":"shard_01789_3390","source_file":"/path/to/shard_01789.parquet","row_number":3390,"mode":"generated_segment_row"}
```

The `id` and `docid` fields intentionally contain the same value. Many indexers expect `id`, while TREC RAG outputs use the term `docid`.

## Indexing Requirement

When building a custom search index, the generated `docid` must be stored as the external document ID returned by retrieval. TREC RAG retrieval and RAG outputs must cite these docids exactly.

Do not let the indexer replace them with internal row numbers, dense integer IDs, generated UUIDs, content hashes, or framework-specific primary keys.

For chunked or passage-level indexes, preserve a mapping from each chunk back to the parent ClimbMix `docid`. Final TREC RAG run files should cite the parent ClimbMix document ID unless official task instructions require a different granularity.

## Reordering Warning

For ClimbMix rows without ID fields, document IDs are row-position dependent. Any preprocessing that changes row positions before docid assignment changes the IDs.

Do not reorder, filter, deduplicate, shard, concatenate, or repartition records before assigning docids. If filtering or repartitioning is needed for a local experiment, first assign and persist the official docids, then transform the corpus while preserving those IDs.

## Stage1 Spot Checks

If stage1 candidate JSONL files are available, use:

```bash
python skills/trec-rag-climbmix-corpus-creation/scripts/create_climbmix_corpus.py \
  /path/to/climbmix-parquet \
  --check-stage1 /path/to/stage1_candidates.jsonl \
  --max-checks 20
```

The script checks that generated docids match candidate docids and that source text matches the candidate document text. Whitespace-normalized text matches are reported separately as `compact_text_match`.

Treat any `FAIL` line as a blocker before indexing or evaluating, unless the mismatch is understood and intentionally outside the TREC RAG corpus contract.

## Live API Spot Checks

For stronger validation of the local docid-generation rule, use the optional API validator:

```bash
python skills/trec-rag-climbmix-corpus-creation/scripts/validate_climbmix_docids_api.py \
  /path/to/climbmix-parquet \
  --sample-size 20
```

The validator samples local Parquet rows, generates docids with the same corpus creation logic, fetches each generated docid from:

```text
GET /v1/climbmix-400b/doc/{docid}
```

and compares the API document text to the local Parquet row text.

This confirms that the bundled corpus creation script matches the official hosted `climbmix-400b` API for the sampled rows. It does not validate a user-built dense, sparse, hybrid, or chunked index after indexing. To validate a custom index, separately query that index and confirm its returned external IDs map back to the official ClimbMix `docid` values.

Authentication follows the `pyserini-rest-api` skill's token-safety rules. The script can use `PYSERINI_API_TOKEN`, `.env.local`, or `.curlrc.pyserini-rest`; it must not print tokens or authorization headers.

Useful options:

- `--base-url`: override the Pyserini REST API base URL.
- `--index`: override the index name; default is `climbmix-400b`.
- `--sample-size`: number of local rows to check.
- `--row`: check one or more specific zero-based row numbers.
- `--text-field`: force a particular local text field.
- `--sleep`: add delay between API requests.

Treat API validation as optional integration validation of corpus generation because it depends on network access, service availability, and a valid Pyserini API token. Do not block deterministic local corpus creation solely because the hosted API is unavailable.
