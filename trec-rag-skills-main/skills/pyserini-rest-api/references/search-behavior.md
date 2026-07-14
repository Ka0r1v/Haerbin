# Search Route Behavior

Use this reference when working with `/v1/{index}/search` or `/v1/{index}/doc/{docid}` behavior in detail, especially `parse` handling or query interpretation.

## Response Shape

Search returns:

```json
{
  "api": "v1",
  "index": "climbmix-400b",
  "query": { "text": "anserini" },
  "candidates": [
    {
      "docid": "shard_00459_61697",
      "score": 12.483799934387207,
      "rank": 1,
      "doc": "..."
    }
  ]
}
```

The `index` field should match the index requested, for example `climbmix-400b` for ClimbMix, `fineweb-edu-100b-karpathy` for FineWeb-Edu, or `msmarco-v2.1-doc-segmented` for MS MARCO V2.1 Segmented Doc.

Document fetch returns:

```json
{
  "api": "v1",
  "index": "climbmix-400b",
  "docid": "shard_00459_61697",
  "doc": "..."
}
```

By default, `doc` is returned as a parsed JSON structure when possible.

## `parse` Behavior

- `parse=true` or omitted: return parsed document contents when possible.
- `parse=false`: return the raw stored document string.
- For the configured indexes, `parse=false` returns the stored JSON string. ClimbMix and FineWeb-Edu documents commonly include fields such as `id` and `text`; MS MARCO V2.1 Segmented Doc documents include segment-oriented fields such as `url`, `title`, `headings`, and `segment`.
- Client-side parsing works with `jq '... | fromjson'`.
- Unless the user explicitly asks for raw stored output, do not send the `parse` parameter at all.
- This applies to both `/search` and `/doc/{docid}` requests.

Examples:

```bash
curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-search-raw.json "<base-url>/v1/climbmix-400b/search?query=anserini&hits=1&parse=false"
jq '.candidates[0].doc | fromjson' tmp/pyserini-rest-search-raw.json
```

```bash
curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-doc-raw.json "<base-url>/v1/climbmix-400b/doc/shard_00459_61697?parse=false"
jq '.doc | fromjson' tmp/pyserini-rest-doc-raw.json
```

Practical guidance:

- Do not include `parse` in requests by default.
- Only specify `parse=false` when the user explicitly asks for the raw stored payload.
- Only specify `parse=true` when the user explicitly asks to see or control the parameter.
- If you are simply inspecting documents to answer a question, fetch them with the default behavior and omit `parse`.

## Query Semantics

Treat `query` as analyzed text, not as a Lucene query language surface.

Observed behavior from ClimbMix query experiments:

- Case-insensitive: `anserini` and `AnSeRiNi` behave identically.
- Quotes do not materially change ranking: `"what is anserini"` matched `what is anserini`.
- Boolean/operator-like syntax was inert for ranking in these experiments:
  - `anserini lucene`
  - `anserini AND lucene`
  - `anserini OR lucene`
  - `+anserini +lucene`
  - `anserini -lucene`
  all produced the same top results and scores.
- Fielded syntax is not exposed meaningfully: `text:anserini` returned zero hits.
- Punctuation is normalized: `anserini?` behaved like `anserini`.
- Hyphenation is normalized: `open-source` behaved like `open source`.
- Morphological normalization or stemming is likely enabled: `anserinis` behaved like `anserini`.
- No-match queries return an empty `candidates` array.

Practical guidance:

- Use normal natural-language or keyword queries.
- Do not rely on Lucene parser features such as fielded search, boolean operators, or required/prohibited term syntax.
- Treat these query semantics as verified for ClimbMix and likely but not guaranteed for the other configured indexes unless separately tested.
