import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deduplicate import unique_items
from scoring import score


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


if __name__ == "__main__":
    unittest.main()
