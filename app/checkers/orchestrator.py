"""
app/checkers/orchestrator.py

Top-level reference checking logic.

Lookup priority:
  1. DOI  → OpenAlex → Crossref / DataCite
  2. DOI healing (broken DOI reconstruction)
  3. arXiv ID
  4. URL checker (direct URL from reference)
  5. Title search (OpenAlex)
  5b. DBLP title search (CS conference fallback)
  6. Web search fallback (DuckDuckGo)

Similarity scoring is applied to every result to help the UI flag
likely hallucinations.
"""
import logging
from .extraction import (
    extract_title_from_reference,
    extract_doi_info,
    extract_arxiv_id_from_text,
    heal_doi,
    build_original_url,
    heal_url,
)
from .normalizer import calculate_similarity, strip_doi_punctuation
from .config import WEB_FALLBACK_TRIGGER

logger = logging.getLogger(__name__)
from .backends import (
    OpenAlexBackend,
    CrossrefBackend,
    DataCiteBackend,
    ArxivBackend,
    URLCheckerBackend,
    WebFallbackBackend,
    DBLPBackend,
)

# --- Cached backend singletons (thread-safe after lazy init) ---

_openalex = None
_crossref = None
_datacite = None
_arxiv = None
_url_checker = None
_web_fallback = None
_dblp = None


def _get_openalex():
    global _openalex
    if _openalex is None:
        _openalex = OpenAlexBackend()
    return _openalex


def _get_crossref():
    global _crossref
    if _crossref is None:
        _crossref = CrossrefBackend()
    return _crossref


def _get_datacite():
    global _datacite
    if _datacite is None:
        _datacite = DataCiteBackend()
    return _datacite


def _get_arxiv():
    global _arxiv
    if _arxiv is None:
        _arxiv = ArxivBackend()
    return _arxiv


def _get_url_checker():
    global _url_checker
    if _url_checker is None:
        _url_checker = URLCheckerBackend()
    return _url_checker


def _get_web_fallback():
    global _web_fallback
    if _web_fallback is None:
        _web_fallback = WebFallbackBackend()
    return _web_fallback


def _get_dblp():
    global _dblp
    if _dblp is None:
        _dblp = DBLPBackend()
    return _dblp


def _run_doi_search_cycle(doi: str) -> dict:
    """
    Try OpenAlex first, then Crossref/DataCite based on the DOI prefix.
    Zenodo DOIs go to DataCite before Crossref; everything else reversed.
    """
    # 1. OpenAlex
    res = _get_openalex().lookup_by_doi(doi)
    if res["status"] == "found":
        return res

    # 2. Zenodo/DataCite-first vs standard Crossref-first
    if "zenodo" in doi.lower() or "10.5281" in doi:
        res = _get_datacite().lookup_by_doi(doi)
        if res["status"] == "found":
            return res
        res = _get_crossref().lookup_by_doi(doi)
        if res["status"] == "found":
            return res
    else:
        res = _get_crossref().lookup_by_doi(doi)
        if res["status"] == "found":
            return res
        res = _get_datacite().lookup_by_doi(doi)
        if res["status"] == "found":
            return res

    return {"status": "not_found"}


def _try_doi_lookup(ref_text: str) -> dict:
    """Steps 1-2: Try DOI lookup with healing fallback."""
    doi, end_pos = extract_doi_info(ref_text)
    if not doi:
        return None

    doi_clean = strip_doi_punctuation(doi)
    logger.info(f"  → Step 1 DOI: {doi_clean}")
    result = _run_doi_search_cycle(doi_clean)

    # --- Step 2: DOI healing ---
    if not result or result["status"] != "found":
        healed_doi, _ = heal_doi(doi_clean, end_pos, ref_text)
        if healed_doi:
            logger.info(f"  → Step 2 DOI healed: {doi_clean} -> {healed_doi}")
            result = _run_doi_search_cycle(healed_doi)

    return result


def _try_arxiv_lookup(ref_text: str) -> dict:
    """Step 3: Try arXiv lookup."""
    arxiv_id = extract_arxiv_id_from_text(ref_text)
    if not arxiv_id:
        return None

    logger.info(f"  → Step 3 arXiv: {arxiv_id}")
    result = _get_arxiv().lookup_by_id(arxiv_id)
    return result


def _try_url_lookup(ref_text: str, title: str) -> dict:
    """Steps 4-4b: Try URL lookup with healing fallback."""
    urls = _get_url_checker().extract_urls(ref_text)
    if not urls:
        return None

    # Step 4: Direct URL lookup
    for url in urls:
        logger.info(f"  → Step 4 URL: {url}")
        result = _get_url_checker().lookup_by_url(url, title)
        if result["status"] == "found":
            return result

    # Step 4b: URL healing
    for url in urls:
        cleaned = url.rstrip(".,;:)]")
        idx = ref_text.find(cleaned)
        if idx >= 0:
            end_pos = idx + len(cleaned)
            healed, _ = heal_url(cleaned, end_pos, ref_text)
            if healed:
                logger.info(f"  → Step 4b URL healed: {url} -> {healed}")
                result = _get_url_checker().lookup_by_url(healed, title)
                if result["status"] == "found":
                    return result

    return {"status": "not_found"}


def _try_title_lookup(title: str) -> dict:
    """Steps 5-6: Try OpenAlex title search with fallbacks."""
    logger.info(f"  → Step 5 Title: {title[:60]}...")
    result = _get_openalex().lookup_by_title(title)

    # Fallback if the match is poor (< WEB_FALLBACK_TRIGGER similarity)
    if result and result.get("status") == "found":
        sim = calculate_similarity(title, result.get("title", ""))
        if sim < WEB_FALLBACK_TRIGGER:
            result = {"status": "not_found"}

    # Step 5b: DBLP title search (CS conference fallback)
    if not result or result["status"] != "found":
        logger.info("  → Step 5b DBLP")
        result = _get_dblp().lookup_by_title(title)

    # Step 6: Web search fallback (last resort)
    if not result or result["status"] != "found":
        logger.info("  → Step 6 Web search")
        result = _get_web_fallback().lookup_by_title(title, full_ref="")

    return result


def _apply_similarity_scoring(result: dict, extracted_title: str) -> dict:
    """Add similarity scoring to the result."""
    if result is None:
        result = {"status": "not_found", "similarity": 0.0}
    elif result.get("status") == "found":
        fetched_title = result.get("title", "")
        similarity = calculate_similarity(extracted_title, fetched_title)
        result["similarity"] = similarity
        logger.info(
            f"  ✓ Result: found (source: {result.get('source', 'N/A')}, similarity: {similarity:.2f})"
        )
    else:
        result.setdefault("similarity", 0.0)
        logger.info(f"  → Result: not_found")
    return result


def check_reference(ref_text: str) -> dict:
    """
    Main entry point. Accepts a raw reference string and returns a result dict:

        {
            "status":     "found" | "not_found" | "skipped" | "error",
            "source":     "OpenAlex" | "Crossref" | "DataCite" | "arXiv",
            "title":      str,
            "author":     str,
            "pub_year":   str,
            "venue":      str,
            "url":        str,
            "similarity": float,   # only when status == "found"
        }
    """
    if not ref_text or len(ref_text) < 10:
        logger.info("  → Skipped: Too short")
        return {
            "status": "skipped",
            "message": "Too short",
            "similarity": 0.0,
            "original_url": build_original_url(ref_text),
        }

    logger.info(f"  Checking reference: {ref_text[:80]}...")

    try:
        extracted_title = extract_title_from_reference(ref_text)
    except Exception as e:
        logger.warning(f"  Title extraction failed: {e}")
        extracted_title = ""

    result = None

    try:
        # --- Step 1-2: DOI lookup with healing ---
        if not result or result.get("status") != "found":
            result = _try_doi_lookup(ref_text)

        # --- Step 3: arXiv ---
        if not result or result.get("status") != "found":
            result = _try_arxiv_lookup(ref_text)

        # --- Steps 4-4b: URL lookup with healing ---
        if not result or result.get("status") != "found":
            result = _try_url_lookup(ref_text, extracted_title)

        # --- Steps 5-6: Title search with fallbacks ---
        if not result or result.get("status") != "found":
            result = _try_title_lookup(extracted_title)

    except Exception as e:
        logger.error(f"  Pipeline error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "similarity": 0.0,
            "original_url": build_original_url(ref_text),
        }

    # Similarity scoring
    result = _apply_similarity_scoring(result, extracted_title)

    result["original_url"] = build_original_url(ref_text)

    return result
