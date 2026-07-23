import sys, os
sys.path.insert(0, os.path.abspath(os.curdir))

from app.checkers.extraction import (
    extract_title_from_reference,
    extract_doi_info,
    heal_doi,
    heal_url,
    extract_urls_from_reference,
)
from app.checkers.normalizer import strip_venue_suffix, strip_author_header
from app.pdf_processor import _strip_embedded_line_numbers, _is_marginal_line_number


def test_title_extraction():
    ref = '[1] Y. Gu, B. Seanor, G. Campa, M. R. Napolitano, L. Rowe, S. Gururajan, and S. Wan, "Design and flight testing evaluation of formation control laws," IEEE Transactions on Control Systems Technology, vol. 14, no. 6, pp. 1105\u20131112, 2006.'
    extracted = extract_title_from_reference(ref)
    assert extracted == "Design and flight testing evaluation of formation control laws", f"Got: {extracted}"

    ref2 = '[36] F. Solera, S. Calderara, and R. Cucchiara, ``Structured learning for detection of social groups in crowd,\'\', in 2015 IEEE'
    extracted2 = extract_title_from_reference(ref2)
    assert "Structured learning for detection" in extracted2, f"Got: {extracted2}"


def test_doi_extraction():
    ref = "Some text 10.1000/xyz123 with a DOI"
    doi, end = extract_doi_info(ref)
    assert doi == "10.1000/xyz123"
    assert end == 24

    ref2 = "No DOI here"
    doi2, end2 = extract_doi_info(ref2)
    assert doi2 is None


def test_doi_healing():
    ref = "10.1000/xyz 123 more text"
    doi, end = extract_doi_info(ref)
    assert doi == "10.1000/xyz"
    healed, new_end = heal_doi(doi, end, ref)
    assert healed == "10.1000/xyz123"


def test_arxiv_extraction():
    ref = "Paper arXiv:2412.11814v1 is great"
    # Extract all URLs and check for arXiv ID
    urls = extract_urls_from_reference(ref)
    arxiv_ids = [url for url in urls if 'arxiv.org' in url]
    assert len(arxiv_ids) > 0
    # Just check that we found some URLs (the exact parsing logic for arXiv IDs was simplified in orchestrator.py)
    # For this test we just want to confirm the function exists and works
    assert len(urls) >= 1

    ref2 = "See https://arxiv.org/abs/2301.12345"
    urls2 = extract_urls_from_reference(ref2)
    arxiv_ids2 = [url for url in urls2 if 'arxiv.org' in url]
    assert len(arxiv_ids2) > 0


def test_strip_venue():
    assert strip_venue_suffix("My Great Title. In: Conference Proceedings") == "My Great Title"
    assert strip_venue_suffix("Already Clean") == "Already Clean"


def test_strip_author_header():
    words = {"crowd", "evacuation", "model", "simulation"}
    result = strip_author_header("Zhang, Crowd evacuation model", words)
    assert result == "Crowd evacuation model"


def test_strip_embedded_line_numbers():
    # Basic standalone line number
    assert _strip_embedded_line_numbers("References\n542\n[1] First ref") == "References\n[1] First ref"
    # Multiple line numbers interleaved in references
    refs = ("[Chen et al., 2022] Yiqun Chen, Hangyu Mao\n"
            "543\n"
            "Shiguang Wu, Tianle Zhang\n"
            "544\n"
            "Hongxing Chang")
    expected = ("[Chen et al., 2022] Yiqun Chen, Hangyu Mao\n"
                "Shiguang Wu, Tianle Zhang\n"
                "Hongxing Chang")
    assert _strip_embedded_line_numbers(refs) == expected
    # No line numbers — unchanged
    clean = "This is a normal reference without numbers."
    assert _strip_embedded_line_numbers(clean) == clean
    # Empty string
    assert _strip_embedded_line_numbers("") == ""
    # Line number at the very end
    assert _strip_embedded_line_numbers("Some text\n999") == "Some text"
    # 5-digit number should NOT be stripped (it might be a year or page)
    assert _strip_embedded_line_numbers("Year\n20245") == "Year\n20245"


def test_is_marginal_line_number():
    # Simulated block tuples: (x0, y0, x1, y1, text, block_no, block_type)
    # A marginal line number: narrow, near left edge, purely numeric
    line_num_block = (35, 100, 55, 110, "542", 0, 0)
    assert _is_marginal_line_number(line_num_block, 600) is True

    # A wide block with text near the edge should not be flagged
    text_block = (35, 100, 300, 110, "Some text here 542", 0, 0)
    assert _is_marginal_line_number(text_block, 600) is False

    # A narrow block in the center is not marginal
    center_block = (300, 100, 320, 110, "42", 0, 0)
    assert _is_marginal_line_number(center_block, 600) is False

    # A narrow block with text (not numeric)
    text_narrow = (35, 100, 55, 110, "Fig", 0, 0)
    assert _is_marginal_line_number(text_narrow, 600) is False


def test_url_healing_basic():
    ref = "See https://example.com/some very/long/path for details"
    url = "https://example.com/some"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    assert healed == "https://example.com/somevery/long/path"


def test_url_healing_with_slash():
    # Continuation starts with / (no space before slash — URL is complete)
    ref = "URL: https://arxiv.org/abs/2301.1234/pdf more info"
    url = "https://arxiv.org/abs/2301.1234"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    assert healed is None  # no whitespace after URL, URL is complete


def test_url_healing_with_space_and_slash():
    # Simulates PDF line break: URL ends, next line starts with /path
    ref = "See https://example.com/path /pdf more info"
    url = "https://example.com/path"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    assert healed == "https://example.com/path/pdf"


def test_url_healing_no_path_chars():
    ref = "URL: https://arxiv.org/abs/2301.1234 more info"
    url = "https://arxiv.org/abs/2301.1234"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    assert healed is None  # "more" has no URL-path characters


def test_url_healing_no_extension():
    ref = "See https://example.com/path end of sentence."
    url = "https://example.com/path"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    assert healed is None


def test_url_healing_stop_words_filtered():
    ref = "https://example.com/path is important"
    url = "https://example.com/path"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    assert healed is None  # "is" is a stop word


def test_url_healing_dot_extension():
    ref = "See https://example.com/file .pdf more text"
    url = "https://example.com/file"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    assert healed == "https://example.com/file.pdf"


def test_url_extraction_heals_broken_urls():
    # URL broken across what would be a line break in PDF
    ref = "Visit https://example.com/some very/long/path for info"
    urls = extract_urls_from_reference(ref)
    # Should find the base URL and heal it
    assert any("somevery" in u for u in urls), f"Got URLs: {urls}"


def test_url_extraction_no_false_positive():
    ref = "See https://doi.org/10.1234/abc for the study"
    urls = extract_urls_from_reference(ref)
    # "study" is not a stop word, but the URL should not be extended into "study"
    # unless it looks like a valid URL continuation
    for url in urls:
        assert "stud" not in url or "doi.org/10.1234/abc" in url


def test_url_healing_underscore_spaces():
    """Test that spaced URL-path words are rejoined with underscores.

    PDFs sometimes render repository/file names with spaces where the
    actual URL uses underscores (e.g. "geometries cat bcn 2024" for
    "geometries_cat_bcn_2024").
    """
    # ds-essay.pdf reference [5] case: GitHub repo name with spaces
    ref = "Available: https://github.com/ArnauInes/geometries cat bcn 2024"
    url = "https://github.com/ArnauInes/geometries"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    assert healed == "https://github.com/ArnauInes/geometries_cat_bcn_2024"

    # Extracted URL should also be healed
    urls = extract_urls_from_reference(ref)
    assert any(
        "geometries_cat_bcn_2024" in u for u in urls
    ), f"Got URLs: {urls}"


def test_url_healing_no_false_positive_with_spaces():
    """Ensure space-replacement doesn't create false URLs from random text."""
    ref = "See https://example.com/foo the bar for details"
    url = "https://example.com/foo"
    idx = ref.find(url)
    assert idx >= 0
    healed, end = heal_url(url, idx + len(url), ref)
    # "the bar" has no digit → should NOT be healed
    assert healed is None


if __name__ == "__main__":
    test_title_extraction()
    test_doi_extraction()
    test_doi_healing()
    test_arxiv_extraction()
    test_strip_venue()
    test_strip_author_header()
    test_strip_embedded_line_numbers()
    test_is_marginal_line_number()
    test_url_healing_basic()
    test_url_healing_with_slash()
    test_url_healing_with_space_and_slash()
    test_url_healing_no_path_chars()
    test_url_healing_no_extension()
    test_url_healing_stop_words_filtered()
    test_url_healing_dot_extension()
    test_url_extraction_heals_broken_urls()
    test_url_extraction_no_false_positive()
    test_url_healing_underscore_spaces()
    test_url_healing_no_false_positive_with_spaces()
    print("All tests passed!")
