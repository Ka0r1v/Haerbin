# TREC RAG 2026 Retrieval MVP

当前已经跑通的检索链路：

```text
官方 ClimbMix BM25
  → DeepSeek：原查询 + 压缩查询 + 5 条子查询
  → 每条查询取 Top-1000，Weighted RRF 合并到 Top-5000
  → MiniLM 粗排 Top-5000
  → BGE v2-m3 精排 Top-1000
  → 六列 TREC runfile（可保留完整候选池，也可裁成 Top-1000）
```

官方 Pyserini REST API 已提供 `climbmix-400b` 索引，并在响应中返回候选段落正文。本 MVP 不下载整个 ClimbMix，不重新 chunk、建索引或计算全库 embedding；语义模型只给 BM25 召回的候选打相关性分数。

## 数据和脚本

| 文件 | 用途 |
| --- | --- |
| `data/topics/rag25-topics-dev.tsv` | 22 个开发 topic |
| `data/topics/trec_rag_2026_queries.tsv` | 119 个正式测试 topic；没有公开 qrels |
| `data/qrels/*.qrels` | 官方发布的 Codex、Ministral、Qwen 三套 UMBRELA 开发 qrels |
| `src/healthcheck.py` | 检查 `.env.local` 和 Pyserini API 连通性，不打印 token |
| `src/retrieve.py` | 调用官方 ClimbMix Pyserini REST API，生成 BM25 baseline |
| `src/query_rewrite.py` | 启发式或 DeepSeek 查询压缩、方面分解与本地缓存 |
| `src/retrieve_multiquery.py` | 分发原查询、压缩查询和子查询，再做 weighted RRF |
| `src/rrf.py` | 通用 reciprocal rank fusion 实现 |
| `src/rerank.py` | MiniLM/BGE cross-encoder 候选重排与原排名保护 |
| `src/dense_rerank.py` | BGE bi-encoder dense 打分及稀疏/稠密排名融合 |
| `src/colbert_rerank.py` | ColBERTv2 token-level MaxSim Top-N 校正 |
| `src/rankllm_rerank.py` | query-aware 文档压缩、DeepSeek listwise 重排和输出校正 |
| `src/fuse_runs.py` | 融合多个 TREC run，并保留指定输出深度 |
| `src/build_docstore.py` | 将 API 正文缓存整理为 SQLite docid 文本库 |
| `src/export_candidates.py` | 将 runfile 和正文导出为 Ragnarök/RankLLM/RAGDoll 兼容 JSONL |
| `src/validate_run.py` | 校验 topic、docid、rank、分数及六列 TREC runfile 格式 |
| `src/evaluate_run.py` | 纯 Python 快速诊断，使用 linear-gain nDCG |
| `src/official_eval.py` | 调用 NIST `trec_eval` 并与本地实现交叉核对 |
| `src/analyze_runs.py` | 批量比较 run、生成逐 topic 和总体实验报告 |
| `tests/test_mvp.py` | 覆盖检索格式、RRF、改写、评测、压缩与排序校正的单元测试 |

`cache/`、`runs/`、`.env.local`、`.venv/` 和 `tools/trec_eval/` 都只保留在本地且已被 Git 忽略。

## 密钥

仓库根目录 `.env.local`：

```text
PYSERINI_API_TOKEN=你的官方检索Token
QUERY_REWRITE_BASE_URL=https://api.deepseek.com
QUERY_REWRITE_API_KEY=你的DeepSeekKey
QUERY_REWRITE_MODEL=deepseek-v4-flash
```

脚本不会打印密钥，也不接受命令行 API Key 参数。

## 从头跑开发集

### 1. 官方 BM25

```powershell
python retrieval_mvp/src/healthcheck.py
python retrieval_mvp/src/retrieve.py
python retrieval_mvp/src/validate_run.py `
  retrieval_mvp/runs/haerbin-bm25-dev.tsv `
  --expected-hits 1000
```

### 2. 扩大候选池到 Top-5000

```powershell
python retrieval_mvp/src/retrieve_multiquery.py `
  --provider llm `
  --no-fallback `
  --baseline-run retrieval_mvp/runs/haerbin-bm25-dev.tsv `
  --baseline-weight 4 `
  --hits-per-query 1000 `
  --output-hits 5000 `
  --output retrieval_mvp/runs/deepseek-deep5000.tsv `
  --run-id haerbin-deepseek-deep5000
```

查询改写和所有官方检索响应都会缓存，失败后可直接重跑续接。

### 3. MiniLM 粗排 5000 个候选

```powershell
.\.venv\Scripts\python.exe retrieval_mvp/src/rerank.py `
  retrieval_mvp/runs/deepseek-deep5000.tsv `
  --model cross-encoder/ms-marco-MiniLM-L-6-v2 `
  --depth 5000 `
  --dtype float16 `
  --device cuda `
  --batch-size 128 `
  --original-weight 4 `
  --semantic-weight 1 `
  --output retrieval_mvp/runs/deep5000-minilm-o4.tsv `
  --run-id haerbin-deep5000-minilm-o4
```

### 4. BGE 精排并输出完整候选池

排序质量优先：

```powershell
.\.venv\Scripts\python.exe retrieval_mvp/src/rerank.py `
  retrieval_mvp/runs/deep5000-minilm-o4.tsv `
  --model BAAI/bge-reranker-v2-m3 `
  --depth 1000 `
  --dtype float16 `
  --device cuda `
  --batch-size 16 `
  --original-weight 2 `
  --semantic-weight 1 `
  --output retrieval_mvp/runs/haerbin-balanced-v2-deep-dev.tsv `
  --run-id haerbin-balanced-v2-deep
```

召回/MAP 更稳的版本只需把 `--original-weight` 改为 `8`，输出到 `haerbin-recall-v2-deep-dev.tsv`。

官方当前规则明确说每题没有固定的最大返回数，所以完整候选池也是合法 run。若希望生成更小的 Top-1000 文件，在命令中加入 `--output-hits 1000`；已经生成的对应文件是 `haerbin-balanced-v2-dev.tsv` 和 `haerbin-recall-v2-dev.tsv`。

模型分数保存在 `cache/reranker/`；调整融合权重不会重新进行 GPU 推理。

## 当前结果

下表使用 Codex UMBRELA qrels、相关阈值 `>=2`，并由 NIST `trec_eval` 计算。nDCG 使用 graded qrels；Recall/MAP 使用阈值化二元 qrels。

| Run | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: |
| 官方 BM25 | 0.5940 | 0.5881 | **0.1081** | 0.2664 | 0.1381 |
| 旧 Balanced | 0.6902 | 0.6535 | 0.1036 | 0.3063 | 0.1621 |
| **Balanced v2 deep** | **0.7210** | **0.6655** | 0.0996 | **0.3381** | 0.1913 |
| **Recall v2 deep** | 0.6792 | 0.6406 | 0.1059 | **0.3381** | **0.1966** |

Top-5000 候选池的 Recall@5000 为：Codex `0.5225`、Ministral `0.4781`、Qwen `0.5148`。如果裁成 Top-1000，Codex MAP 会分别变成 `0.1666` 和 `0.1719`，Recall@5000 也会等于 Recall@1000；因此除非后续提交系统另有限制，建议保留完整深度。

## 官方评测和本地评测的区别

- `evaluate_run.py` 是我们自己的快速诊断程序。
- `official_eval.py` 调用 NIST 官方 `trec_eval`；当前所有指标与本地实现的差异小于约 `0.00005`。
- 三套 qrels 是比赛方发布的开发数据，但属于 UMBRELA/模型生成判断，不是最终 NIST 人工判断。
- 119 个正式 test topics 没有公开 qrels，因此现在无法在本地得到正式测试分数。正式成绩要生成 runfile、按比赛方流程提交，等待组织方/NIST 评测。
- RAGDoll 不直接读取六列 Retrieval runfile 输出官方 nDCG/MAP；其 UMBRELA 流程可以对 query-document pair 生成 0–3 级相关性判断。本项目已用该官方流程对 v3 Top-10 完成 220 条本地诊断，结果见 `reports/ragdoll_top10.md`。

本机已经在 WSL 中构建好 `usnistgov/trec_eval`。运行：

```powershell
python retrieval_mvp/src/official_eval.py `
  retrieval_mvp/runs/haerbin-balanced-v2-deep-dev.tsv `
  --rel-threshold 2
```

## 验证

```powershell
python retrieval_mvp/src/validate_run.py `
  retrieval_mvp/runs/haerbin-balanced-v2-deep-dev.tsv
python -m unittest discover retrieval_mvp/tests -v
```

正式测试时，把检索命令的 `--topics` 指向 `retrieval_mvp/data/topics/trec_rag_2026_queries.tsv`。先在开发集固定参数，不要使用没有 qrels 的 test topics 调参。

## Advanced Hybrid v3

在 v2 之上已经实现并实测：

```text
Balanced v2
  → BGE-small dense hybrid RRF
  → ColBERTv2 Top-100 late-interaction 校正
  → query-aware 句子压缩
  → DeepSeek RankLLM Top-20 listwise 校正
```

最终开发 run：`runs/haerbin-hybrid-v3-dev.tsv`。Codex qrels 的结果为 nDCG@10 `0.7243`、nDCG@20 `0.6658`、Recall@1000 `0.3423`、Recall@5000 `0.5225`、MAP `0.1937`。

新增脚本：

- `src/build_docstore.py`：把原始 API JSON 缓存转换为 SQLite docid 正文库。
- `src/dense_rerank.py`：BGE bi-encoder dense 排名和稀疏排名融合。
- `src/colbert_rerank.py`：ColBERTv2 token-level MaxSim 重排。
- `src/rankllm_rerank.py`：文档相关句压缩、DeepSeek listwise 重排和严格输出校正。

完整消融、三套 qrels 结果和不采用 Text2SQL/Text2Cypher 的原因见 `reports/advanced_retrieval_v3.md`。
