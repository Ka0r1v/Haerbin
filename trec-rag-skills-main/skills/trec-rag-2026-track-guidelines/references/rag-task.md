# Retrieval-Augmented Generation Task (`RAG`)

Use this reference when building, explaining, or validating the TREC RAG 2026 Retrieval-Augmented Generation task.

## Task Summary

- **Given**: a list of topics and access to ClimbMix retrieval results and document contents.
- **Task**: retrieve relevant evidence and return a summarized answer grounded in that evidence.
- **Notes**: this task best matches an industrial RAG setup that combines retrieval, evidence selection, and generation. The answer should be evaluated as both an answer and a grounded, cited use of retrieved material.

Unlike the removed `AG` task, the 2026 `RAG` task does not assume a fixed provided evidence set. The system is responsible for retrieval. Use the Pyserini REST baseline retriever when focusing on answer generation.

## Input Format: Topics

Use the same `trec_rag_2026_queries.tsv` topic file as the Retrieval task. Each input line contains two tab-separated fields: topic ID and topic text. Preserve the topic ID exactly in `metadata.narrative_id` and copy the topic text exactly into `metadata.narrative`.

Example:

```tsv
rag2026-37	I work for a New York City council member whose district has a lot of transit riders but also some small businesses worried about delivery costs. Can you help me understand whether congestion pricing is a credible and fair way to fund the MTA? What should we weigh about the revenue promise, who pays, who benefits, environmental tradeoffs in places like the Bronx and New Jersey, and whether the MTA and Albany can be held accountable for actually spending the money on reliable service instead of repeating past mistakes?
```

## Input Format: Documents

Use ClimbMix documents returned by retrieval as the evidence source. Search returns candidate objects with `docid`, `rank`, `score`, and `doc`; document fetch returns a wrapper with `docid` and `doc`.

```json
{
  "docid": "shard_00459_61697",
  "rank": 1,
  "score": 12.483799934387207,
  "doc": "..."
}
```

A RAG system may:

- Use the document text from `doc` returned directly in search results.
- Fetch full document contents with `GET /v1/climbmix-400b/doc/{docid}`.
- Apply its own chunking or passage selection internally.

The Pyserini REST API schema allows `doc` to be a string, object, array, number, boolean, or null depending on index contents and `parse` behavior. Current ClimbMix search responses commonly return `doc` as a string containing the document text. If `doc` is an object, extract its text-bearing field such as `text` or `contents`; if it is a string, use the string directly.

Use the ClimbMix `docid` as the cited evidence identifier in final RAG `references`. Use the document text only as evidence for writing cited answer sentences. Do not include full document payloads, raw snippets, ranks, or scores in the submitted RAG JSONL unless official instructions explicitly require them.

Do not copy all top-ranked retrieved documents into `references` by default. Include only documents that directly support at least one generated answer sentence.

If a system chunks documents internally, keep final `references` tied to ClimbMix document IDs.

## Output Format: RAG Output

For official submissions, provide JSONL in `rag_output_trec_rag_2026.jsonl`, with one JSON object per topic.

```json
{
  "metadata": {
    "team_id": "my-team",
    "narrative_id": "rag2026-37",
    "narrative": "I work for a New York City council member whose district has a lot of transit riders but also some small businesses worried about delivery costs. Can you help me understand whether congestion pricing is a credible and fair way to fund the MTA? What should we weigh about the revenue promise, who pays, who benefits, environmental tradeoffs in places like the Bronx and New Jersey, and whether the MTA and Albany can be held accountable for actually spending the money on reliable service instead of repeating past mistakes?",
    "run_id": "my-rag-run",
    "run_desc": "BM25 top-100 ClimbMix retrieval with agent-written evidence-grounded sentence answers."
  },
  "references": [
    "shard_00459_61697",
    "shard_01012_88420",
    "shard_00210_44018"
  ],
  "answer": [
    {
      "text": "Congestion pricing should be assessed by whether it can provide reliable dedicated revenue for transit improvements while managing the distribution of costs across drivers, riders, and affected neighborhoods.",
      "citations": [0, 1]
    },
    {
      "text": "A credible plan should also explain how environmental impacts, delivery concerns, and MTA spending accountability will be monitored after implementation.",
      "citations": [1, 2]
    }
  ]
}
```

Required fields:

- `metadata.team_id`: team identifier.
- `metadata.narrative_id`: topic ID from the first column of `trec_rag_2026_queries.tsv`.
- `metadata.narrative`: topic text from the second column of `trec_rag_2026_queries.tsv`, copied exactly.
- `metadata.run_id`: run identifier.
- `metadata.run_desc`: short description of the submitted system or run.
- `references`: ordered list of retrieved ClimbMix document IDs cited by the answer. Do not include uncited documents.
- `answer`: array of sentence-level answer objects. The full response may be up to 1024 words per topic.
- `answer[].text`: answer sentence.
- `answer[].citations`: up to three zero-indexed positions into `references` for that sentence.

Do not add extra keys to the `metadata` object. If a system needs to document prompts, generation type, retrieval configuration, or other diagnostics, include a concise summary in `metadata.run_desc` or keep the details in separate run documentation rather than the submitted RAG JSONL metadata.

## Evaluation

The TREC RAG organizers will evaluate submitted RAG responses using system-by-system battles. For each topic, responses from two submitted systems will be paired for side-by-side comparison, with system identities hidden and presentation order randomized. The evaluator will choose which response is better, or may indicate that the responses are tied when neither is clearly preferable.

Each submitted response will also receive individualized nugget rubric scoring in the style of AutoNuggetizer. This evaluates each response independently against topic-specific nugget criteria rather than only through pairwise comparison.

Both evaluation procedures are organizer-run and are not produced by participant agents or included in the submitted RAG JSONL output. Participants should focus on producing accurate, well-grounded, cited answers; the evaluation will be applied after submission by the organizers.

## Answer Rules

- Break the final answer into individual sentences.
- Keep the full response at or below 1024 words per topic.
- Ground each sentence in retrieved evidence.
- Cite no more than three references per sentence.
- Every citation must be an integer index into `references`.
- Do not cite documents that are missing from `references`.
- Every document in `references` should be cited by at least one answer sentence.
- Sort citation indices by support strength when the system can estimate support.
- Avoid unsupported claims, even if the model knows them from prior knowledge.

## Validation Rules

- `rag_output_trec_rag_2026.jsonl` must be valid JSONL, with one complete object per line.
- Every input topic must have exactly one RAG object unless a subset was explicitly requested.
- Every RAG object must have `metadata`, `references`, and `answer`.
- Every RAG citation must be a valid zero-indexed reference position.
- Every `answer[].citations` array must contain no more than three reference positions.
- Every RAG reference must be cited by at least one answer sentence.
- Every RAG answer must be no more than 1024 words.
- Answer claims must be supported by cited references.
