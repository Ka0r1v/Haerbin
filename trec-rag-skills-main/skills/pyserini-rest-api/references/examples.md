# Examples

Use these examples when running common Pyserini REST API requests manually. Replace `<base-url>` with the current service location from `SKILL.md`.

## Basic Search

```bash
curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-search.json "<base-url>/v1/climbmix-400b/search?query=Albert%20Einstein&hits=5"
jq . tmp/pyserini-rest-search.json
```

## Compact Result List

```bash
curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-search.json "<base-url>/v1/climbmix-400b/search?query=Albert%20Einstein&hits=5"
jq '.candidates[] | {rank, score, docid}' tmp/pyserini-rest-search.json
```

## Fetch One Document

```bash
curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-doc.json "<base-url>/v1/climbmix-400b/doc/shard_00459_61697"
jq . tmp/pyserini-rest-doc.json
```

## FineWeb-Edu Search

```bash
curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-fineweb-edu-search.json "<base-url>/v1/fineweb-edu-100b-karpathy/search?query=Albert%20Einstein&hits=5"
jq '.candidates[] | {rank, score, docid}' tmp/pyserini-rest-fineweb-edu-search.json
```

## MS MARCO V2.1 Segmented Doc Search

```bash
curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-msmarco-v21-segmented-doc-search.json "<base-url>/v1/msmarco-v2.1-doc-segmented/search?query=Albert%20Einstein&hits=5"
jq '.candidates[] | {rank, score, docid}' tmp/pyserini-rest-msmarco-v21-segmented-doc-search.json
```
