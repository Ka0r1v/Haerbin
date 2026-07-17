# Ragnarök 借鉴结论

本地 `ragnarok/` 是 Castorini 的端到端开源 RAG 基线。它在 TREC RAG 2025 的典型流程是：

```text
Anserini BM25 Top-100 → RankLLM / RankQwen3-32B 多轮重排 → Qwen3-32B 生成 → 引用格式校验
```

## 已经借鉴到 Retrieval MVP 的部分

1. **保留多阶段信号**：不让语义模型完全覆盖 BM25，而是通过 RRF 融合 BM25、DeepSeek 多查询、MiniLM 和 BGE 排名。
2. **候选正文缓存**：复用官方 Pyserini 响应中的 `doc`，不重复下载语料。
3. **标准候选请求**：`export_candidates.py` 输出 `query + candidates + doc.segment` JSONL，可作为 RankLLM 或 Ragnarök 生成阶段的输入桥梁。
4. **主 run 与召回保护 run 分离**：一个优化 nDCG/MAP，一个保护 Recall，避免单一参数承担冲突目标。

## 暂时不直接复制的部分

- RankQwen3-32B 官方示例需要约 4 张 GPU，本机 RTX 4060 8GB 不适合直接运行。
- Ragnarök 文档针对 TREC RAG 2025/MS MARCO，不能直接把数据集配置用于 2026/ClimbMix。
- `origin/Gemini` 分支的 `build_and_validate_rag_entry` 是一个有用的格式草稿，但尚未覆盖完整官方 validator 行为；进入 Task 2 时应基于 2026 规范重新实现并测试。

## 后续可接入

- 有更大 GPU 或远程推理服务时，把 Top-100 JSONL 交给 RankLLM 做 listwise 重排。
- Retrieval 参数固定后，复用 Ragnarök 的逐句引用解析、未引用 reference 清理、长度和引用范围校验思路构建 Task 2。
