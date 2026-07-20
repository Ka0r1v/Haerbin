# BM25 / V2 / V3 统一 RAGDoll Shallow-Pool 对比

统一判断池：`ragdoll-bm25-v2-v3-top10.judgments.jsonl`、`ragdoll-bm25-v2-v3-top10.tiebreak.judgments.jsonl`；每个系统评估 Top-10。

| Run | pooled nDCG@10 | grade>=2 | judged |
| --- | ---: | ---: | ---: |
| BM25 | 0.7285 | 49.55% (109/220) | 220 |
| V2 | 0.8465 | 63.18% (139/220) | 220 |
| V3 | 0.8509 | 64.09% (141/220) | 220 |

Judgment distribution：grade 0=12、grade 1=138、grade 2=147、grade 3=44
；failed=2；resolved conflicts=25。

这是同一 BM25/V2/V3 Top-10 并集上的 shallow-pool LLM judgment，适合比较三个系统的 Top-10。它仍然不是全库 qrels，不能计算可信的 Recall@1000/5000 或正式排行榜成绩。
