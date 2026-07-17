# Bundled Retrieval Data

本目录只打包 Retrieval MVP 所需的小型公开文件，没有包含 ClimbMix 原始语料或索引。

来源：[TREC-RAG/trec-rag-data](https://github.com/TREC-RAG/trec-rag-data)，同步提交：

```text
1de1b22ac7f9936be7e42c9e70d576cc9cb83770
```

文件：

- `topics/rag25-topics-dev.tsv`：2026 开发用的 22 个 RAG25 topic。
- `topics/trec_rag_2026_queries.tsv`：2026 正式测试 topics。
- `qrels/*.qrels`：开发 topic 在 ClimbMix 候选池上的三份 UMBRELA qrels。

Qrels 是 LLM 对候选池生成的 0–4 级判断，不是全 ClimbMix 的穷举判断。数据若有更新，应以官方仓库为准。
