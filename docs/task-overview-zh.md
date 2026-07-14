# TREC RAG 2026 两项任务讲解

TREC RAG 2026 包含 Retrieval（`R`）和 Retrieval-Augmented Generation（`RAG`）两项任务。两者读取相同的 topic，并以 ClimbMix 为检索语料，但最终目标和提交格式不同。

## Retrieval Task

Retrieval Task 只评估“找文档”的能力。系统需要针对每个 topic 检索 ClimbMix，并把相关文档按相关程度排序。

基本流程：

```text
topic → 查询改写/拆分 → ClimbMix 检索 → 结果融合与重排 → 文档排名
```

提交文件是 `r_output_trec_rag_2026.tsv`，每行包含：

```text
topic_id Q0 docid rank score run_id
```

我们需要实现查询处理、候选召回、结果融合、文档重排、runfile 生成和格式校验。可以直接使用官方 `climbmix-400b` 索引，也可以使用自建检索系统。

## RAG Task

RAG Task 评估完整的“检索后回答”能力。系统不仅要找到相关文档，还要阅读证据、生成答案，并明确说明每个答案句子由哪些文档支持。

基本流程：

```text
topic
  ↓
检索和重排 ClimbMix 文档
  ↓
证据筛选与内部 chunk/passage 选择
  ↓
基于证据生成逐句答案
  ↓
将每句话绑定到 ClimbMix docid
  ↓
输出 JSONL
```

RAG 任务没有提供固定证据集。检索仍由参赛系统负责；如果主要研究答案生成，可以用官方 Pyserini 检索作为 baseline。

提交文件是 `rag_output_trec_rag_2026.jsonl`，每个 topic 对应一行 JSON，主要包括：

- `metadata`：团队、topic、run 等信息。
- `references`：答案实际引用的 ClimbMix 文档 ID 列表。
- `answer`：逐句答案，每句话包含 `text` 和指向 `references` 的 `citations`。

答案总长度不超过 1024 个单词；每句话最多引用三个文档。不能把所有召回文档都塞进 `references`，只有真正支撑答案句子的文档才能出现。

## 两项任务的关系

| 对比项 | Retrieval | RAG |
| --- | --- | --- |
| 输入 topic | 相同 | 相同 |
| 文档集合 | ClimbMix | ClimbMix |
| 是否需要检索 | 是 | 是 |
| 是否需要生成自然语言答案 | 否 | 是 |
| 是否需要逐句引用 | 否 | 是 |
| 输出 | 文档排名 TSV | 答案与引用 JSONL |
| 主要能力 | 召回、融合、重排 | 检索、证据筛选、生成、引用正确性 |

Retrieval 可以看作 RAG 的上游模块：

```text
Retrieval 系统输出的高质量候选文档
                  ↓
RAG 系统筛选证据并生成有引用的答案
```

两项任务可以共用查询改写、Pyserini 客户端、候选缓存、结果融合和 reranker。Retrieval 提交要求输出完整的文档排名；RAG 的 `references` 则只保留最终答案实际使用的文档，不应直接复制 Retrieval 的全部 Top K。

## 我们需要做什么

推荐先搭建一条共享流水线，再分别产生两种提交：

1. 读取并严格保留官方 topic ID 与原文。
2. 将复杂 topic 拆成多个可检索的子查询。
3. 调用官方 ClimbMix/Pyserini 索引召回候选文档。
4. 融合多查询结果，并使用 reranker 重新排序。
5. 从排序结果生成 Retrieval TSV。
6. 为 RAG 进一步读取正文、选择能直接支持回答的证据。
7. 让生成模型只基于证据形成逐句答案，并为每句话绑定引用。
8. 生成 RAG JSONL，并自动检查引用下标、字段、长度和证据覆盖。

工程上应把“检索”和“答案生成”解耦。这样可以单独评测检索效果，也可以更换生成模型，而不必重复访问和处理全部候选文档。
