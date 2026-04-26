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
from .normalizer import calculate_similarity
from .backends import openalex, crossref, datacite, arxiv as arxiv_backend


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
        return {"status": "skipped", "reason": "Too short"}

    print(f"\n[DEBUG] Checking reference...")
    print(f"  Original: {ref_text[:100]}...")

    # Pre-extract title for similarity scoring at the end
    extracted_title = extract_title_from_reference(ref_text)

    result = None

    # --- Step 1: DOI lookup ---
    doi, end_pos = extract_doi_info(ref_text)
    if doi:
        print(f"  → Found DOI: {doi}")
        result = _run_doi_search_cycle(doi)

        # --- Step 2: DOI healing ---
        if not result or result["status"] != "found":
            print("  → DOI not found. Attempting to heal/expand...")
            healed_doi, _ = heal_doi(doi, end_pos, ref_text)
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

    # Similarity scoring
    if result and result.get("status") == "found":
        fetched_title = result.get("title", "")
        similarity = calculate_similarity(extracted_title, fetched_title)
        result["similarity"] = similarity
        print(f"  [DEBUG] Similarity comparison:")
        print(f"  [DEBUG]   Extracted title: '{extracted_title}'")
        print(f"  [DEBUG]   Fetched title:   '{fetched_title}'")
        print(f"  [DEBUG]   Score: {similarity:.2f}")

    return result
