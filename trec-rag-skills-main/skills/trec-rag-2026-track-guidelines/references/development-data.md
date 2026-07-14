# TREC RAG 2026 Development Data

Sources checked June 12, 2026:

- Data repo: https://github.com/TREC-RAG/trec-rag-data/tree/main/trec-rag-2026/development-data
- Announcement: https://x.com/TREC_RAG/status/2065484729747448042
- TREC RAG 2025 overview: https://arxiv.org/abs/2603.09891
- ResearchRubrics paper: https://arxiv.org/abs/2511.07685
- Nugget background: https://arxiv.org/abs/2504.15068

These links are provenance and optional background. Agents normally should not open them unless the user asks for deeper context, citations, or source verification.

## Summary

TREC RAG 2026 development data is an early public practice set for building and evaluating systems before the official evaluation topics are released. Use it for smoke tests, retrieval tuning, prompt iteration, RAG answer-generation practice, and validation rehearsals.

Do not treat these development topics, projected qrels, nuggets, or rubrics as final official evaluation inputs. Keep exact dataset contents in the `trec-rag-data` repository; this reference explains purpose, schema, and safe usage.

## Topic Files

### `topics/rag25-topics-dev.tsv`

These are narratives from TREC RAG 2025 selected for RAG 2026 development. TREC RAG 2025 used long, multi-sentence narratives to model deep-search information needs that require retrieval, reasoning, synthesis, and grounded generation.

Each row is:

```text
qid<TAB>narrative
```

Use these topics when you want RAG25-style development queries with known diagnostic artifacts. Preserve `qid` exactly when creating local runs, joining against nuggets, or evaluating retrieval against projected qrels.

### `topics/research-rubrics-topics-dev.tsv`

These are prompts from ResearchRubrics, a deep-research benchmark of realistic prompts paired with expert-written, fine-grained rubrics. The ResearchRubrics paper describes the benchmark as covering open-ended deep research tasks that require multi-step reasoning, cross-document synthesis, and evidence-backed long-form answers.

Each row is:

```text
qid<TAB>prompt
```

Use these prompts to practice deep-research answer generation and rubric-based diagnostics. Preserve `qid` exactly when joining prompts to the ResearchRubrics rubric file.

## Diagnostic Files

### `rag25-dev-nuggets/rag25-dev-nuggets.jsonl`

These are diagnostic answer-coverage targets for the RAG25-derived development topics. Nuggets are short semantic information units that a good answer may need to cover. In TREC RAG evaluation, nuggets are mapped to sub-narratives and used to measure answer completeness and coverage.

Each JSONL object has:

- `qid`: topic ID matching `rag25-topics-dev.tsv`.
- `nuggets`: array of nugget objects.
- `nuggets[].text`: short semantic information unit.
- `nuggets[].mapped_sub_narrative`: the sub-narrative or coverage area associated with the nugget.
- `nuggets[].importance`: `vital` or `okay`; vital nuggets represent information that is important for a strong answer, while okay nuggets are useful but less essential.
- `nuggets[].source`: provenance label such as `original` or `post-edit`.

Use nuggets to diagnose whether a generated answer covers important information needs and sub-narratives. Do not use nuggets as citations or as source evidence. A generated answer still needs support from retrieved ClimbMix documents.

### `researchrubrics-dev-rubrics/research-rubrics-dev-rubrics.jsonl`

These are rubric criteria for the ResearchRubrics development prompts. ResearchRubrics pairs realistic prompts with expert-written criteria that assess factual grounding, reasoning soundness, synthesis, clarity, instruction following, and citation quality.

Each JSONL object has prompt metadata plus:

- `qid`: prompt ID matching `research-rubrics-topics-dev.tsv`.
- `domain`: ResearchRubrics topic domain.
- `conceptual_breadth`, `logical_nesting`, `exploration`: prompt complexity labels.
- `rubrics`: array of rubric criteria.
- `rubrics[].criterion`: one criterion to evaluate against an answer.
- `rubrics[].weight`: numeric criterion weight. Positive weights reward desired answer properties; negative weights penalize failure modes.
- `rubrics[].axis`: rubric category, such as communication quality, implicit criteria, instruction following, synthesis, or references and citation quality.

Use these rubrics only to evaluate an agent's generated answer after it is produced. They describe what a strong answer should contain, but they are not source evidence or generation input. Do not cite them as factual support in a submitted RAG answer; cite retrieved ClimbMix documents instead.

### `rag25-dev-umbrela-qrels/*.qrels`

These are projected ClimbMix relevance judgments for the RAG25-derived development topics. They are UMBRELA/model-generated development qrels over ClimbMix document IDs, useful for retrieval tuning and offline metric calculations.

Each file uses standard TREC qrels format:

```text
topic_id 0 docid relevance_grade
```

Example:

```text
14 0 shard_04439_8336 4
```

Use qrels to evaluate retrieval runs with metrics such as nDCG or recall. Treat the relevance labels as development diagnostics, not official final NIST judgments.

The current qrels files correspond to different projected assessor/model variants. If comparing systems, choose one qrels file consistently or report results separately for each qrels variant.

## Recommended Development Workflow

1. Choose a development topic set: RAG25-derived topics for TREC-style narrative diagnostics, or ResearchRubrics prompts for deep-research rubric diagnostics.
2. Retrieve ClimbMix documents using the system under test or the Pyserini/ClimbMix baseline.
3. For retrieval-only work, evaluate ranked output against a selected development qrels file when available.
4. For RAG work on RAG25-derived topics, use nuggets to diagnose answer coverage after verifying that answer claims are grounded in retrieved ClimbMix documents.
5. For RAG work on ResearchRubrics prompts, use the rubric criteria to diagnose answer quality and failure modes.
6. Keep final submission-format validation separate from development diagnostics; development artifacts do not replace official 2026 evaluation topics or submission instructions.
