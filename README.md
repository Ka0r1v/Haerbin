# Haerbin

TREC RAG 2026 Retrieval Task 项目仓库。

## 赛题概览

- 输入：`trec_rag_2026_queries.tsv`，每行包含 topic ID 和查询文本。
- 检索集合：ClimbMix（Pyserini 索引名：`climbmix-400b`），也可以使用自建检索系统。
- 目标：为每个 topic 返回按相关性排序的 ClimbMix 文档 ID。
- 提交文件：`r_output_trec_rag_2026.tsv`。
- 每行格式：`topic_id Q0 docid rank score run_id`。

完整的任务定义、字段说明、示例与校验规则见：

- [TREC RAG 2026 Retrieval Task 说明](docs/retrieval-task.md)

## 提交前检查

- topic ID 必须与官方查询文件完全一致。
- 每个 topic 的 rank 从 1 开始并按升序排列。
- 每个 topic 内的 score 应当非递增。
- 每行必须包含 6 个以空白分隔的字段。
- `docid` 必须是检索系统返回的 ClimbMix 文档 ID。

## 来源

赛题说明整理自 TREC-RAG 官方仓库：
[TREC-RAG/trec-rag-skills — retrieval-task.md](https://github.com/TREC-RAG/trec-rag-skills/blob/main/skills/trec-rag-2026-track-guidelines/references/retrieval-task.md)。
如本仓库内容与官方最新说明不一致，以官方说明为准。
