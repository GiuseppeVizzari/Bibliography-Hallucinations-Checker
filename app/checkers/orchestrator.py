"""
app/checkers/orchestrator.py

Top-level reference checking logic.

Lookup priority:
  1. DOI  → OpenAlex → Crossref / DataCite
  2. DOI healing (broken DOI reconstruction)
  3. arXiv ID
  4. URL checker (direct URL from reference)
  5. Title search (OpenAlex)
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
)
from .normalizer import calculate_similarity, strip_doi_punctuation, WEB_FALLBACK_TRIGGER

logger = logging.getLogger(__name__)
from .backends import (
    OpenAlexBackend,
    CrossrefBackend,
    DataCiteBackend,
    ArxivBackend,
    URLCheckerBackend,
    WebFallbackBackend
)


def _run_doi_search_cycle(doi: str) -> dict:
    """
    Try OpenAlex first, then Crossref/DataCite based on the DOI prefix.
    Zenodo DOIs go to DataCite before Crossref; everything else reversed.
    """
    # 1. OpenAlex
    openalex_backend = OpenAlexBackend()
    res = openalex_backend.lookup_by_doi(doi)
    if res["status"] == "found":
        return res

    # 2. Zenodo/DataCite-first vs standard Crossref-first
    if "zenodo" in doi.lower() or "10.5281" in doi:
        datacite_backend = DataCiteBackend()
        res = datacite_backend.lookup_by_doi(doi)
        if res["status"] == "found":
            return res
        crossref_backend = CrossrefBackend()
        res = crossref_backend.lookup_by_doi(doi)
        if res["status"] == "found":
            return res
    else:
        crossref_backend = CrossrefBackend()
        res = crossref_backend.lookup_by_doi(doi)
        if res["status"] == "found":
            return res
        datacite_backend = DataCiteBackend()
        res = datacite_backend.lookup_by_doi(doi)
        if res["status"] == "found":
            return res

    return {"status": "not_found"}


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
        return {"status": "skipped", "reason": "Too short", "similarity": 0.0}

    logger.debug(f"\n[DEBUG] Checking reference...")
    logger.debug(f"  Original: {ref_text[:100]}...")

    try:
        extracted_title = extract_title_from_reference(ref_text)
    except Exception as e:
        logger.debug(f"  - Title extraction failed: {e}")
        extracted_title = ""

    result = None

    try:
        # --- Step 1: DOI lookup ---
        doi, end_pos = extract_doi_info(ref_text)
        if doi:
            doi_clean = strip_doi_punctuation(doi)
            logger.debug(f"  → Found DOI: {doi_clean}")
            result = _run_doi_search_cycle(doi_clean)

            # --- Step 2: DOI healing ---
            if not result or result["status"] != "found":
                logger.debug("  → DOI not found. Attempting to heal/expand...")
                healed_doi, _ = heal_doi(doi_clean, end_pos, ref_text)
                if healed_doi:
                    result = _run_doi_search_cycle(healed_doi)

        # --- Step 3: arXiv ---
        if not result or result["status"] != "found":
            arxiv_id = extract_arxiv_id_from_text(ref_text)

            if arxiv_id:
                logger.debug(f"  → Found arXiv ID: {arxiv_id}")
                arxiv_backend = ArxivBackend()
                result = arxiv_backend.lookup_by_id(arxiv_id)

        # --- Step 4: URL checker (direct URL from reference) ---
        if not result or result["status"] != "found":
            url_checker_backend = URLCheckerBackend()
            urls = url_checker_backend.extract_urls(ref_text)
            for url in urls:
                logger.debug(f"  → Trying URL from reference: {url}")
                result = url_checker_backend.lookup_by_url(url, extracted_title)
                if result["status"] == "found":
                    break
            else:
                if urls:
                    result = {"status": "not_found"}

        # --- Step 5: Title search ---
        if not result or result["status"] != "found":
            logger.debug(f"  Extracted title: {extracted_title[:80]}...")
            logger.debug("  → Falling back to title search...")
            openalex_backend = OpenAlexBackend()
            result = openalex_backend.lookup_by_title(extracted_title)

            # Fallback if the match is poor (< WEB_FALLBACK_TRIGGER similarity)
            if result and result.get("status") == "found":
                sim = calculate_similarity(extracted_title, result.get("title", ""))
                if sim < WEB_FALLBACK_TRIGGER:
                    logger.debug(f"  [DEBUG] OpenAlex match too weak (similarity {sim:.2f} < {WEB_FALLBACK_TRIGGER:.2f}). Trying web search...")
                    result = {"status": "not_found"}

        # --- Step 6: Web search fallback (last resort) ---
        if not result or result["status"] != "found":
            logger.debug("  → Falling back to web search...")
            web_fallback_backend = WebFallbackBackend()
            result = web_fallback_backend.lookup_by_title(extracted_title, full_ref=ref_text)

    except Exception as e:
        logger.debug(f"  - Unexpected error in verification pipeline: {e}")
        return {"status": "error", "message": str(e), "similarity": 0.0}

    # Similarity scoring
    if result is not None:
        if result.get("status") == "found":
            fetched_title = result.get("title", "")
            similarity = calculate_similarity(extracted_title, fetched_title)
            result["similarity"] = similarity
            logger.debug(f"  [DEBUG] Similarity comparison:")
            logger.debug(f"  [DEBUG]   Extracted title: '{extracted_title}'")
            logger.debug(f"  [DEBUG]   Fetched title:   '{fetched_title}'")
            logger.debug(f"  [DEBUG]   Score: {similarity:.2f}")
        else:
            result["similarity"] = 0.0
    else:
        result = {"status": "not_found", "similarity": 0.0}

    return result
