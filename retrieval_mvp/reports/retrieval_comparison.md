# Retrieval run comparison

Averaged per topic across 3 qrels files; relevance threshold >= 2.

| Run | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.4601 | 0.4585 | 0.0997 | 0.2506 | 0.1386 |
| DeepSeek-RRF | 0.4971 | 0.4768 | 0.0974 | 0.2925 | 0.1615 |
| MiniLM | 0.5440 | 0.5174 | 0.0973 | 0.2925 | 0.1669 |

## MiniLM: largest nDCG@10 gains

- Topic 213: +0.3236
- Topic 200: +0.1747
- Topic 144: +0.1377
- Topic 233: +0.1270
- Topic 273: +0.1246

## MiniLM: largest nDCG@10 losses

- Topic 31: -0.0431
- Topic 515: +0.0028
- Topic 707: +0.0085
- Topic 499: +0.0132
- Topic 37: +0.0440
