"""
app/checkers/backends/dblp.py

DBLP API backend — title search for computer science conference/journal proceedings.

DBLP is used as a fallback when OpenAlex title search fails or returns low-confidence
matches, because DBLP covers CS conference proceedings that OpenAlex indexes poorly.
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict

import requests

from ..normalizer import calculate_similarity, normalize_ligatures, normalize_quotes
from ..config import (
    DBLP_FOUND_THRESHOLD,
    DBLP_CANDIDATE_THRESHOLD,
    DBLP_MAX_RESULTS,
    DBLP_MAX_PAGES,
    DBLP_MIN_DELAY,
)
from .base import BackendService

logger = logging.getLogger(__name__)

DBLP_API = "https://dblp.org/search/publ/api"


def _parse_authors(xml_authors) -> str:
    """Extract author names from a DBLP <authors> element."""
    names = []
    for person in xml_authors.findall("person"):
        name = person.get("name", "")
        if name:
            names.append(name)
    if not names:
        return "N/A"
    if len(names) > 3:
        return ", ".join(names[:3]) + ", et al."
    return ", ".join(names)


def _build_dblp_url(result: ET.Element) -> str:
    """Build a DBLP URL from a DBLP result element."""
    href = result.get("url", "")
    if href and href.startswith("http"):
        return href
    return ""


def _get_text(parent: ET.Element, tag: str) -> str:
    """Safely get text content of a child element."""
    el = parent.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return "N/A"


def _process_dblp_result(result: ET.Element, target_title: str) -> dict:
    """Convert a DBLP XML result element into the standard result dict with similarity."""
    title_text = _get_text(result, "title")

    authors_el = result.find("authors")
    authors = _parse_authors(authors_el) if authors_el is not None else "N/A"

    pub_year = _get_text(result, "year")
    venue = _get_text(result, "venue")

    url = _build_dblp_url(result)

    similarity = calculate_similarity(target_title, title_text)

    return {
        "status": "found",
        "source": "DBLP",
        "title": title_text,
        "author": authors,
        "pub_year": str(pub_year) if pub_year != "N/A" else "N/A",
        "venue": venue,
        "url": url,
        "similarity": similarity,
    }


class DBLPBackend(BackendService):
    """DBLP API backend implementation."""

    def lookup_by_doi(self, doi: str) -> dict:
        """Lookup by DOI — not implemented for DBLP (returns not_found)."""
        return {"status": "not_found"}

    def lookup_by_id(self, identifier: str) -> dict:
        """Lookup by identifier — not implemented for DBLP (returns not_found)."""
        return {"status": "not_found"}

    def lookup_by_title(self, title: str, full_ref: str = "") -> dict:
        """
        Search DBLP by title string.

        Queries the DBLP XML API with the normalized title, paginating up to
        DBLP_MAX_PAGES results. Returns the best match if similarity >= FOUND
        threshold, a candidate if >= CANDIDATE threshold, otherwise not_found.
        """
        if not title:
            return {"status": "not_found"}

        # Normalize the query: decompose ligatures, strip curly quotes, lowercase
        clean = normalize_quotes(title)
        clean = normalize_ligatures(clean)
        query = clean.strip()

        if not query:
            return {"status": "not_found"}

        logger.debug(f"  DBLP title search: {query[:70]}...")

        best_result = None
        best_similarity = 0.0

        for page in range(DBLP_MAX_PAGES):
            params = {
                "q": query,
                "format": "json",
                "h": DBLP_MAX_RESULTS,
                "p": page,
            }

            try:
                response = requests.get(DBLP_API, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                logger.debug(f"  - DBLP request error on page {page}: {e}")
                break
            except ValueError:
                logger.debug(f"  - DBLP returned non-JSON on page {page}")
                break

            results = data.get("result", {})
            hits = results.get("hits", {})
            hit_list = hits.get("hit", [])

            if not hit_list:
                break

            for hit in hit_list:
                info_xml = hit.get("info", "")
                if not info_xml:
                    continue

                res = _process_dblp_result(
                    ET.fromstring(info_xml),
                    title,
                )

                if res["status"] == "found" and res["similarity"] > best_similarity:
                    best_similarity = res["similarity"]
                    best_result = res

            # If we already have a strong match, skip pagination
            if best_similarity >= DBLP_FOUND_THRESHOLD:
                break

            # Rate limit: be polite to DBLP
            time.sleep(DBLP_MIN_DELAY)

        if best_result:
            sim = best_result["similarity"]
            if sim >= DBLP_FOUND_THRESHOLD:
                logger.debug(
                    f"  ✓ Found in DBLP (similarity {sim:.2f}): {best_result['title'][:60]}..."
                )
                return best_result
            elif sim >= DBLP_CANDIDATE_THRESHOLD:
                logger.debug(
                    f"  ~ DBLP candidate (similarity {sim:.2f}): {best_result['title'][:60]}..."
                )
                return {**best_result, "status": "candidate"}
            else:
                logger.debug(
                    f"  - DBLP best match too weak (similarity {sim:.2f} < {DBLP_CANDIDATE_THRESHOLD}): '{best_result['title'][:60]}'"
                )
        else:
            logger.debug("  - No results from DBLP")

        return {"status": "not_found"}

    def lookup_by_url(self, url: str, reference_title: str) -> dict:
        """Verify a URL resource — not implemented for DBLP (returns not_found)."""
        return {"status": "not_found"}

    def extract_urls(self, ref_text: str) -> list:
        """Extract non-DOI/non-arXiv URLs — not implemented for DBLP."""
        return []
