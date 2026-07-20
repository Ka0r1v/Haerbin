# Recall 漏检分析与 V4 Candidate 实验

本报告记录 2026-07-19 完成的五项工作：逐 topic Recall 统计、漏检文本分析、差异化 typed query routes、独立全库召回器可行性核验，以及 BM25/V2/V3 统一 RAGDoll shallow-pool 对比。

统一主评测口径：22 个开发 topics、Codex UMBRELA qrels、相关阈值 `>=2`、NIST `trec_eval`、linear-gain nDCG。

## 1. 逐 topic 相关文档与漏检

完整表格见：

- `topic_recall_analysis.tsv`：机器可读的逐 topic 命中、Recall 和漏检数量；
- `topic_miss_analysis.md`：逐 topic 表格与抽样漏检类别分析。

Codex qrels 中每个 topic 的已知相关文档数量：

| 统计 | 数量 |
| --- | ---: |
| 最少 | 173 |
| 中位数 | 609 |
| 最多 | 925 |

因此 Recall 偏低不是因为“每题本来就没有多少相关文档”。相反，每题通常有数百篇 grade `>=2` 的已知相关文档。

V3 Recall@5000 最差的 topics：

| qid | 相关总数 | V3 命中@5000 | Recall@5000 | 漏检 |
| --- | ---: | ---: | ---: | ---: |
| 200 | 494 | 147 | 0.298 | 347 |
| 219 | 580 | 188 | 0.324 | 392 |
| 37 | 827 | 269 | 0.325 | 558 |
| 407 | 296 | 101 | 0.341 | 195 |
| 84 | 701 | 279 | 0.398 | 422 |

V3 Recall@5000 最好的 topics：

| qid | 相关总数 | V3 命中@5000 | Recall@5000 | 漏检 |
| --- | ---: | ---: | ---: | ---: |
| 499 | 609 | 512 | 0.841 | 97 |
| 213 | 173 | 133 | 0.769 | 40 |
| 225 | 555 | 388 | 0.699 | 167 |
| 161 | 687 | 470 | 0.684 | 217 |
| 58 | 516 | 341 | 0.661 | 175 |

## 2. 漏检文本模式

方法：从每个 topic 的 V3 Top-5000 之外，按 qrels grade 优先抽样 5 篇相关文档，共 110 篇；通过官方 Pyserini `/doc/{docid}` 读取原文；DeepSeek 只基于 topic 和这些原文，分析实体别名、时间、地点、术语和 query facet。

该分析只用于发现模式。每题 5 篇样本不能代表该题全部漏检文档的类别比例。

从 22 个 topic 的抽样证据生成的推荐路由频次：

| 路由类型 | 次数 |
| --- | ---: |
| 独立信息 facet | 48 |
| 专业术语/缩写/领域表达 | 43 |
| 地域/司法辖区 | 16 |
| 实体名/别名 | 14 |
| 时间/历史阶段 | 10 |

典型模式：

- Topic 200：`Holocaust` 与 `Shoah`、`Final Solution`、`Aktion Reinhard` 等历史术语和别名；
- Topic 233：`FOMO`、`#StatusOfMind`、平台名与青少年心理健康 facet；
- Topic 407：原问题包含 Dubai，但相关池中还有 Canada/Australia/US 的 zoning、planning restrictions、gentrification 证据；
- Topic 161：`Dobbs`、`Roe`、`quickening`、`viability` 以及 India/Canada 等比较法地域；
- Topic 31：`electronic waste` 与 `WEEE`、有毒化学物、发展中国家工人健康和企业回收步骤。

## 3. 差异化 Typed Query Routes

新增 `src/retrieve_facet_routes.py`。它生成查询时只读取原始 topic，不读取 qrels、漏检文档或上面的每题建议，因此不会把开发集漏检标签直接泄漏进查询。

每题默认生成：

- 3 条 `facet`：分别针对独立机制、后果、论点或证据类型；
- 2 条 `terminology`：针对专业、法律、科学术语或缩写；
- 最多 1 条 `entity_alias`：原 topic 有依据时才生成；
- 最多 1 条 `temporal`：存在时间/历史需求时才生成；
- 最多 1 条 `geographic`：存在地域/司法辖区需求时才生成。

校正规则：

- 每条不超过 24 个词；
- 只使用普通分析文本，不使用 Lucene Boolean/field/quote 语法；
- Jaccard 相似度过高的近重复查询被删除；
- 实体、日期、地点不能脱离 topic 凭空添加；
- baseline BM25 保留 weight 4，typed routes 使用较低类型权重；
- 所有 LLM 输出和 148 次官方搜索均缓存。

### 3.1 路由类型消融

以下是 typed-route candidate run 自己的结果，还没有经过 V3 的 cross-encoder/ColBERT/RankLLM：

| 路由 | nDCG@10 | Recall@100 | Recall@1000 | Recall@5000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Facet only | 0.6324 | 0.1079 | 0.2828 | 0.4264 | 0.1621 |
| Terminology only | 0.6166 | 0.1072 | 0.2665 | 0.3657 | 0.1465 |
| Facet + Terminology | 0.6441 | 0.1078 | 0.2820 | 0.4719 | 0.1663 |
| Facet + Entity/Time/Geo | 0.6372 | **0.1099** | 0.2884 | 0.4652 | 0.1687 |
| **全部 typed routes** | **0.6515** | 0.1094 | **0.2901** | **0.4846** | **0.1717** |

结论：facet 是主要召回来源；术语对深层候选有明显补充；实体/时间/地域路由对较浅层 Recall 更有帮助；五种类型合并后的整体候选质量最好。

### 3.2 与旧 V3 候选的互补性

虽然 typed routes 单独 Recall@5000 `0.4846` 低于 V3 的 `0.5225`，但两个 Top-5000 候选集合的相关文档并不相同：

| 项目 | 相关文档数（22 topics 合计） |
| --- | ---: |
| typed routes 找到、V3 未找到 | **1008** |
| V3 找到、typed routes 未找到 | 1625 |
| 两个 Top-5000 并集中的相关文档 | 7699 |

所以 typed routes 不应该替换 V3，而应该作为互补候选源。

## 4. 融合与头部保护

直接对 V3 和 typed routes 做 weighted RRF：

| V3:Facet | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | Recall@5000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8:1 | 0.7135 | 0.6692 | 0.1034 | 0.3454 | 0.5378 | 0.1997 |
| 4:1 | 0.7082 | 0.6670 | 0.1055 | 0.3463 | 0.5434 | 0.2030 |
| 2:1 | 0.7014 | 0.6611 | 0.1095 | **0.3477** | 0.5519 | **0.2058** |
| 1:1 | 0.6849 | 0.6490 | **0.1120** | 0.3428 | **0.5565** | 0.2041 |

融合提高 Recall/MAP，但会扰乱已经较好的 V3 Top-10。为此给 `src/fuse_runs.py` 增加 `--head-run` 和 `--head-depth`，先锁定 V3 头部，再只融合后续候选。

### 4.1 当前 V4 Candidate：Protect Top-10

配置：V3:typed routes=`2:1`，锁定 V3 Top-10，输出 Top-5000。

| Run | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | Recall@5000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.5940 | 0.5881 | 0.1081 | 0.2664 | 0.2664 | 0.1381 |
| V3 | 0.7243 | 0.6658 | 0.1016 | 0.3423 | 0.5225 | 0.1937 |
| **V4 candidate / protect10** | **0.7243** | **0.6677** | **0.1095** | **0.3477** | **0.5519** | **0.2061** |

相对 V3：

- nDCG@10：保持不变；
- nDCG@20：`+0.0019`；
- Recall@100：`+0.0079`，并超过 BM25；
- Recall@1000：`+0.0054`；
- Recall@5000：`+0.0294`；
- MAP：`+0.0124`。

该结果已由 NIST `trec_eval` 核验，本地实现误差均小于约 `0.00004`。

## 5. 独立全库第二召回器可行性

截至 2026-07-19，官方 Pyserini REST skill 对 ClimbMix 指定的唯一索引是 `climbmix-400b`。官方还列出了 FineWeb-Edu 和 MS MARCO V2.1 索引，但它们是不同语料，不能用于 ClimbMix Retrieval submission。

实际 OpenAPI 只暴露两类路径：

- `/{index}/search`；
- `/{index}/doc/{docid}`。

官方说明还明确：查询按普通分析文本处理，Boolean、fielded query 和 quotes 不提供独立检索语义。当前没有公开 ClimbMix dense/Faiss/SPLADE 第二端点，也没有发现可在本机下载并独立遍历的完整 ClimbMix index。`/doc/{docid}` 只能读取已知 docid，不能枚举全库。

因此：

- 当前 BGE dense、ColBERT 仍是候选内 reranker，不是独立全库召回器；
- typed query routing 是当前唯一实际可用的“扩大候选集合”手段，但后端仍是同一个 BM25 index；
- 如果官方随后发布 dense baseline/index、完整语料访问或新的 API 路由，应优先接入并与 BM25 做独立候选并集；
- 官网仍只写“Baselines week of July 19”，本次核验时尚未找到 2026 baseline 下载链接。

## 6. BM25 / V2 / V3 公平 RAGDoll Pool

构建方法：每个系统取 Top-10，按 `qid+docid` 合并去重，形成统一的 341 个 query-document pair。所有候选都使用同一个官方 RAGDoll UMBRELA prompt、Pi runner 和 `deepseek/deepseek-v4-flash` judge。

已有 V3 judgment 复用 220 条，只新增判断 121 个候选。一次 CLI 超时产生 93 组重复 judgment，其中 25 组 grade 不一致；这些冲突单独进行第三票并以中位数解决。失败尝试没有造成任何唯一候选缺失。

统一 shallow-pool 结果（exponential-gain nDCG）：

| Run | pooled nDCG@10 | grade>=2 | judged |
| --- | ---: | ---: | ---: |
| BM25 | 0.7285 | 49.55%（109/220） | 220 |
| V2 | 0.8465 | 63.18%（139/220） | 220 |
| V3 | **0.8509** | **64.09%（141/220）** | 220 |

这比此前只判断 V3 自己 Top-10 得到的 `0.9034` 更公平。新的 `0.8509` 使用 BM25/V2/V3 统一候选池构造 ideal ranking，因此能直接比较三个系统。它仍然不是全库 qrels，不能计算可信的 Recall@1000/5000，也不是正式 leaderboard 分数。

## 7. 新增/修改文件

| 文件 | 用途 |
| --- | --- |
| `src/analyze_misses.py` | 逐 topic Recall、漏检数量、官方 doc lookup、抽样 facet 分析 |
| `src/retrieve.py` | 新增官方 `/doc/{docid}` 客户端 |
| `src/retrieve_facet_routes.py` | 只基于 topic 生成 typed routes、检索、缓存、类型消融 |
| `src/fuse_runs.py` | 新增头部保护融合 |
| `src/build_ragdoll_pool.py` | 构建稳定 task id 的多系统 shallow pool、复用 judgment、生成冲突第三票任务 |
| `src/evaluate_ragdoll_pool.py` | 对统一 pool 计算多个 run 的 pooled nDCG 和相关率 |
| `reports/topic_recall_analysis.tsv` | 逐 topic 机器可读统计 |
| `reports/topic_miss_analysis.md` | 逐 topic 漏检文本模式 |
| `reports/ragdoll_bm25_v2_v3_pool.md` | 统一 RAGDoll pool 结果 |

## 8. 下一步

1. 把 protect10 作为 V4 candidate，在三套公开 qrels 上做稳定性验证；
2. 减少 typed query 数量，寻找 3–5 条路由达到接近当前 Recall 的低成本组合；
3. 对 V4 新增候选做 cross-encoder，而不是只依靠 RRF 排序；
4. 继续监控官方 2026 baseline，若出现独立 dense/sparse index 立即接入；
5. 正式 test topics 只能使用“原 topic → typed routes”的无 qrels 泄漏路径，不能使用开发集漏检分析生成的每题建议查询。
