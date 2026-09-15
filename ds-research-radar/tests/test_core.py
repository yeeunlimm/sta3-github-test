import sys
import unittest
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deduplicate import unique_items
from scoring import score
from weekly_candidates import actionability, article_text, build_report, feed_items, possible_event_clusters, watchlist_matches, wordcloud_svg


class DeduplicationTests(unittest.TestCase):
    def test_same_primary_url_is_duplicate(self):
        first = {"title": "A", "primary_source_url": "https://example.org/paper"}
        second = {"title": "Renamed A", "primary_source_url": "https://example.org/paper/"}
        unique, duplicates = unique_items([first, second])
        self.assertEqual(unique, [first])
        self.assertEqual(duplicates, [second])

    def test_title_and_organization_fallback(self):
        first = {"title": "Model-X: Results", "organization": "Example Lab"}
        second = {"title": "model x results", "organization": "example lab"}
        unique, duplicates = unique_items([first, second])
        self.assertEqual(len(unique), 1)
        self.assertEqual(len(duplicates), 1)


class ScoringTests(unittest.TestCase):
    def test_full_evidence_scores_100(self):
        self.assertEqual(score({name: 1 for name in ("ds_relevance", "technical_impact", "evidence_quality", "industry_signal", "novelty")}), 100)

    def test_missing_evidence_is_not_invented(self):
        self.assertEqual(score({"ds_relevance": 1}), 30)

    def test_invalid_signal_is_rejected(self):
        with self.assertRaises(ValueError):
            score({"novelty": 1.1})


class WeeklyCandidateTests(unittest.TestCase):
    def test_atom_feed_extracts_lightweight_metadata(self):
        entries = feed_items(
            """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Embedding retrieval</title><link href="https://example.org/post"/><updated>2026-09-14T00:00:00Z</updated><summary>AI search system</summary></entry></feed>""",
            "GeekNews",
        )
        self.assertEqual(entries[0]["title"], "Embedding retrieval")
        self.assertEqual(entries[0]["primary_source_url"], "https://example.org/post")

    def test_wordcloud_is_empty_when_no_industry_candidates(self):
        self.assertIn("No industry candidates", wordcloud_svg(Counter()))

    @patch("weekly_candidates.fetch_article")
    @patch("weekly_candidates.fetch_feed")
    def test_report_keeps_only_recent_unseen_relevant_candidates(self, mocked_fetch, mocked_article):
        mocked_fetch.return_value = [
            {
                "title": "Multilingual language model evaluation",
                "primary_source_url": "https://example.org/new",
                "published_at": "2026-09-14T00:00:00Z",
                "summary": "A benchmark for LLM evaluation.",
                "source": "ResearchFeed",
            },
            {
                "title": "Old climate paper",
                "primary_source_url": "https://example.org/old",
                "published_at": "2026-08-31T00:00:00Z",
                "summary": "Climate research.",
                "source": "ResearchFeed",
            },
            {
                "title": "Previously read AI evaluation",
                "primary_source_url": "https://example.org/seen",
                "published_at": "2026-09-14T00:00:00Z",
                "summary": "LLM evaluation.",
                "source": "ResearchFeed",
            },
        ]
        mocked_article.side_effect = lambda item, timeout: {
            **item,
            "original_text": "Original report text with evidence.",
            "original_read_status": "read",
            "detail_summary_draft": "원문 읽기 초안",
            "detail_summary_prompt": "요약 프롬프트",
            "review_status": "pending_human_confirmation",
            "notion_eligibility": "approved_only",
        }
        report, cache = build_report(
            {"ResearchFeed": "https://example.org/feed"},
            {"seen_identity_keys": ["primary_source_url:httpsexampleorgseen"]},
            datetime(2026, 9, 15, tzinfo=UTC),
            {"ResearchFeed"},
            approved_urls={"https://example.org/new"},
        )
        self.assertTrue(report["review_required"])
        self.assertFalse(report["notion_write_performed"])
        self.assertEqual([item["title"] for item in report["candidates"]], ["Multilingual language model evaluation"])
        self.assertEqual(report["summary"]["older_than_7_days_skipped"], 1)
        self.assertEqual(report["summary"]["previously_seen_skipped"], 1)
        self.assertEqual(report["summary"]["originals_read"], 1)
        self.assertEqual(report["summary"]["human_approved"], 1)
        self.assertTrue(report["trend_candidates"])
        self.assertEqual(report["candidates"][0]["review_status"], "approved")
        self.assertEqual(report["candidates"][0]["notion_eligibility"], "approved_only")
        self.assertIn("last_successful_run_at", cache)

    def test_article_text_excludes_script_content(self):
        extracted = article_text("<html><script>secret()</script><p>Useful evidence.</p><p>Second finding.</p></html>")
        self.assertEqual(extracted, "Useful evidence. Second finding.")

    def test_actionability_uses_only_explicit_evidence(self):
        score, evidence = actionability({}, {"code_available": True, "public_data": True, "modest_compute": False})
        self.assertEqual(score, 60)
        self.assertEqual(evidence, ["코드 공개", "공개 데이터"])
        self.assertIsNone(actionability({}, {})[0])

    def test_watchlist_and_event_clusters_are_review_cues(self):
        first = {"title": "New LLM evaluation benchmark", "summary": "ECMWF is not mentioned", "domains": ["language"], "primary_source_url": "https://example.org/1"}
        second = {"title": "New LLM evaluation benchmark release", "summary": "", "domains": ["language"], "primary_source_url": "https://example.org/2"}
        self.assertEqual(watchlist_matches(first, ["LLM evaluation", "ECMWF"]), ["LLM evaluation", "ECMWF"])
        self.assertEqual(len(possible_event_clusters([first, second])), 1)


if __name__ == "__main__":
    unittest.main()
