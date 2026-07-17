# RAGDoll / UMBRELA Top-10 诊断

本报告记录 Advanced Hybrid v3 的一次本地 RAGDoll 评测。评测使用 Castorini 官方 RAGDoll 仓库代码，源码提交为：

```text
1f0671908ab6dc581a61648463e3566ba413b480
```

## 配置

- Retrieval run：`haerbin-hybrid-v3-dev.tsv`
- Topics：22 个公开开发 topics
- 判断范围：每题 Top-10，共 220 个 query-document pair
- Evaluator：RAGDoll `umbrela judge`
- Prompt：官方 UMBRELA `bing` 模板
- Runner：Pi `0.80.10`
- Judge model：`deepseek/deepseek-v4-flash`
- Thinking：`minimal`
- 并发：8

API key 从本地 `.env.local` 映射到进程环境，没有写入输入、输出、报告或 Git。

## 结果

| 项目 | 数值 |
| --- | ---: |
| Judgments | 220 |
| Completed | 220 |
| Failed | 0 |
| Parse failures（grade = -1） | 0 |
| Top-10 nDCG | 0.9034 |
| Grade >= 2 | 141 / 220（64.09%） |
| Grade >= 1 | 218 / 220（99.09%） |
| Mean grade | 1.7773 / 3 |

等级分布：

| UMBRELA grade | 数量 |
| --- | ---: |
| 0 | 2 |
| 1 | 77 |
| 2 | 109 |
| 3 | 32 |

## 解释与限制

这是“官方 RAGDoll 框架与 prompt + DeepSeek judge”的本地诊断，不是 TREC/NIST 最终排行榜成绩，也不是 RAGDoll 默认 judge 模型的结果。

候选池只包含 v3 自己取回的 Top-10，因此 `0.9034` 主要回答“这 10 篇内部排序是否合理”。它不能发现 Top-10 之外遗漏的相关文档，所以不能据此报告可信的 Recall@100、Recall@1000、Recall@5000 或完整 MAP。它也不能与公开 Codex/Ministral/Qwen qrels 的 nDCG 直接比较。

后续进行系统间公平对比时，应合并 BM25、Balanced v2、v3 等系统的 Top-10 或 Top-20，建立统一 shallow pool，再让 RAGDoll 对去重后的候选统一判分。

## 本地文件

以下运行产物有正文、模型输出或体积较大，已通过 `.gitignore` 排除，不提交到仓库：

- `retrieval_mvp/candidates/ragdoll-hybrid-v3-top10.jsonl`
- `retrieval_mvp/candidates/ragdoll-hybrid-v3-top10.tasks.jsonl`
- `retrieval_mvp/candidates/ragdoll-hybrid-v3-top10.judgments.jsonl`
- `retrieval_mvp/candidates/ragdoll-hybrid-v3-top10.raw-events/`
- `retrieval_mvp/tools/ragdoll/`
- `retrieval_mvp/tools/pi/`
