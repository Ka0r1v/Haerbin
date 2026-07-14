---
name: pyserini-rest-api
description: Use for accessing the Pyserini REST API, which is the official API for the TREC RAG tracks.
metadata:
  version: v0.2.0
  source_url: https://github.com/TREC-RAG/trec-rag-skills/tree/main/skills/pyserini-rest-api
---

# Pyserini REST API

Use this skill when you need to access the Pyserini REST API or help someone build against it. Search is one route family exposed by the API, not the full API surface.

## Service Location

The Pyserini REST API is currently exposed at:

```text
http://api.castorini.uwaterloo.ca
```

The service location is liable to change. Consult the `pyserini-rest-api` skill in the https://github.com/TREC-RAG/trec-rag-skills/ repository for the latest service location and usage guidance.

Command examples use `<base-url>` as a placeholder for the current service location.

## Dataset Configuration

Use these exact dataset-to-index mappings:

- MS MARCO V2.1 Segmented Doc: `msmarco-v2.1-doc-segmented`
- ClimbMix: `climbmix-400b`
- FineWeb-Edu: `fineweb-edu-100b-karpathy`

When the user asks for a dataset by name, map it to the corresponding index above. If the user provides an explicit index, use it as given after confirming it matches the intended dataset when the context is ambiguous.

If the dataset or index is not clear from context, ask the user which index to search before making authenticated search or document-fetch requests. If the user asks which indexes are available, provide the dataset configuration above.

## Authentication Workflow

The Pyserini REST API requires a Pyserini access token. Use the repo-local workflow below unless the user has already provided another secure token mechanism. Token safety rules are mandatory.

### Token Access

If the user does not have a Pyserini API token, tell them to email `get-pyserini@googlegroups.com` to request one.

Mandatory token safety rules:

- Do not attempt authenticated searches or document fetches unless a token is available through a safe local mechanism.
- Never commit `.env.local`, never paste the token into chat, and never print it in command output.
- Never commit `.curlrc.pyserini-rest`, and never print its contents.
- Do not put the token in tracked files, examples, logs, shell history snippets, command lines, or skill documentation.

Recommended repo-local workflow:

- Ask the user for the Pyserini API token if it is not already available locally.
- Store the token in the repo-local `.env.local` file as `PYSERINI_API_TOKEN=...`.
- Prefer storing the curl authorization header in the repo-local `.curlrc.pyserini-rest` file.
- If `.env.local` already exists, read only enough to determine whether `PYSERINI_API_TOKEN` is present; do not display the file contents.
- If `.curlrc.pyserini-rest` is missing but `.env.local` has `PYSERINI_API_TOKEN`, create `.curlrc.pyserini-rest` with mode `600` and a single authorization header derived from the token.
- If `.curlrc.pyserini-rest` exists but authenticated requests fail after confirming `PYSERINI_API_TOKEN` is present, regenerate `.curlrc.pyserini-rest` from `.env.local` without printing either file.
- Use `.curlrc.pyserini-rest` for requests:

```bash
curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-search.json "<base-url>/v1/climbmix-400b/search?query=anserini&hits=5"
jq . tmp/pyserini-rest-search.json
```

Rationale: using `curl -sS -K .curlrc.pyserini-rest` keeps the token out of visible command lines and creates a stable command prefix that can be approved once for network access. After that approval is persisted, future Pyserini REST requests can reuse the same prefix without repeated escalation prompts.

When using `jq`, prefer saving the `curl` response to a temporary JSON file with `-o` and then running `jq` as a separate local command. Do not pipe `curl` directly into `jq`; the sandbox treats each pipeline segment as a separate command and may require repeated escalation for otherwise local JSON inspection.

If the API returns an authorization error, tell the user the local token appears missing, expired, or invalid without revealing any token value.

## Endpoints

The service presents an OpenAPI-compliant REST API. Use the interactive and machine-readable documentation when discovering endpoints or generating clients:

- Swagger UI: `<base-url>/docs`
- ReDoc: `<base-url>/redoc`
- OpenAPI JSON: `<base-url>/openapi.json`
- OpenAPI YAML: `<base-url>/openapi.yaml`

Endpoint paths are relative to `<base-url>`:

- `GET /`
- `GET /v1/{index}/search`
- `GET /v1/{index}/doc/{docid}`

## Health Check

Use this procedure when the user asks whether the Pyserini REST API server is up.

Start with the unauthenticated root endpoint. This confirms that the HTTP service is reachable without needing to touch the local token:

```bash
curl -sS -i --max-time 10 "<base-url>/"
```

The server is reachable if this returns `HTTP/1.1 200 OK` and a JSON body like:

```json
{"name":"Pyserini API","version":"v1","description":"REST API aligned with Anserini (Lucene indexes via Pyserini).","openapi":"/openapi.yaml","documentation":"/docs"}
```

Then run a minimal authenticated search to verify that the search endpoint, index, token, and retrieval path are working. The command below uses the recommended repo-local curl workflow; adapt the authorization mechanism if the user provided a different secure token setup. Use `Albert Einstein` as the standard health-check query. ClimbMix is the default health-check dataset unless the user asks to check a specific dataset. If the user asks to health-check all indexes, run the same query against every index in Dataset Configuration.

```bash
curl -sS -K .curlrc.pyserini-rest --max-time 15 -o tmp/pyserini-rest-health-search.json -w '%{http_code}\n' "<base-url>/v1/climbmix-400b/search?query=Albert%20Einstein&hits=1"
```

Expected status:

```text
200
```

Inspect the saved response with `jq` as a separate local command:

```bash
jq '{api,index,query,candidate_count:(.candidates | length),first:(.candidates[0] // null | if . == null then null else {rank,docid,score,has_doc:(.doc != null)} end)}' tmp/pyserini-rest-health-search.json
```

A healthy search response should include `api`, `index`, `query`, `candidate_count` greater than zero, and a first candidate with `rank`, `docid`, `score`, and `has_doc: true`.

Interpretation:

- Root endpoint returns `200`, authenticated search returns `200`, and `has_doc` is `true`: the API server is up and the search route is working.
- Root endpoint returns `200` but authenticated search returns `401` or an authorization error: the service is up, but the local token is missing, expired, or invalid.
- Root endpoint returns `200` but search returns an index error: the service is up, but the requested index may be unavailable or misnamed.
- Root endpoint times out or cannot connect: the service is likely down or unreachable from the current network.
- Do not print `.curlrc.pyserini-rest`, `.env.local`, or any authorization header while checking health.

## Request Model

### Search

```text
GET /v1/{index}/search?query=...&hits=...
```

Parameters:

- `query`: required string
- `hits`: optional positive integer, default `10`
- `parse`: optional boolean, default `true`; omit it unless the user explicitly asks to control raw vs. parsed output. See `references/search-behavior.md` for detailed `parse` behavior.

### Document Fetch

```text
GET /v1/{index}/doc/{docid}
```

Parameters:

- `docid`: required path string
- `parse`: optional boolean, default `true`; omit it unless the user explicitly asks to control raw vs. parsed output. See `references/search-behavior.md` for detailed `parse` behavior.

## Response Shape

For search and document response examples, read `references/search-behavior.md` when implementing clients, inspecting `doc` contents, or validating response parsing. By default, `doc` is returned as a parsed JSON structure when possible.

## Search Route Behavior

For detailed behavior of `/v1/{index}/search` and `/v1/{index}/doc/{docid}`, read `references/search-behavior.md` when implementing clients, debugging `parse` output, answering questions about raw stored payloads, or reasoning about query semantics.

## Error Behavior

For verified error response bodies and observed status codes, read `references/error-behavior.md` when debugging clients, validating error handling, or explaining non-`200` API responses.

## Useful Commands

For manual request examples, read `references/examples.md` when the user asks for sample `curl` commands, compact result lists, or dataset-specific request examples.

## References

- `references/search-behavior.md`: response shape, `parse` behavior, raw stored payloads, and query semantics.
- `references/error-behavior.md`: verified error response bodies and observed non-`200` status codes.
- `references/examples.md`: manual `curl` and `jq` examples for common API requests.

## Workflow

When helping with this API:

1. Confirm the dataset or index name. Map ClimbMix to `climbmix-400b`, FineWeb-Edu to `fineweb-edu-100b-karpathy`, and MS MARCO V2.1 Segmented Doc to `msmarco-v2.1-doc-segmented`.
2. If the dataset or index is unclear from context, ask the user which index to search. If the user asks what is available, answer with the mappings from Dataset Configuration.
3. Use an available secure token mechanism. If using the recommended repo-local workflow, check whether `.env.local` contains `PYSERINI_API_TOKEN` without printing it.
4. If no token is available, ask the user for one. If they do not have a token, tell them to email `get-pyserini@googlegroups.com` to request one.
5. If using the recommended repo-local workflow, ensure `.curlrc.pyserini-rest` exists, is ignored by git, and has mode `600`.
6. When using the recommended repo-local curl workflow, use `curl -sS -K .curlrc.pyserini-rest -o tmp/pyserini-rest-*.json` for all Pyserini REST requests so the token stays out of command lines and the command prefix can be approved once for network access.
7. Use `/v1/{index}/search` for retrieval and `/v1/{index}/doc/{docid}` for follow-up fetches.
8. Run `jq` only as a separate local command against the saved `tmp/pyserini-rest-*.json` file; avoid `curl | jq` pipelines.
9. Omit `parse` by default; read `references/search-behavior.md` before changing it.
10. Formulate queries as ordinary text; avoid assuming Lucene query syntax support.
11. Read `references/search-behavior.md` when the user asks about raw stored payloads, query semantics, or detailed response interpretation.
12. Read `references/error-behavior.md` when debugging clients or explaining non-`200` API responses.
13. When debugging clients, check HTTP status and the JSON `error` field first.
