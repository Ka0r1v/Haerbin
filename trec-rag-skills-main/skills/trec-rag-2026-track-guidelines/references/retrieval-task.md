# Retrieval Task (`R`)

Use this reference when building, explaining, or validating the TREC RAG 2026 Retrieval task.

## Task Summary

- **Given**: a list of topics and access to the ClimbMix collection through the Pyserini REST API or a custom retrieval system.
- **Task**: return a ranked list of relevant ClimbMix document IDs for each topic. Participants may choose how many documents to return per topic.
- **Notes**: this task is the 2026 counterpart of the 2025 Retrieval task, but uses ClimbMix as the primary retrieval collection instead of the MS MARCO V2.1 segmented collection.

## Input Format: Topics

Topics are provided as TSV in `trec_rag_2026_queries.tsv`. Each line contains the topic ID and the topic text, separated by a tab.

```tsv
rag2026-37	I work for a New York City council member whose district has a lot of transit riders but also some small businesses worried about delivery costs. Can you help me understand whether congestion pricing is a credible and fair way to fund the MTA? What should we weigh about the revenue promise, who pays, who benefits, environmental tradeoffs in places like the Bronx and New Jersey, and whether the MTA and Albany can be held accountable for actually spending the money on reliable service instead of repeating past mistakes?
```

Required fields:

- First column: topic identifier. Preserve this exactly in all outputs.
- Second column: topic text, usually a two- to three-sentence description of the information need. Use it as the default initial retrieval query unless the system intentionally performs query rewriting or decomposition internally. For `RAG` output, copy this value exactly into `metadata.narrative`.

## Input Format: Documents

For baseline systems, retrieve ClimbMix documents from the Pyserini REST API. The configured index name is:

```text
climbmix-400b
```

Search returns a response with a `candidates` array. Each candidate represents one retrieved ClimbMix document:

```json
{
  "api": "v1",
  "index": "climbmix-400b",
  "query": { "text": "congestion pricing MTA funding accountability" },
  "candidates": [
    {
      "docid": "shard_00459_61697",
      "rank": 1,
      "score": 12.483799934387207,
      "doc": "..."
    }
  ]
}
```

Document fetch by ClimbMix document ID returns one document wrapper:

```json
{
  "api": "v1",
  "index": "climbmix-400b",
  "docid": "shard_00459_61697",
  "doc": "..."
}
```

Document field rules:

- `docid`: ClimbMix document ID to use in submissions.
- `rank`: returned rank for a search candidate.
- `score`: retrieval score for a search candidate.
- `doc`: ClimbMix document contents. The Pyserini REST API schema allows this payload to be a string, object, array, number, boolean, or null depending on index contents and `parse` behavior. Current ClimbMix search responses commonly return `doc` as a string containing the document text.

Use `docid` as the external identifier in Retrieval run files and RAG `references`. Use the document text from `doc` as evidence content. Do not put full `doc` payloads, raw snippets, `rank`, or `score` in official Retrieval or RAG outputs unless official instructions explicitly require them.

When a system needs full document contents for generation, fetch by `docid` through the document endpoint. If `doc` is an object, extract its text-bearing field such as `text` or `contents`; if it is a string, use the string directly as the document text. If the API returns raw stored JSON instead of parsed content, parse it according to the `pyserini-rest-api` skill before extracting the document text.

## Output Format: Ranked Results

For official submissions, provide a standard TREC runfile in `r_output_trec_rag_2026.tsv`. Each line contains six whitespace-separated fields:

```text
topic_id Q0 docid rank score run_id
```

Example:

```text
1 Q0 shard_00459_61697 1 12.4838 my-run
1 Q0 shard_01012_88420 2 11.9721 my-run
1 Q0 shard_00210_44018 3 10.5542 my-run
2 Q0 shard_00044_91812 1 10.8114 my-run
```

Field rules:

- `topic_id`: topic identifier from `trec_rag_2026_queries.tsv`.
- `Q0`: fixed string.
- `docid`: ClimbMix document ID.
- `rank`: rank of the retrieved document for that topic, starting at 1.
- `score`: numeric score used to rank documents.
- `run_id`: stable identifier for the submitted run.

## Validation Rules

- There is no fixed maximum number of rows per topic; participants may return as many ranked documents as they choose.
- Rows per topic may vary across topics.
- Sort each topic's rows by rank ascending.
- Keep scores non-increasing within each topic.
- `r_output_trec_rag_2026.tsv` must have exactly six whitespace-separated columns per line.
- Retrieval ranks must restart at 1 for each topic.
- Every Retrieval `docid` must be a ClimbMix document ID returned by the retriever or custom index.
- Do not emit MS MARCO segment IDs unless official 2026 instructions explicitly require a mapping step.
