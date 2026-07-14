# TREC RAG 2026 Track Reference

Sources checked June 17, 2026:

- Home: https://trec-rag.github.io/
- NIST TREC 2026 call for participation: https://trec.nist.gov/cfp.html
- GitHub org: https://github.com/TREC-RAG
- Development data: https://github.com/TREC-RAG/trec-rag-data/tree/main/trec-rag-2026/development-data

## Summary

TREC RAG 2026 is the returning Text REtrieval Conference track for retrieval-augmented generation systems; the 2026 track is agent-first and uses NVIDIA's ClimbMix-400b corpus/index. This overview reference summarizes public overview, participation, timeline, and organizer information, while task-level guidelines are covered by the main `trec-rag-2026-track-guidelines` skill.

## Track Goals

The goals of TREC RAG 2026 are:

1. **Automating Deep Research Question Generation**
   - Given a corpus, can we automatically generate open-ended deep research questions that have underspecified goals, surface long-tail domains, and require many intermediate retrieval and reasoning steps to answer?
2. **Developing Improved Evaluation Techniques for Agentic Search**
   - Developing accurate evaluation metrics for assessing retrieval in agentic search.
   - Developing accurate methods to evaluate agentic search answers through side-by-side answer comparisons.
3. **Aligning Deep Research Datasets with LLM Pre-Training Corpora**
   - *Fairness*: Building a testbed to fairly evaluate when LLMs are "memorizing" versus genuinely "generalizing," since we know what the LLM has seen.
   - *Disentanglement*: Building a controlled setting for isolating the contributions of retrieval from the contributions of parametric knowledge in agentic search systems.
4. **Understanding and formulating what an agent-first community evaluation would look like**
   - Conducting a refreshed evaluation of modern coding agents, such as Codex and Claude Code, as automatic system-vs.-system "assessors" compared with humans and previous-generation LLMs.
   - Exploring how agents can reduce the overhead of participating in community evaluation efforts and broaden participation.

## 2026 Status

- The site announces that TREC RAG is returning for 2026 as one of the TREC 2026 tracks.
- The site announces that TREC RAG 2026 will be agent-first and points agents to the TREC-RAG `trec-rag-skills` repository.
- The site announces that TREC RAG 2026 will use NVIDIA's ClimbMix-400b.
- Development queries for RAG 2026 are released at https://github.com/TREC-RAG/trec-rag-data/tree/main/trec-rag-2026/development-data so teams can test systems before the official evaluation topics are released in early July. The development data includes RAG25 and ResearchRubrics topic TSV files, RAG25 answer nuggets, RAG25 UMBRELA qrels over ClimbMix-400b, and ResearchRubrics evaluation rubrics.
- The public site says guidelines have been released and points to the `trec-rag-2026-track-guidelines` skill.
- The released 2026 tasks are Retrieval (`R`) and Retrieval-Augmented Generation (`RAG`): the Retrieval task ranks passages for supplied topics using ClimbMix through the Pyserini REST API or a custom retrieval system; the RAG task retrieves evidence and returns a summarized answer grounded in that evidence.
- Use `references/development-data.md` when people want to test or evaluate systems with the released development topics, nuggets, rubrics, and qrels; it explains what each file is and how to use it safely.
- Use `trec-rag-2026-track-guidelines` for task rules, baselines, output formats, ClimbMix/Pyserini defaults, and validation.
- The submission deadline is public as August 7th, but upload procedures and portal-specific requirements should be verified from the official site before submission-critical work.
- Current TREC RAG website timeline:
  - Test topics released: July 6th.
  - Baselines released: soon after July 6th.
  - Submission deadline: August 7th.
  - Results and judgments returned: TBD.
  - TREC 2026 Conference: November 2026.

## Participation Guidance

- Register for TREC through NIST/Evalbase. The home page says to use the first bullet under Schedule to register an organization in Evalbase.
- Use the TREC RAG website timeline for track-specific dates; use the NIST TREC 2026 call for participation for general TREC registration, organization, and conference participation context.
- Join the Google Groups mailing list, Discord, and SIGIR Slack.
- Include "TREC RAG" in Google Groups join requests.
- Contact njedidi@uwaterloo.ca for issues joining.

## 2026 Organizers

- Nour Jedidi, University of Waterloo
- Lingwei Gu, University of Waterloo
- Pouya Sadeghi, University of Waterloo
- Daniel Campos, Zipf AI
- Nandan Thakur, University of Waterloo
- Nick Craswell, Microsoft
- Ronak Pradeep, University of Waterloo
- Shivani Upadhyay, University of Waterloo
- Jimmy Lin, University of Waterloo

## Handling Prior-Year Questions

This reference intentionally excludes 2024 and 2025 details.

- For TREC RAG 2025 questions, refer users to https://trec-rag.github.io/trec25/
- For TREC RAG 2024 questions, refer users to https://trec-rag.github.io/trec24/
- If asked about task-level 2026 differences from 2025, use `trec-rag-2026-track-guidelines` for the 2026 side and refer to the 2025 page for prior-year details.
