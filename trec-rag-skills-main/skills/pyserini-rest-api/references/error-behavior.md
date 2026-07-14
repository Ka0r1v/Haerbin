# Error Behavior

Use this reference when debugging Pyserini REST API client behavior, validating error handling, or explaining observed non-`200` responses.

Verified responses:

- Missing `query`:

```json
{"error":"Parameter 'query' is required"}
```

- `hits=0`:

```json
{"error":"Parameter 'hits' must be positive"}
```

- `hits=abc`:

```json
{"error":"Parameter 'hits' must be an integer"}
```

- `parse=maybe`:

```json
{"error":"Parameter 'parse' must be 'true' or 'false'"}
```

- Invalid index:

```json
{"error":"Unable to open index: no-such-index"}
```

- Missing document:

```json
{"error":"Document not found: no-such-docid"}
```

- Non-`GET` request:

```json
{"error":"Only GET is supported"}
```

Status codes observed:

- `400` for invalid parameters and invalid index
- `404` for missing document
- `405` for unsupported method
