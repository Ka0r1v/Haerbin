# Advanced Retrieval v3 实验报告

评测口径：22 个开发 topic、相关阈值 `>=2`、NIST `trec_eval`、Codex UMBRELA qrels。nDCG 使用 graded linear gain。

## 技术适用性

| 技术 | 是否应用 | 实现 |
| --- | --- | --- |
| 混合检索 | 是 | BM25/多查询候选与 BGE-small bi-encoder dense 排名做 RRF |
| 查询构建与分发 | 是 | 原查询、压缩查询、子查询使用独立路由权重 |
| 查询重构 | 已有并增强 | DeepSeek 压缩 + 5 个 aspect 子查询 |
| RRF | 是 | 查询路由、dense、cross-encoder、ColBERT 排名均用 weighted RRF 校正 |
| Cross-Encoder | 已有 | MiniLM 粗排 5000，BGE v2-m3 精排 1000 |
| ColBERT | 是 | ColBERTv2 token-level embeddings + MaxSim，重排 Top-100 |
| RankLLM | 是 | DeepSeek listwise 重排 Top-20，严格候选编号验证和缓存 |
| 压缩 | 是 | query-aware 相关句抽取，每篇 RankLLM 输入限制 900 字符 |
| 校正 | 是 | 原排名保护权重、非法编号过滤、去重、缺失候选原序补齐 |
| Text2SQL | 否 | 当前没有关系数据库、schema 或 SQL 检索端点 |
| Text2Cypher | 否 | 当前没有知识图谱、图 schema 或 Cypher 端点 |

## 消融结果

| Run | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | Recall@5000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 官方 BM25 | 0.5940 | 0.5881 | 0.1081 | 0.2664 | 0.2664 | 0.1381 |
| Balanced v2 | 0.7210 | 0.6655 | 0.0996 | 0.3381 | 0.5225 | 0.1913 |
| Dense hybrid 独立（o2） | 0.6676 | 0.6380 | 0.1013 | 0.3450 | 0.5225 | 0.1962 |
| Balanced v2 + Dense | 0.7150 | **0.6680** | 0.1016 | **0.3423** | 0.5225 | **0.1938** |
| 再加 ColBERT Top-100 | 0.7214 | 0.6651 | 0.1016 | **0.3423** | 0.5225 | 0.1936 |
| 再加 RankLLM Top-20（v3） | **0.7243** | 0.6658 | 0.1016 | **0.3423** | **0.5225** | 0.1937 |

查询路由权重中，`baseline=4, compressed=2, subquery=1` 把候选阶段 Recall@1000 从 `0.3178` 提高到 `0.3195`、Recall@5000 从 `0.5225` 提高到 `0.5241`，但 nDCG@10 从 `0.6347` 略降到 `0.6339`。把该路由 run 再融入最终结果会降低 nDCG，因此保留为可选参数，不进入 v3 默认 run。

## 三套 qrels 稳定性

| qrels | v3 nDCG@10 | v3 nDCG@20 | Recall@1000 | Recall@5000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Codex | 0.7243 | 0.6658 | 0.3423 | 0.5225 | 0.1937 |
| Ministral | 0.8138 | 0.7637 | 0.3015 | 0.4781 | 0.2156 |
| Qwen | 0.7215 | 0.6936 | 0.3285 | 0.5148 | 0.1993 |

## 最终链路

```text
Pyserini BM25
→ DeepSeek 查询压缩/分解/路由
→ weighted RRF Top-5000
→ MiniLM cross-encoder Top-5000
→ BGE v2-m3 cross-encoder Top-1000
→ BGE-small dense hybrid RRF
→ ColBERTv2 MaxSim Top-100
→ 压缩后的 DeepSeek RankLLM Top-20
→ haerbin-hybrid-v3-dev.tsv
```

Dense 首次对约 10.8 万个 topic-document pair 编码约 24 分钟，之后读取缓存。ColBERT Top-100 GPU 打分约 19 秒。RankLLM 22 题首次调用约 8 分钟，之后读取缓存约 1 秒。
