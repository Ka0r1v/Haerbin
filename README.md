# Haerbin

TREC RAG 2026 项目仓库，覆盖 Retrieval（检索）与 Retrieval-Augmented Generation（检索增强生成）两项任务。

## 两项任务

| 任务 | 核心目标 | 提交文件 |
| --- | --- | --- |
| Retrieval (`R`) | 为每个 topic 检索并排序相关 ClimbMix 文档 | `r_output_trec_rag_2026.tsv` |
| Retrieval-Augmented Generation (`RAG`) | 检索证据，生成逐句引用且有证据支撑的答案 | `rag_output_trec_rag_2026.jsonl` |

两项任务使用同一个 `trec_rag_2026_queries.tsv` 和 ClimbMix 文档集合。RAG 包含检索环节，可以复用 Retrieval 系统的结果，再进行证据筛选、答案生成和引用绑定。

## 文档

- [中文任务讲解与对照](docs/task-overview-zh.md)
- [Retrieval Task 官方说明整理](docs/retrieval-task.md)
- [RAG Task 官方说明整理](docs/rag-task.md)

## 关键提交规则

- topic ID 和原始 topic 文本必须与官方输入保持一致。
- Retrieval 输出每行必须有六个字段，且每个 topic 的 rank 从 1 开始。
- RAG 输出必须是合法 JSONL，每个 topic 对应一个完整 JSON 对象。
- RAG 答案按句子组织，每句最多引用三个 `references` 中的文档。
- 只引用真正支持答案内容的 ClimbMix 文档，避免无依据陈述。

## 来源

赛题说明整理自 [TREC-RAG/trec-rag-skills](https://github.com/TREC-RAG/trec-rag-skills)。如本仓库内容与官方最新说明不一致，以官方说明为准。
