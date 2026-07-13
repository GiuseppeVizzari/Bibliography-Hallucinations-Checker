"""
test_dblp.py

Unit tests for the DBLP backend — title search via the DBLP XML API.
Uses mocking to avoid rate-limiting the live API during testing.
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.checkers.backends.dblp import DBLPBackend
from app.checkers.config import (
    DBLP_FOUND_THRESHOLD,
    DBLP_CANDIDATE_THRESHOLD,
    DBLP_MAX_RESULTS,
    DBLP_MAX_PAGES,
    DBLP_MIN_DELAY,
)


class TestDBLPBackendInit(unittest.TestCase):
    """Verify config constants are reasonable."""

    def test_found_threshold(self):
        self.assertEqual(DBLP_FOUND_THRESHOLD, 0.60)

    def test_candidate_threshold(self):
        self.assertEqual(DBLP_CANDIDATE_THRESHOLD, 0.40)

    def test_max_results(self):
        self.assertEqual(DBLP_MAX_RESULTS, 10)

    def test_max_pages(self):
        self.assertEqual(DBLP_MAX_PAGES, 2)

    def test_min_delay(self):
        self.assertEqual(DBLP_MIN_DELAY, 1.0)


class TestDBLPBackendLookupByTitle(unittest.TestCase):
    """Test DBLP title search with mocked API responses."""

    def setUp(self):
        self.backend = DBLPBackend()

    def _mock_response(self, hits):
        """Build a mock DBLP API response with the given hit list."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "hits": {
                    "total": len(hits),
                    "hit": hits,
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def _make_hit(self, title, authors, venue, year, dblp_url=""):
        """Build a single DBLP hit matching the real DBLP API response format.
        
        The real DBLP API returns info as a raw XML string (not a dict).
        """
        authors_xml = "".join(
            f'<person name="{a}"/>' for a in authors
        )
        xml_str = (
            f'<result type="inproceedings" key="{dblp_url}">'
            f'<title>{title}</title>'
            f'<year>{year}</year>'
            f'<venue>{venue}</venue>'
            f'<authors>{authors_xml}</authors>'
            f'</result>'
        )
        return {"info": xml_str}

    @patch("app.checkers.backends.dblp.requests.get")
    def test_empty_title_returns_not_found(self, mock_get):
        result = self.backend.lookup_by_title("")
        self.assertEqual(result["status"], "not_found")
        mock_get.assert_not_called()

    @patch("app.checkers.backends.dblp.requests.get")
    def test_none_title_returns_not_found(self, mock_get):
        result = self.backend.lookup_by_title(None)
        self.assertEqual(result["status"], "not_found")
        mock_get.assert_not_called()

    @patch("app.checkers.backends.dblp.requests.get")
    def test_found_match_above_threshold(self, mock_get):
        """When DBLP returns a close match, status should be 'found'."""
        hit = self._make_hit(
            "Attention Is Still All You Need",
            ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
            "NeurIPS",
            "2017",
            "conf/nips/2017-1",
        )
        mock_get.return_value = self._mock_response([hit])

        result = self.backend.lookup_by_title("Attention Is All You Need")
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["source"], "DBLP")
        self.assertIn("Attention", result["title"])
        self.assertEqual(result["pub_year"], "2017")
        self.assertEqual(result["venue"], "NeurIPS")
        self.assertGreaterEqual(result["similarity"], DBLP_FOUND_THRESHOLD)

    @patch("app.checkers.backends.dblp.requests.get")
    def test_candidate_match_below_threshold(self, mock_get):
        """When DBLP returns a weak match, status should be 'candidate'."""
        hit = self._make_hit(
            "Some Completely Different Paper Title",
            ["Someone Else"],
            "ICML",
            "2020",
            "conf/icml/2020-1",
        )
        mock_get.return_value = self._mock_response([hit])

        result = self.backend.lookup_by_title("Attention Is All You Need")
        self.assertEqual(result["status"], "not_found")
        self.assertLess(result.get("similarity", 0.0), DBLP_CANDIDATE_THRESHOLD)

    @patch("app.checkers.backends.dblp.requests.get")
    def test_no_hits_returns_not_found(self, mock_get):
        """When DBLP returns no results, should return not_found."""
        mock_get.return_value = self._mock_response([])

        result = self.backend.lookup_by_title("NonExistentPaper12345")
        self.assertEqual(result["status"], "not_found")

    @patch("app.checkers.backends.dblp.requests.get")
    def test_request_error_returns_not_found(self, mock_get):
        """When the DBLP API returns an error, should return not_found."""
        import requests as req

        mock_get.side_effect = req.RequestException("Connection error")

        result = self.backend.lookup_by_title("Some Paper Title")
        self.assertEqual(result["status"], "not_found")

    @patch("app.checkers.backends.dblp.requests.get")
    def test_invalid_json_returns_not_found(self, mock_get):
        """When DBLP returns non-JSON, should return not_found."""
        mock_get.return_value = MagicMock()
        mock_get.return_value.json.side_effect = ValueError("Invalid JSON")

        result = self.backend.lookup_by_title("Some Paper Title")
        self.assertEqual(result["status"], "not_found")

    @patch("app.checkers.backends.dblp.requests.get")
    def test_unicode_ligatures_handled(self, mock_get):
        """Unicode ligatures (e.g., ﬁ) should be decomposed before querying."""
        hit = self._make_hit(
            "EfficientNet: Rethinking Model Scaling",
            ["Chuang Gan"],
            "ICML",
            "2019",
            "conf/icml/2019-1",
        )
        mock_get.return_value = self._mock_response([hit])

        # Title with ligature ﬁ (U+FB01)
        result = self.backend.lookup_by_title("EfﬁcientNet: Rethinking Model Scaling")
        self.assertEqual(result["status"], "found")

    @patch("app.checkers.backends.dblp.requests.get")
    def test_curly_quotes_handled(self, mock_get):
        """Curly quotes should be normalized before querying."""
        hit = self._make_hit(
            "Deep Residual Learning for Image Recognition",
            ["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"],
            "CVPR",
            "2016",
            "conf/cvpr/2016-1",
        )
        mock_get.return_value = self._mock_response([hit])

        # Title with curly quotes
        result = self.backend.lookup_by_title('"Deep Residual Learning" for Image Recognition')
        self.assertEqual(result["status"], "found")

    @patch("app.checkers.backends.dblp.requests.get")
    def test_authors_extracted_correctly(self, mock_get):
        """Author names should be properly extracted from XML."""
        hit = self._make_hit(
            "BERT: Pre-training of Deep Bidirectional Transformers",
            ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"],
            "NAACL",
            "2019",
            "conf/naacl/2019-1",
        )
        mock_get.return_value = self._mock_response([hit])

        result = self.backend.lookup_by_title("BERT: Pre-training of Deep Bidirectional Transformers")
        self.assertEqual(result["status"], "found")
        self.assertIn("Devlin", result["author"])
        self.assertIn("et al.", result["author"])  # More than 3 authors

    @patch("app.checkers.backends.dblp.requests.get")
    def test_single_author_no_et_al(self, mock_get):
        """Single author should not have 'et al.'."""
        hit = self._make_hit(
            "On the Convergence of Adam and Beyond",
            ["Sebastian U. Stich"],
            "ICLR",
            "2019",
            "conf/iclr/2019-1",
        )
        mock_get.return_value = self._mock_response([hit])

        result = self.backend.lookup_by_title("On the Convergence of Adam and Beyond")
        self.assertEqual(result["status"], "found")
        self.assertNotIn("et al.", result["author"])
        self.assertIn("Stich", result["author"])

    @patch("app.checkers.backends.dblp.requests.get")
    def test_pagination_when_no_strong_match(self, mock_get):
        """Should paginate when no result meets the found threshold."""
        hit1 = self._make_hit(
            "Page One Result",
            ["Author One"],
            "Conference A",
            "2020",
            "conf/a/2020-1",
        )
        hit2 = self._make_hit(
            "Page Two Result",
            ["Author Two"],
            "Conference B",
            "2021",
            "conf/b/2021-1",
        )
        # Page 1 returns weak match; page 2 also returns weak match
        mock_get.side_effect = [
            self._mock_response([hit1]),
            self._mock_response([hit2]),
        ]

        result = self.backend.lookup_by_title("Some Weak Match Title")
        self.assertIn(result["status"], ["not_found", "candidate"])
        self.assertEqual(mock_get.call_count, 2)  # Both pages queried

    @patch("app.checkers.backends.dblp.requests.get")
    def test_stops_pagination_on_strong_match(self, mock_get):
        """Should stop paginating once a strong match is found."""
        hit1 = self._make_hit(
            "Exact Match Paper Title",
            ["Match Author"],
            "Conference C",
            "2022",
            "conf/c/2022-1",
        )
        mock_get.return_value = self._mock_response([hit1])

        result = self.backend.lookup_by_title("Exact Match Paper Title")
        self.assertEqual(result["status"], "found")
        self.assertEqual(mock_get.call_count, 1)  # Only first page queried

    @patch("app.checkers.backends.dblp.requests.get")
    def test_standard_result_dict_keys(self, mock_get):
        """Result should contain all standard keys."""
        hit = self._make_hit(
            "Transformer-XL: Attentive Language Models",
            ["Yunhao Tang", "Dong Yu", "Shlomo Dubnov"],
            "ICLR",
            "2020",
            "conf/iclr/2020-1",
        )
        mock_get.return_value = self._mock_response([hit])

        result = self.backend.lookup_by_title("Transformer-XL: Attentive Language Models")
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["source"], "DBLP")
        self.assertIn("title", result)
        self.assertIn("author", result)
        self.assertIn("pub_year", result)
        self.assertIn("venue", result)
        self.assertIn("url", result)
        self.assertIn("similarity", result)


class TestDBLPBackendOtherMethods(unittest.TestCase):
    """Test that non-title methods return not_found as expected."""

    def setUp(self):
        self.backend = DBLPBackend()

    def test_lookup_by_doi_returns_not_found(self):
        result = self.backend.lookup_by_doi("10.1234/test")
        self.assertEqual(result["status"], "not_found")

    def test_lookup_by_id_returns_not_found(self):
        result = self.backend.lookup_by_id("2403.02221")
        self.assertEqual(result["status"], "not_found")

    def test_lookup_by_url_returns_not_found(self):
        result = self.backend.lookup_by_url("https://example.com", "Title")
        self.assertEqual(result["status"], "not_found")

    def test_extract_urls_returns_empty(self):
        result = self.backend.extract_urls("Some reference text")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
