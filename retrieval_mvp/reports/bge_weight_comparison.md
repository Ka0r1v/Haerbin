# Retrieval run comparison

Averaged per topic across 3 qrels files; relevance threshold >= 2.

| Run | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.4601 | 0.4585 | 0.0997 | 0.2506 | 0.1386 |
| DeepSeek-RRF | 0.4971 | 0.4768 | 0.0974 | 0.2925 | 0.1615 |
| MiniLM-o4 | 0.5440 | 0.5174 | 0.0973 | 0.2925 | 0.1669 |
| BGE-o1 | 0.5751 | 0.5245 | 0.0842 | 0.2925 | 0.1546 |
| BGE-o2 | 0.5736 | 0.5454 | 0.0947 | 0.2925 | 0.1666 |
| BGE-o4 | 0.5408 | 0.5134 | 0.0978 | 0.2925 | 0.1676 |
| BGE-o8 | 0.5229 | 0.4933 | 0.0981 | 0.2925 | 0.1653 |

## BGE-o8: largest nDCG@10 gains

- Topic 213: +0.2365
- Topic 233: +0.1376
- Topic 144: +0.1287
- Topic 161: +0.1206
- Topic 58: +0.0994

## BGE-o8: largest nDCG@10 losses

- Topic 407: -0.0362
- Topic 31: -0.0343
- Topic 499: +0.0033
- Topic 515: +0.0097
- Topic 200: +0.0300
