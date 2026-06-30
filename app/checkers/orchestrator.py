"""
app/checkers/orchestrator.py

Top-level reference checking logic.

Lookup priority:
  1. DOI  → OpenAlex → Crossref / DataCite
  2. DOI healing (broken DOI reconstruction)
  3. arXiv ID
  4. Title search (OpenAlex)

Similarity scoring is applied to every result to help the UI flag
likely hallucinations.
"""
from .extraction import (
    extract_title_from_reference,
    extract_doi_info,
    heal_doi,
    extract_arxiv_id,
)
from .normalizer import calculate_similarity, strip_doi_punctuation
from .backends import openalex, crossref, datacite, arxiv as arxiv_backend, url_checker, web_fallback


def _run_doi_search_cycle(doi: str) -> dict:
    """
    Try OpenAlex first, then Crossref/DataCite based on the DOI prefix.
    Zenodo DOIs go to DataCite before Crossref; everything else reversed.
    """
    # 1. OpenAlex
    res = openalex.lookup_by_doi(doi)
    if res["status"] == "found":
        return res

    # 2. Zenodo/DataCite-first vs standard Crossref-first
    if "zenodo" in doi.lower() or "10.5281" in doi:
        res = datacite.lookup_by_doi(doi)
        if res["status"] == "found":
            return res
        res = crossref.lookup_by_doi(doi)
        if res["status"] == "found":
            return res
    else:
        res = crossref.lookup_by_doi(doi)
        if res["status"] == "found":
            return res
        res = datacite.lookup_by_doi(doi)
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

    print(f"\n[DEBUG] Checking reference...")
    print(f"  Original: {ref_text[:100]}...")

    try:
        extracted_title = extract_title_from_reference(ref_text)
    except Exception as e:
        print(f"  - Title extraction failed: {e}")
        extracted_title = ""

    result = None

    try:
        # --- Step 1: DOI lookup ---
        doi, end_pos = extract_doi_info(ref_text)
        if doi:
            doi_clean = strip_doi_punctuation(doi)
            print(f"  → Found DOI: {doi_clean}")
            result = _run_doi_search_cycle(doi_clean)

            # --- Step 2: DOI healing ---
            if not result or result["status"] != "found":
                print("  → DOI not found. Attempting to heal/expand...")
                healed_doi, _ = heal_doi(doi_clean, end_pos, ref_text)
                if healed_doi:
                    result = _run_doi_search_cycle(healed_doi)

        # --- Step 3: arXiv ---
        if not result or result["status"] != "found":
            arxiv_id = extract_arxiv_id(ref_text)
            if arxiv_id:
                print(f"  → Found arXiv ID: {arxiv_id}")
                result = arxiv_backend.lookup_by_id(arxiv_id)

        # --- Step 4: Title search ---
        if not result or result["status"] != "found":
            print(f"  Extracted title: {extracted_title[:80]}...")
            print("  → Falling back to title search...")
            result = openalex.lookup_by_title(extracted_title)
            
            # Fallback to web search if the match is poor (< 0.6 similarity)
            if result and result.get("status") == "found":
                sim = calculate_similarity(extracted_title, result.get("title", ""))
                if sim < 0.6:
                    print(f"  [DEBUG] OpenAlex match too weak (similarity {sim:.2f} < 0.60). Trying web search...")
                    result = {"status": "not_found"}

        # --- Step 4b: Web search fallback ---
        if not result or result["status"] != "found":
            print("  → Falling back to web search...")
            result = web_fallback.lookup_by_title(extracted_title, full_ref=ref_text)

        # --- Step 5: URL checker ---
        if not result or result["status"] != "found":
            url = url_checker.extract_url(ref_text)
            if url:
                result = url_checker.lookup_by_url(url, extracted_title)

    except Exception as e:
        print(f"  - Unexpected error in verification pipeline: {e}")
        return {"status": "error", "message": str(e), "similarity": 0.0}

    # Similarity scoring
    if result is not None:
        if result.get("status") == "found":
            fetched_title = result.get("title", "")
            similarity = calculate_similarity(extracted_title, fetched_title)
            result["similarity"] = similarity
            print(f"  [DEBUG] Similarity comparison:")
            print(f"  [DEBUG]   Extracted title: '{extracted_title}'")
            print(f"  [DEBUG]   Fetched title:   '{fetched_title}'")
            print(f"  [DEBUG]   Score: {similarity:.2f}")
        else:
            result["similarity"] = 0.0
    else:
        result = {"status": "not_found", "similarity": 0.0}

    return result
