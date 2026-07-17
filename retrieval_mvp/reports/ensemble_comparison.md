# Retrieval run comparison

Averaged per topic across 3 qrels files; relevance threshold >= 2.

| Run | nDCG@10 | nDCG@20 | Recall@100 | Recall@1000 | MAP |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.4601 | 0.4585 | 0.0997 | 0.2506 | 0.1386 |
| MiniLM-o4 | 0.5440 | 0.5174 | 0.0973 | 0.2925 | 0.1669 |
| BGE-o2 | 0.5736 | 0.5454 | 0.0947 | 0.2925 | 0.1666 |
| BGE-o4 | 0.5408 | 0.5134 | 0.0978 | 0.2925 | 0.1676 |
| Ensemble-o4-m1-b1 | 0.5691 | 0.5424 | 0.0965 | 0.2925 | 0.1684 |
| Ensemble-o6-m1-b1 | 0.5508 | 0.5243 | 0.0973 | 0.2925 | 0.1687 |
| Ensemble-o8-m1-b1 | 0.5464 | 0.5148 | 0.0981 | 0.2925 | 0.1678 |
| Ensemble-o4-m05-b1 | 0.5530 | 0.5264 | 0.0963 | 0.2925 | 0.1688 |
| Ensemble-o4-m1-b05 | 0.5501 | 0.5264 | 0.0965 | 0.2925 | 0.1684 |
| Ensemble-o6-m05-b1 | 0.5471 | 0.5130 | 0.0976 | 0.2925 | 0.1679 |

## Ensemble-o6-m05-b1: largest nDCG@10 gains

- Topic 213: +0.3155
- Topic 200: +0.1723
- Topic 144: +0.1414
- Topic 233: +0.1215
- Topic 14: +0.1180

## Ensemble-o6-m05-b1: largest nDCG@10 losses

- Topic 31: -0.0428
- Topic 515: +0.0097
- Topic 300: +0.0435
- Topic 407: +0.0463
- Topic 707: +0.0514
