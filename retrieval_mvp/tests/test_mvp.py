from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from evaluate_run import evaluate  # noqa: E402
from analyze_runs import topic_metrics  # noqa: E402
from query_rewrite import heuristic_rewrite  # noqa: E402
from rankllm_rerank import compress_document, validate_ranking  # noqa: E402
from rerank import RunItem, extract_document_text, fused_order, write_run as write_reranked_run  # noqa: E402
from retrieve import Topic, normalize_candidates, read_topics, write_run  # noqa: E402
from retrieve_multiquery import build_queries, build_query_routes, query_cache_path  # noqa: E402
from rrf import reciprocal_rank_fusion  # noqa: E402
from validate_run import validate  # noqa: E402


class RetrievalMvpTests(unittest.TestCase):
    def test_end_to_end_mocked_retrieval_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            topics_path = root / "topics.tsv"
            run_path = root / "run.tsv"
            topics_path.write_text("q1\tfirst query\nq2\tsecond query\n", encoding="utf-8")
            topics = read_topics(topics_path)

            def fake_search(topic: Topic) -> dict:
                return {
                    "candidates": [
                        {"docid": f"shard_00001_{topic.qid[-1]}1", "rank": 1, "score": 2.0},
                        {"docid": f"shard_00001_{topic.qid[-1]}2", "rank": 2, "score": 1.0},
                    ]
                }

            topic_count, row_count = write_run(topics, run_path, "test-run", 2, fake_search)
            self.assertEqual((topic_count, row_count), (2, 4))
            errors, validated_topics, validated_rows = validate(
                run_path, topics_path, allow_subset=False, expected_hits=2
            )
            self.assertEqual(errors, [])
            self.assertEqual((validated_topics, validated_rows), (2, 4))

    def test_candidate_normalization_deduplicates_docids(self) -> None:
        payload = {
            "candidates": [
                {"docid": "shard_00001_1", "score": 3},
                {"docid": "shard_00001_1", "score": 2},
                {"docid": "shard_00001_2", "score": 1},
            ]
        }
        candidates = normalize_candidates(payload, hits=10)
        self.assertEqual([item.docid for item in candidates], ["shard_00001_1", "shard_00001_2"])

    def test_diagnostic_metrics_perfect_ranking(self) -> None:
        qrels = {"q1": {"d1": 4, "d2": 2, "d3": 0}}
        run = {"q1": ["d1", "d2", "d3"]}
        metrics = evaluate(qrels, run, threshold=1)
        for value in metrics.values():
            self.assertAlmostEqual(value, 1.0)

    def test_heuristic_rewrite_preserves_topic_and_creates_distinct_queries(self) -> None:
        topic = Topic(
            qid="q1",
            narrative=(
                "How does New York congestion pricing fund the MTA, affect Bronx pollution, "
                "change New Jersey traffic, and influence small business delivery costs?"
            ),
        )
        rewrite = heuristic_rewrite(topic, subquery_count=5)
        queries = build_queries(rewrite, "all")
        self.assertEqual(queries[0], topic.narrative)
        self.assertGreaterEqual(len(queries), 5)
        self.assertEqual(len(queries), len({query.casefold() for query in queries}))
        self.assertTrue(any("MTA" in query for query in queries))

    def test_query_cache_uses_query_hash(self) -> None:
        first = query_cache_path(Path("cache"), "q1", "first query")
        second = query_cache_path(Path("cache"), "q1", "second query")
        self.assertNotEqual(first, second)
        self.assertEqual(first.parent, second.parent)

    def test_query_routes_preserve_query_roles(self) -> None:
        topic = Topic(
            qid="q1",
            narrative=(
                "How does congestion pricing fund transit, affect pollution in the Bronx, "
                "and change delivery costs for small businesses?"
            ),
        )
        rewrite = heuristic_rewrite(topic, subquery_count=3)
        routes = build_query_routes(rewrite, "all")
        self.assertEqual(routes[0][0], "original")
        self.assertEqual(routes[1][0], "compressed")
        self.assertTrue(all(route == "subquery" for route, _ in routes[2:]))

    def test_rrf_rewards_documents_seen_in_multiple_rankings(self) -> None:
        fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60)
        self.assertEqual(fused[0].docid, "b")
        self.assertGreater(fused[0].score, fused[1].score)

    def test_weighted_rrf_can_prioritize_baseline(self) -> None:
        fused = reciprocal_rank_fusion(
            [["baseline", "shared"], ["rewrite", "shared"]],
            k=60,
            weights=[4.0, 1.0],
        )
        self.assertEqual(fused[0].docid, "shared")
        self.assertLess(
            [item.docid for item in fused].index("baseline"),
            [item.docid for item in fused].index("rewrite"),
        )

    def test_reranker_extracts_supported_document_shapes(self) -> None:
        self.assertEqual(extract_document_text(" passage "), "passage")
        self.assertEqual(extract_document_text({"contents": " body "}), "body")
        self.assertEqual(extract_document_text({"segment": "chunk"}), "chunk")
        self.assertIsNone(extract_document_text({"unknown": "value"}))

    def test_semantic_fusion_keeps_tail_and_can_change_head(self) -> None:
        items = [RunItem("a", 1, 3.0), RunItem("b", 2, 2.0), RunItem("c", 3, 1.0)]
        ordered = fused_order(
            items,
            {"a": 0.1, "b": 0.9},
            depth=2,
            original_weight=0.0,
            semantic_weight=1.0,
            rrf_k=60,
        )
        self.assertEqual([item.docid for item in ordered], ["b", "a", "c"])

    def test_reranker_can_limit_output_hits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "reranked.tsv"
            rows = write_reranked_run(
                output,
                {"q1": [RunItem("a", 1, 3.0), RunItem("b", 2, 2.0), RunItem("c", 3, 1.0)]},
                {"q1": {"a": 0.1, "b": 0.9, "c": 0.2}},
                depth=3,
                original_weight=1.0,
                semantic_weight=1.0,
                rrf_k=60,
                run_id="test",
                output_hits=2,
            )
            self.assertEqual(rows, 2)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 2)

    def test_per_topic_analysis_reports_expected_recall(self) -> None:
        metrics = topic_metrics({"a": 4, "b": 2, "c": 0}, ["a", "x", "b"], 2)
        self.assertEqual(metrics["Recall@100"], 1.0)
        self.assertGreater(metrics["nDCG@10"], 0.0)

    def test_rankllm_compression_prefers_query_relevant_sentence(self) -> None:
        document = "Cats sleep often. Congestion pricing funds transit service. Dogs like walks. " * 20
        compressed = compress_document("congestion pricing transit funding", document, max_chars=120)
        self.assertIn("Congestion pricing", compressed)
        self.assertLessEqual(len(compressed), 120)

    def test_rankllm_ranking_repairs_duplicates_and_missing_labels(self) -> None:
        ranking = validate_ranking({"ranking": ["D2", "d2", "D1"]}, ["D1", "D2", "D3"])
        self.assertEqual(ranking, ["D2", "D1", "D3"])


if __name__ == "__main__":
    unittest.main()
