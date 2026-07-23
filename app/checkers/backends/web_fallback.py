"""
app/checkers/backends/web_fallback.py

Web search fallback backend — uses a web search engine to find references
that are not indexed in academic databases (e.g. datasets, reports, news).
"""

import logging
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from ..extraction import extract_urls_from_reference
from ..normalizer import calculate_similarity
from ..config import (
    TITLE_SIMILARITY_THRESHOLD,
    WEB_BOOST_SNIPPET_CONTAINS,
    WEB_BOOST_TITLE_OVERLAP,
    WEB_BOOST_LENGTH_MATCH,
)
from .base import BackendService
from .security import validate_url_for_fetch

logger = logging.getLogger(__name__)


def _verify_page(url: str, target_title: str) -> bool:
    """
    Fetches the page and checks if the title is present in the <h1> or <title> tags.
    """
    try:
        validate_url_for_fetch(url)
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return False

        soup = BeautifulSoup(response.text, "html.parser")

        # 1. Check <title> tag
        page_title = soup.title.string.strip() if soup.title else ""
        if (
            page_title
            and calculate_similarity(target_title, page_title)
            > TITLE_SIMILARITY_THRESHOLD
        ):
            return True

        # 2. Check <h1> tags
        for h1 in soup.find_all("h1"):
            h1_text = h1.get_text().strip()
            if (
                h1_text
                and calculate_similarity(target_title, h1_text)
                > TITLE_SIMILARITY_THRESHOLD
            ):
                return True

        return False
    except Exception:
        return False


def _try_direct_url_verification(url: str, target_title: str) -> dict:
    """
    Attempts to verify a direct URL (DOI, arXiv) without web search.
    Returns a result dict if successful, otherwise None.
    """
    try:
        validate_url_for_fetch(url)
        # If it's an arXiv URL or DOI, we can try to fetch and check the title directly
        # This is a simplified check - in practice, you might want to do more sophisticated checks
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            # For arXiv, we might want to check the metadata from its API
            # For DOIs, we can use the DOI content negotiation service

            # Check if page title matches closely
            soup = BeautifulSoup(response.text, "html.parser")
            page_title = soup.title.string.strip() if soup.title else ""

            # Simple check - if title is not empty and matches the target
            if page_title:
                similarity = calculate_similarity(target_title, page_title)
                if similarity >= TITLE_SIMILARITY_THRESHOLD:
                    return {
                        "status": "found",
                        "source": "Direct URL Check",
                        "title": page_title,
                        "url": url,
                        "venue": "Web Page (Direct URL)",
                        "author": "Unknown",
                        "pub_year": "Unknown",
                        "similarity": similarity,
                    }
            # If title check failed but the URL is valid, return as candidate for further review
            return {
                "status": "candidate",
                "source": "Direct URL Check",
                "title": target_title,
                "url": url,
                "venue": "Web Page (Candidate - Direct URL)",
                "author": "Unknown",
                "pub_year": "Unknown",
                "similarity": 0.0,
            }
    except Exception as e:
        # Log the exception for debugging if needed, but don't fail the process
        logger.debug(f"  [DEBUG] Direct URL check failed for {url}: {e}")
        pass
    return None


class WebFallbackBackend(BackendService):
    """Web search fallback backend implementation."""

    def lookup_by_doi(self, doi: str) -> dict:
        """Lookup by DOI (not used for web fallback)."""
        return {"status": "not_found"}

    def lookup_by_id(self, identifier: str) -> dict:
        """Lookup by identifier (not used for web fallback)."""
        return {"status": "not_found"}

    def lookup_by_title(self, title: str, full_ref: str = "") -> dict:
        """
        Searches the web for the given title.
        If found and verified, returns a result dict.
        If no matches pass snippet check but search results exist,
        returns the best matching result as a 'candidate'.
        """
        if not title:
            return {"status": "not_found"}

        # First, check if there are any URLs in the original reference that we can use directly
        if full_ref:
            urls = extract_urls_from_reference(full_ref)
            for url in urls:
                result = _try_direct_url_verification(url, title)
                if result and result["status"] == "found":
                    return result
                elif result and result["status"] == "candidate":
                    # If we found a URL but it's not a perfect match, we can still return it as candidate
                    # Let the web search logic below handle further refinement if needed or use this result for display
                    pass  # Continue to web search logic below, but don't return here yet

        query = f'"{title}"'
        results = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
                if not results:
                    # Fallback to a more general search if quoted search returns no results
                    results = list(ddgs.text(title, max_results=5))
        except Exception as e:
            logger.debug(f"  [DEBUG] Web search error: {e}")
            return {"status": "not_found"}

        if not results:
            return {"status": "not_found"}

        # Rank results by similarity to the title
        ranked_results = []
        for res in results:
            url = res.get("href", "")
            res_title = res.get("title", "")
            snippet = res.get("body", "")

            # Primary score: similarity between target title and web result title
            score = calculate_similarity(title, res_title)

            # Boost score if the title is contained in the snippet or the result title is in the target title
            # This boost is important for finding exact matches even if there's some variation in titles
            if (snippet and title.lower() in snippet.lower()) or (
                res_title and res_title.lower() in title.lower()
            ):
                score = max(score, WEB_BOOST_SNIPPET_CONTAINS)

            # Additional boost for exact title matches or when the result title contains parts of the target title
            # This helps with cases where search engines return very similar titles but not exact matches
            if res_title and (
                title.lower() in res_title.lower()
                or (
                    len(title) > 10
                    and len(res_title) > 10
                    and any(word in res_title.lower() for word in title.lower().split())
                )
            ):
                score = max(score, WEB_BOOST_TITLE_OVERLAP)

            # Even more aggressive boost for very similar titles (within 10% difference in length)
            if res_title and abs(len(title) - len(res_title)) < len(title) * 0.1:
                score = max(score, WEB_BOOST_LENGTH_MATCH)

            ranked_results.append((score, res))

        # Sort by score descending
        ranked_results.sort(key=lambda x: x[0], reverse=True)
        best_score, best_res = ranked_results[0]

        # Additional debugging
        logger.debug(
            f"  [DEBUG] Web search best match: score={best_score:.2f}, title='{best_res.get('title')}'"
        )

        # If we have a very strong match, try to verify the page
        if best_score >= TITLE_SIMILARITY_THRESHOLD:
            url = best_res.get("href", "")
            # Ensure URL is valid before returning
            if not url or not url.startswith(("http://", "https://")):
                # If URL is invalid, try to find a better alternative or return not_found
                return {"status": "not_found"}
            if _verify_page(url, title):
                return {
                    "status": "found",
                    "source": "Web Search",
                    "title": title,
                    "url": url,
                    "venue": "Web Page",
                    "author": "Unknown",
                    "pub_year": "Unknown",
                    "similarity": best_score,
                }
            else:
                # Even if verification fails, if it's a good match, it's a candidate
                url = best_res.get("href", "")
                if not url or not url.startswith(("http://", "https://")):
                    # If URL is invalid, don't return a candidate
                    return {"status": "not_found"}
                return {
                    "status": "candidate",
                    "source": "Web Search",
                    "title": best_res.get("title", title),
                    "url": url,
                    "venue": "Web Page (Candidate)",
                    "author": "Unknown",
                    "pub_year": "Unknown",
                    "similarity": best_score,
                }

        # If score is decent, return as candidate - ensure URL exists
        if best_score >= 0.4:
            url = best_res.get("href", "")
            if not url or not url.startswith(("http://", "https://")):
                # If URL is invalid, return not_found instead of a candidate
                return {"status": "not_found"}
            return {
                "status": "candidate",
                "source": "Web Search",
                "title": best_res.get("title", title),
                "url": url,
                "venue": "Web Page (Candidate)",
                "author": "Unknown",
                "pub_year": "Unknown",
                "similarity": best_score,
            }

        return {"status": "not_found"}