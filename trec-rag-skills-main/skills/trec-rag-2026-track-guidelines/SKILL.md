---
name: trec-rag-2026-track-guidelines
description: Use when discussing, building, validating, or explaining the TREC RAG 2026 track, systems, baselines, participation, or submissions. This skill covers the 2026 track overview, public status, organizers, participation guidance, Retrieval and Retrieval-Augmented Generation tasks, ClimbMix/Pyserini REST retrieval defaults, required input and output formats, citation rules, and validation checks for agent-created TREC RAG 2026 runs.
metadata:
  version: v0.3.0
---

# TREC RAG 2026 Track Guidelines

Use this skill when answering conversational questions about the TREC RAG 2026 track, orienting new participants, preparing a TREC RAG 2026 submission, validating outputs, reasoning about task requirements, or building a baseline. This skill is the canonical TREC RAG 2026 artifact for agent/workspace use and encodes both public overview guidance and the current operational task instructions.

Start with the concise answer the user asked for. Load only the reference files needed for the request. Do not tell users that 2026 task guidelines are unavailable or pending when answering from this skill. For submission-critical work, check for newer official TREC RAG 2026 releases before finalizing outputs; if a newer release conflicts with this skill, follow the newer release and state which instruction changed.

## Audience and Terminology

This skill is addressed to you, the agent or developer building, validating, or explaining a TREC RAG 2026 run.

- Use `team` or `participant` for the official TREC submitter.
- Use `system` for the retrieval or RAG pipeline being built or evaluated.
- Use `user` only when referring to the person giving instructions outside the track specification.

## Core Defaults

- Available 2026 tasks: Retrieval (`R`) and Retrieval-Augmented Generation (`RAG`).
- Removed task: the 2025 Augmented Generation-only task (`AG`) is not a 2026 output.
- The 2026 task guidelines are out in this `trec-rag-2026-track-guidelines` skill for agent/workspace use.
- Submission deadline: August 7th, per the TREC RAG website source checked June 17, 2026.
- Submission upload procedures and portal-specific requirements are still not specified in the public TREC RAG materials; verify them before submission-critical work.
- Primary retrieval corpus/index: ClimbMix.
- Pyserini REST index name: `climbmix-400b`.
- Topic input filename: `trec_rag_2026_queries.tsv`.
- Retrieval output filename: `r_output_trec_rag_2026.tsv`.
- RAG output filename: `rag_output_trec_rag_2026.jsonl`.
- RAG response length: up to 1024 words per topic.
- RAG sentence citation limit: up to 3 references per answer sentence.
- RAG evaluation: organizer-run, anonymized system-by-system battles over submitted responses plus individualized nugget rubric scoring in the style of AutoNuggetizer.
- Retrieval depth: participant-chosen; there is no fixed maximum number of submitted documents per topic.

## Track Overview And Participation

Use [references/trec-rag-overview.md](references/trec-rag-overview.md) for conversational overview questions, current public status, track goals, organizers, participation guidance, source links, and timeline.

- Answer only with 2026 information from the current TREC RAG public materials unless the user explicitly provides newer source material.
- Treat the August 7th submission deadline as public but still verify upload procedures and portal-specific requirements before submission-critical work.
- If the user needs operationally current participation instructions, browse `https://trec-rag.github.io/` before answering because registration, timelines, and guidelines can change.
- If the user asks about TREC RAG 2025 or TREC RAG 2024, do not summarize those years from this skill. Refer them to:
  - 2025: https://trec-rag.github.io/trec25/
  - 2024: https://trec-rag.github.io/trec24/
- If the user asks about task-level differences between 2025 and 2026, use this skill for the 2026 side and refer to the 2025 page for prior-year details.

## What to Read

- For track overview, public status, organizers, participation guidance, source links, and timeline, read [references/trec-rag-overview.md](references/trec-rag-overview.md).
- For Retrieval (`R`) task requirements, output format, and validation rules, read [references/retrieval-task.md](references/retrieval-task.md).
- For Retrieval-Augmented Generation (`RAG`) task requirements, output format, citation rules, and validation rules, read [references/rag-task.md](references/rag-task.md).
- For released development topics, nuggets, rubrics, projected qrels, smoke tests, retrieval tuning, prompt iteration, or practice evaluation, read [references/development-data.md](references/development-data.md).
- For Pyserini REST API access, authentication, endpoint docs, command examples, response parsing, health checks, query behavior, or error handling, use the `pyserini-rest-api` skill.

Read only the reference files needed for the requested task. For API mechanics, route to `pyserini-rest-api` and load only the API references needed for the implementation detail.

## Validation Checklist

Before considering a run complete, verify:

- The run targets only the requested 2026 task: `R`, `RAG`, or both.
- No `AG`-only output is produced.
- Every input topic has output unless a subset was explicitly requested.
- Retrieval output follows [references/retrieval-task.md](references/retrieval-task.md).
- RAG output follows [references/rag-task.md](references/rag-task.md).
- No secrets, API tokens, `.env.local` contents, or authorization headers appear in outputs.

## When Requirements Are Unclear

Treat this skill and its referenced files as the authoritative task instructions for agent-created TREC RAG 2026 runs. If a newer official TREC RAG skill release supersedes this one, follow the newer skill and state which instruction changed. If submission logistics such as deadlines, upload procedures, or portal-specific requirements are not yet specified, state the assumption and proceed with the applicable defaults in this skill.
