# Haerbin — TREC RAG 2026

本仓库整理 TREC RAG 2026 的 Retrieval 与 Retrieval-Augmented Generation（RAG）任务资料，并实现了一套可复现的 Retrieval MVP。当前开发重点是 Task 1：在官方 ClimbMix/Pyserini 检索服务之上提高候选召回和排序质量；Task 2 的官方说明与可借鉴的 Ragnarök 代码也已纳入仓库。

## 当前状态

- 已跑通官方 Pyserini REST API 的 BM25 baseline。
- 已加入 DeepSeek 查询压缩、问题分解、多查询检索和 weighted RRF。
- 已加入 MiniLM、BGE cross-encoder、BGE dense hybrid、ColBERTv2 和 RankLLM 多阶段重排。
- 已实现六列 TREC runfile 校验、本地指标计算和 NIST `trec_eval` 交叉验证。
- 已用官方 RAGDoll/UMBRELA 流程对最终系统的 22 个开发查询 Top-10 做真实 LLM judge 诊断。
- 119 个正式 test topics 没有公开 qrels，目前只能生成提交文件，不能在本地得到正式排行榜分数。

## 最终 Retrieval 链路

```text
官方 ClimbMix BM25
→ DeepSeek 原查询压缩 + 5 个方面子查询
→ weighted RRF 合并为 Top-5000 候选池
→ MiniLM cross-encoder 粗排 Top-5000
→ BGE v2-m3 cross-encoder 精排 Top-1000
→ BGE-small dense hybrid RRF
→ ColBERTv2 MaxSim 校正 Top-100
→ query-aware 文档压缩 + DeepSeek RankLLM 校正 Top-20
→ 六列 TREC runfile
```

系统不下载或重建完整 ClimbMix，不重新对全库 chunk/embedding。官方服务负责索引和第一阶段召回；本项目缓存服务返回的候选正文，并只对候选池做语义打分和重排。

## 开发集结果

以下使用 22 个开发 topics、Codex UMBRELA qrels、相关阈值 `>=2`，由 NIST `trec_eval` 计算；nDCG 使用 graded qrels，Recall/MAP 使用阈值化 qrels。

| 版本 | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | Recall@5000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 官方 BM25 | 0.5940 | 0.5881 | **0.1081** | 0.2664 | 0.2664 | 0.1381 |
| Balanced v2 | 0.7210 | 0.6655 | 0.0996 | 0.3381 | 0.5225 | 0.1913 |
| Balanced v2 + Dense | 0.7150 | **0.6680** | 0.1016 | **0.3423** | 0.5225 | **0.1938** |
| + ColBERT Top-100 | 0.7214 | 0.6651 | 0.1016 | **0.3423** | 0.5225 | 0.1936 |
| **Hybrid v3 + RankLLM** | **0.7243** | 0.6658 | 0.1016 | **0.3423** | **0.5225** | 0.1937 |

相对 BM25，最终 v3 的 nDCG@10 提高 `0.1303`，Recall@1000 提高 `0.0759`，MAP 提高 `0.0556`。Recall@100 略有下降，说明当前系统更擅长重新排列和扩大深层候选池，但浅层召回仍是下一阶段的主要优化点。

三套官方开发 qrels 的稳定性、完整消融和每项技术的取舍见 [advanced_retrieval_v3.md](retrieval_mvp/reports/advanced_retrieval_v3.md)。

### RAGDoll Top-10 诊断

使用官方 RAGDoll/UMBRELA prompt、Pi runner 和 `deepseek/deepseek-v4-flash`，对 v3 的 22×Top-10 共 220 个 query-document pair 判分：

| 指标 | 结果 |
| --- | ---: |
| 成功判断 | 220 / 220 |
| 解析失败 | 0 |
| Top-10 nDCG | 0.9034 |
| UMBRELA 等级 `>=2` | 141 / 220（64.09%） |
| UMBRELA 等级 `>=1` | 218 / 220（99.09%） |
| 平均等级 | 1.7773 / 3 |

该结果只衡量当前 Top-10 内部排序，不能用于估计 Recall@100/1000/5000，也不能与上面的公开 qrels 分数直接比较。详见 [ragdoll_top10.md](retrieval_mvp/reports/ragdoll_top10.md)。

## 目录说明

| 路径 | 用途 |
| --- | --- |
| `docs/` | Retrieval、RAG 两项官方规则的本地整理和中文讲解 |
| `retrieval_mvp/` | 当前 Retrieval 实验代码、公开开发数据、测试和实验报告 |
| `retrieval_mvp/src/` | 检索、查询改写、融合、重排、校验和评测脚本 |
| `retrieval_mvp/data/topics/` | 22 个开发 topics 与 119 个正式 test topics |
| `retrieval_mvp/data/qrels/` | 三套公开 UMBRELA 开发 qrels |
| `retrieval_mvp/reports/` | 参数比较、消融、v3 与 RAGDoll 结果 |
| `retrieval_mvp/tests/` | 不调用外部 API 的单元测试 |
| `ragnarok/` | Castorini Ragnarök 源码快照，用于研究 Task 2、RankLLM 和引用生成 |
| `.vscode/` | 可直接在 VS Code 运行的 healthcheck、检索、重排和评测任务 |

各个 Retrieval 脚本的职责、完整运行命令和缓存策略见 [Retrieval MVP README](retrieval_mvp/README.md)。Ragnarök 中实际借鉴和暂未采用的部分见 [RAGNAROK_NOTES.md](retrieval_mvp/RAGNAROK_NOTES.md)。

## 快速开始

### 1. 创建环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r retrieval_mvp/requirements-rerank.txt
```

### 2. 配置本地密钥

复制 `retrieval_mvp/.env.example` 为仓库根目录 `.env.local`，然后填写：

```text
PYSERINI_API_TOKEN=<官方提供的 token>
QUERY_REWRITE_BASE_URL=https://api.deepseek.com
QUERY_REWRITE_API_KEY=<你的 DeepSeek API key>
QUERY_REWRITE_MODEL=deepseek-v4-flash
```

`.env.local`、`.env`、运行缓存、模型缓存、runfile、RAGDoll judgment 和本地工具目录均被 Git 忽略。代码只从环境变量或 `.env.local` 读取密钥，不会把密钥写入 runfile。

### 3. 健康检查与单元测试

```powershell
python retrieval_mvp/src/healthcheck.py
python -m unittest discover retrieval_mvp/tests -v
```

### 4. 跑官方 BM25 MVP

```powershell
python retrieval_mvp/src/retrieve.py
python retrieval_mvp/src/validate_run.py `
  retrieval_mvp/runs/haerbin-bm25-dev.tsv `
  --expected-hits 1000
python retrieval_mvp/src/evaluate_run.py `
  retrieval_mvp/runs/haerbin-bm25-dev.tsv `
  --rel-threshold 2
```

高级 v3 的分阶段命令见 [retrieval_mvp/README.md](retrieval_mvp/README.md)。首次运行需要下载模型并调用外部 API；之后会优先复用本地缓存。

## 凭据与提交策略

以下内容不会进入 Git：

- `.env`、`.env.*`（示例文件除外）和 `.curlrc.pyserini-rest`；
- `retrieval_mvp/cache/`、`runs/`、`candidates/`；
- `.venv/`、下载的 `trec_eval`、RAGDoll、Pi 和模型文件。

提交前应运行 `git status --ignored` 和凭据扫描，不要把 API key 放入命令行、日志、README、issue 或 commit message。

## 资料来源

- [TREC RAG 2026 官方网站](https://trec-rag.github.io/)
- [TREC RAG Skills](https://github.com/TREC-RAG/trec-rag-skills)
- [TREC RAG Data](https://github.com/TREC-RAG/trec-rag-data)
- [Castorini RAGDoll](https://github.com/castorini/RAGDoll)
- [Castorini Ragnarök](https://github.com/castorini/ragnarok)

如本仓库说明与官方最新规则不一致，以官方规则为准。
